"""以 Paper 为 cluster 的候选—比较基准配对 Bootstrap。"""

from __future__ import annotations

import hashlib
import json
import platform
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from a2a_dygrade_rl.evaluation.metrics_safety import (
    is_legal_completed_prediction,
    is_severe,
    is_stop,
    normalized_gate_error,
)
from a2a_dygrade_rl.evaluation.qwk_readiness import score_to_fixed_bin
from a2a_dygrade_rl.evaluation.statistical_gate import evaluate_bootstrap_gate
from a2a_dygrade_rl.utils.schemas import PairedBootstrapGateResult, QualityMetricProtocol


@dataclass
class _DatasetContribution:
    item_count: int = 0
    severe_count: int = 0
    stop_count: int = 0
    unsafe_stop_count: int = 0
    gate_error_sum: float = 0.0
    valid_completed_n: int = 0
    confusion: Counter[tuple[int, int]] = field(default_factory=Counter)
    gold_hist: Counter[int] = field(default_factory=Counter)
    pred_hist: Counter[int] = field(default_factory=Counter)

    def add(self, other: "_DatasetContribution") -> None:
        self.item_count += other.item_count
        self.severe_count += other.severe_count
        self.stop_count += other.stop_count
        self.unsafe_stop_count += other.unsafe_stop_count
        self.gate_error_sum += other.gate_error_sum
        self.valid_completed_n += other.valid_completed_n
        self.confusion.update(other.confusion)
        self.gold_hist.update(other.gold_hist)
        self.pred_hist.update(other.pred_hist)


@dataclass(frozen=True)
class _PreparedPaper:
    paper_id: str
    datasets: dict[str, _DatasetContribution]


def _prepare_papers(records: Iterable[dict[str, Any]], protocol: QualityMetricProtocol) -> dict[str, _PreparedPaper]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        paper_id = str(record.get("paper_id", ""))
        if not paper_id:
            raise ValueError("配对 Bootstrap record 缺少 paper_id")
        grouped[paper_id].append(dict(record))
    prepared: dict[str, _PreparedPaper] = {}
    for paper_id, rows in grouped.items():
        datasets: dict[str, _DatasetContribution] = defaultdict(_DatasetContribution)
        for row in rows:
            dataset = str(row.get("dataset", ""))
            if dataset not in protocol.datasets:
                raise ValueError(f"Bootstrap 遇到未注册 dataset: {dataset}")
            contribution = datasets[dataset]
            error = normalized_gate_error(row, protocol.gate_error_invalid_value)
            severe = is_severe(error, protocol.severe_threshold)
            stopped = is_stop(row)
            contribution.item_count += 1
            contribution.severe_count += int(severe)
            contribution.stop_count += int(stopped)
            contribution.unsafe_stop_count += int(stopped and severe)
            contribution.gate_error_sum += error
            if is_legal_completed_prediction(row):
                gold_bin = score_to_fixed_bin(row["gold_score"], row["score_min"], row["score_max"])
                pred_bin = score_to_fixed_bin(row["pred_score"], row["score_min"], row["score_max"])
                contribution.valid_completed_n += 1
                contribution.confusion[(gold_bin, pred_bin)] += 1
                contribution.gold_hist[gold_bin] += 1
                contribution.pred_hist[pred_bin] += 1
        prepared[paper_id] = _PreparedPaper(paper_id=paper_id, datasets=dict(datasets))
    return prepared


def _fixed_qwk(contribution: _DatasetContribution) -> tuple[float | None, float]:
    total = contribution.valid_completed_n
    if total <= 0:
        return None, 0.0
    labels = tuple(range(11))
    denominator = 100.0
    observed = 0.0
    expected = 0.0
    for truth in labels:
        for pred in labels:
            weight = ((truth - pred) ** 2) / denominator
            observed += weight * contribution.confusion[(truth, pred)] / total
            expected += weight * (contribution.gold_hist[truth] * contribution.pred_hist[pred]) / (total * total)
    if expected <= 0.0:
        return None, expected
    return 1.0 - observed / expected, expected


def _aggregate_metrics(
    papers: list[_PreparedPaper],
    sampled_indices: list[int],
    protocol: QualityMetricProtocol,
) -> dict[str, Any] | None:
    totals: dict[str, _DatasetContribution] = {dataset: _DatasetContribution() for dataset in protocol.datasets}
    for index in sampled_indices:
        paper = papers[index]
        for dataset, contribution in paper.datasets.items():
            totals[dataset].add(contribution)

    severe: dict[str, float] = {}
    unsafe: dict[str, float] = {}
    nmae: dict[str, float] = {}
    qwk: dict[str, float] = {}
    for dataset in protocol.datasets:
        contribution = totals[dataset]
        if contribution.item_count <= 0 or contribution.stop_count <= 0:
            return None
        dataset_qwk, expected = _fixed_qwk(contribution)
        if (
            contribution.valid_completed_n < protocol.qwk_min_valid_completed
            or len(contribution.gold_hist) < protocol.qwk_min_gold_nonempty_bins
            or expected <= 0.0
            or dataset_qwk is None
        ):
            return None
        severe[dataset] = contribution.severe_count / contribution.item_count
        unsafe[dataset] = contribution.unsafe_stop_count / contribution.stop_count
        nmae[dataset] = contribution.gate_error_sum / contribution.item_count
        qwk[dataset] = dataset_qwk
    return {
        "severe": severe,
        "unsafe_stop": unsafe,
        "macro_nmae": sum(nmae.values()) / len(protocol.datasets),
        "macro_qwk": sum(qwk.values()) / len(protocol.datasets),
    }


def _metric_deltas(candidate: dict[str, Any] | None, comparator: dict[str, Any] | None, datasets: tuple[str, ...]) -> dict[str, float] | None:
    if candidate is None or comparator is None:
        return None
    return {
        "max_dataset_delta_severe": max(candidate["severe"][dataset] - comparator["severe"][dataset] for dataset in datasets),
        "max_dataset_delta_unsafe_stop": max(
            candidate["unsafe_stop"][dataset] - comparator["unsafe_stop"][dataset] for dataset in datasets
        ),
        "delta_macro_nmae": candidate["macro_nmae"] - comparator["macro_nmae"],
        "delta_macro_qwk": candidate["macro_qwk"] - comparator["macro_qwk"],
    }



def _pairing_index(records: list[dict[str, Any]], label: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in records:
        key = (
            str(row.get("paper_id", "")),
            str(row.get("item_id", "")),
            str(row.get("dataset", "")),
        )
        if not all(key):
            raise ValueError(f"{label} Bootstrap record 缺少 paper_id/item_id/dataset")
        if key in index:
            raise ValueError(f"{label} Bootstrap record 出现重复 Paper/Item/Dataset key: {key}")
        index[key] = row
    return index


def _records_hash(records: list[dict[str, Any]]) -> str:
    ordered = sorted(
        records,
        key=lambda row: (
            str(row.get("paper_id", "")),
            str(row.get("item_id", "")),
            str(row.get("dataset", "")),
        ),
    )
    payload = json.dumps(ordered, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def paired_cluster_bootstrap(
    candidate_records: Iterable[dict[str, Any]],
    comparator_records: Iterable[dict[str, Any]],
    *,
    protocol: QualityMetricProtocol | None = None,
    candidate_id: str = "candidate",
    comparator_id: str = "comparator",
    budget_id: str = "unspecified",
    comparison_kind: str = "fixed_reference",
) -> PairedBootstrapGateResult:
    protocol = protocol or QualityMetricProtocol.formal_v13()
    if protocol.bootstrap_unit != "paper" or not protocol.bootstrap_paired:
        raise ValueError("正式 Bootstrap 必须是 Paper 级配对")
    candidate_rows = [dict(record) for record in candidate_records]
    comparator_rows = [dict(record) for record in comparator_records]
    candidate_index = _pairing_index(candidate_rows, "candidate")
    comparator_index = _pairing_index(comparator_rows, "comparator")
    if set(candidate_index) != set(comparator_index):
        raise ValueError("候选与比较基准必须使用完全相同的 Paper/Item/Dataset 集合")
    for key in sorted(candidate_index):
        candidate = candidate_index[key]
        comparator = comparator_index[key]
        for field_name in ("gold_score", "score_min", "score_max"):
            try:
                candidate_value = float(candidate[field_name])
                comparator_value = float(comparator[field_name])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"配对 Bootstrap 缺少合法 {field_name}: {key}") from exc
            if candidate_value != comparator_value:
                raise ValueError(f"候选与比较基准的 {field_name} 不一致: {key}")

    candidate_map = _prepare_papers(candidate_rows, protocol)
    comparator_map = _prepare_papers(comparator_rows, protocol)
    paper_ids = sorted(candidate_map)
    if paper_ids != sorted(comparator_map):
        raise ValueError("候选与比较基准 Paper 集合不一致")
    if not paper_ids:
        raise ValueError("配对 Bootstrap 至少需要一份 Paper")
    candidate_papers = [candidate_map[paper_id] for paper_id in paper_ids]
    comparator_papers = [comparator_map[paper_id] for paper_id in paper_ids]
    all_indices = list(range(len(paper_ids)))
    point_deltas = _metric_deltas(
        _aggregate_metrics(candidate_papers, all_indices, protocol),
        _aggregate_metrics(comparator_papers, all_indices, protocol),
        protocol.datasets,
    )
    if point_deltas is None:
        point_deltas_dict: dict[str, float | None] = {
            "max_dataset_delta_severe": None,
            "max_dataset_delta_unsafe_stop": None,
            "delta_macro_nmae": None,
            "delta_macro_qwk": None,
        }
    else:
        point_deltas_dict = point_deltas

    rng = random.Random(protocol.bootstrap_seed)
    digest = hashlib.sha256()
    replicate_deltas: dict[str, list[float]] = {
        "max_dataset_delta_severe": [],
        "max_dataset_delta_unsafe_stop": [],
        "delta_macro_nmae": [],
        "delta_macro_qwk": [],
    }
    undefined_replicates = 0
    for _ in range(protocol.bootstrap_replicates):
        sampled = [rng.randrange(len(paper_ids)) for _ in paper_ids]
        for index in sampled:
            digest.update(index.to_bytes(4, byteorder="little", signed=False))
        deltas = _metric_deltas(
            _aggregate_metrics(candidate_papers, sampled, protocol),
            _aggregate_metrics(comparator_papers, sampled, protocol),
            protocol.datasets,
        )
        if deltas is None:
            undefined_replicates += 1
            continue
        for key, value in deltas.items():
            replicate_deltas[key].append(value)

    if undefined_replicates:
        # 任一重采样 readiness 未定义，不能删掉失败 replicate 后继续宣称通过。
        replicate_deltas = {key: [] for key in replicate_deltas}
    paper_ids_hash = hashlib.sha256("\n".join(paper_ids).encode("utf-8")).hexdigest()
    reconstruction = {
        "sampling_algorithm": "python_random_randrange_v1",
        "python_version": platform.python_version(),
        "ordered_paper_ids": paper_ids,
        "ordered_paper_ids_hash": paper_ids_hash,
        "candidate_records_sha256": _records_hash(candidate_rows),
        "comparator_records_sha256": _records_hash(comparator_rows),
        "paper_count": len(paper_ids),
        "replicates": protocol.bootstrap_replicates,
        "seed": protocol.bootstrap_seed,
        "undefined_replicates": undefined_replicates,
    }
    return evaluate_bootstrap_gate(
        point_deltas=point_deltas_dict,
        replicate_deltas=replicate_deltas,
        protocol=protocol,
        candidate_id=candidate_id,
        comparator_id=comparator_id,
        budget_id=budget_id,
        comparison_kind=comparison_kind,
        resample_index_digest=digest.hexdigest(),
        reconstruction=reconstruction,
    )
