"""V1.3 正式质量协议的加载、指纹与 Item/Dataset 聚合。"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.evaluation.metrics_safety import (
    is_deferral,
    is_extreme,
    is_legal_completed_prediction,
    is_severe,
    is_stop,
    normalized_gate_error,
)
from a2a_dygrade_rl.evaluation.qwk_readiness import evaluate_qwk_readiness, score_to_fixed_bin
from a2a_dygrade_rl.utils.io import read_yaml
from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol
from a2a_dygrade_rl.utils.validation import validate_quality_metric_protocol


def protocol_fingerprint(protocol: QualityMetricProtocol) -> str:
    payload = json.dumps(asdict(protocol), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_quality_protocol(path: str | Path) -> QualityMetricProtocol:
    data = read_yaml(path)
    qwk = data.get("qwk", {})
    bootstrap = data.get("bootstrap", {})
    safety = data.get("safety", {})
    gate = data.get("gate_error", {})
    selection = data.get("quality_champion", {})
    resource = data.get("resource_selection", {})
    protocol = QualityMetricProtocol(
        protocol_version=str(data.get("protocol_version", "quality_protocol_v1.3")),
        datasets=tuple(str(value) for value in data.get("datasets", QualityMetricProtocol.FORMAL_DATASETS)),
        gate_error_invalid_value=float(gate.get("invalid_or_incomplete_value", 1.0)),
        severe_threshold=float(safety.get("severe_threshold", 0.25)),
        severe_operator=str(safety.get("severe_operator", ">")),
        extreme_threshold=float(safety.get("extreme_threshold", 0.50)),
        extreme_operator=str(safety.get("extreme_operator", ">=")),
        unsafe_stop_denominator=str(safety.get("unsafe_stop_denominator", "all_stops")),
        zero_stop_policy=str(safety.get("zero_stop_policy", "na_quality_infeasible")),
        qwk_bin_count=11,
        qwk_fixed_labels=tuple(int(value) for value in qwk.get("fixed_labels", range(11))),
        qwk_mapping=str(qwk.get("mapping", "floor(10*z+0.5)_clip_0_10")),
        qwk_min_valid_completed=int(qwk.get("min_valid_completed_per_dataset", 100)),
        qwk_min_gold_nonempty_bins=int(qwk.get("min_gold_nonempty_bins", 2)),
        qwk_require_positive_expected_disagreement=bool(qwk.get("require_positive_expected_weighted_disagreement", True)),
        bootstrap_unit=str(bootstrap.get("unit", "paper")),
        bootstrap_paired=bool(bootstrap.get("paired", True)),
        bootstrap_replicates=int(bootstrap.get("replicates", 5000)),
        bootstrap_confidence_level=float(bootstrap.get("confidence_level", 0.95)),
        bootstrap_sidedness=str(bootstrap.get("sidedness", "one_sided")),
        noninferiority_margin=float(bootstrap.get("noninferiority_margin", 0.0)),
        bootstrap_seed=int(bootstrap.get("seed", 20260729)),
        bootstrap_quantile_method=str(bootstrap.get("quantile_method", "conservative_nearest_rank")),
        budget_ids=tuple(str(value) for value in data.get("quality_gates", {}).get("all_budget_ids_required", QualityMetricProtocol.FORMAL_BUDGETS)),
        quality_champion_order=tuple(str(value) for value in selection.get("order", QualityMetricProtocol().quality_champion_order)),
        resource_order=tuple(str(value) for value in resource.get("order", QualityMetricProtocol().resource_order)),
    )
    validate_quality_metric_protocol(asdict(protocol))
    return protocol


def gate_error(
    *,
    gold_score: float,
    pred_score: float | None,
    score_min: float,
    score_max: float,
    status: str = "completed",
    active_cache_valid: bool = True,
    invalid_value: float = 1.0,
) -> float:
    return normalized_gate_error(
        {
            "gold_score": gold_score,
            "pred_score": pred_score,
            "score_min": score_min,
            "score_max": score_max,
            "status": status,
            "active_cache_valid": active_cache_valid,
        },
        invalid_value=invalid_value,
    )


def evaluate_quality(
    records: Iterable[dict[str, Any]],
    *,
    protocol: QualityMetricProtocol | None = None,
    datasets: Iterable[str] | None = None,
    qwk_min_valid_completed: int | None = None,
) -> dict[str, Any]:
    protocol = protocol or QualityMetricProtocol.formal_v13()
    dataset_order = tuple(datasets) if datasets is not None else tuple(protocol.datasets)
    min_qwk_n = int(qwk_min_valid_completed if qwk_min_valid_completed is not None else protocol.qwk_min_valid_completed)
    rows = [dict(record) for record in records]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    item_rows: list[dict[str, Any]] = []
    for record in rows:
        dataset = str(record.get("dataset", ""))
        if dataset not in dataset_order:
            raise ValueError(f"质量协议遇到未注册 dataset: {dataset}")
        error = normalized_gate_error(record, protocol.gate_error_invalid_value)
        enriched = dict(record)
        enriched["gate_error"] = error
        enriched["severe"] = is_severe(error, protocol.severe_threshold)
        enriched["extreme"] = is_extreme(error, protocol.extreme_threshold)
        enriched["is_stop"] = is_stop(record)
        enriched["unsafe_stop"] = enriched["is_stop"] and enriched["severe"]
        enriched["is_deferral"] = is_deferral(record)
        enriched["valid_completed"] = is_legal_completed_prediction(record)
        grouped[dataset].append(enriched)
        item_rows.append(enriched)

    dataset_metrics: dict[str, dict[str, Any]] = {}
    readiness_records: dict[str, dict[str, Any]] = {}
    for dataset in dataset_order:
        dataset_rows = grouped.get(dataset, [])
        total = len(dataset_rows)
        severe_count = sum(bool(row["severe"]) for row in dataset_rows)
        extreme_count = sum(bool(row["extreme"]) for row in dataset_rows)
        stop_count = sum(bool(row["is_stop"]) for row in dataset_rows)
        unsafe_count = sum(bool(row["unsafe_stop"]) for row in dataset_rows)
        valid_rows = [row for row in dataset_rows if row["valid_completed"]]
        gold_bins = [score_to_fixed_bin(row["gold_score"], row["score_min"], row["score_max"]) for row in valid_rows]
        pred_bins = [score_to_fixed_bin(row["pred_score"], row["score_min"], row["score_max"]) for row in valid_rows]
        readiness = evaluate_qwk_readiness(
            dataset,
            gold_bins,
            pred_bins,
            min_valid_completed=min_qwk_n,
            min_gold_nonempty_bins=protocol.qwk_min_gold_nonempty_bins,
        )
        readiness_records[dataset] = readiness.to_dict()
        dataset_metrics[dataset] = {
            "item_count": total,
            "severe_count": severe_count,
            "severe_rate": severe_count / total if total else None,
            "extreme_count": extreme_count,
            "extreme_rate": extreme_count / total if total else None,
            "stop_count": stop_count,
            "unsafe_stop_count": unsafe_count,
            "unsafe_stop_rate": unsafe_count / stop_count if stop_count else None,
            "stop_coverage": stop_count / total if total else 0.0,
            "deferral_count": sum(bool(row["is_deferral"]) for row in dataset_rows),
            "deferral_rate": sum(bool(row["is_deferral"]) for row in dataset_rows) / total if total else None,
            "nmae": sum(float(row["gate_error"]) for row in dataset_rows) / total if total else None,
            "qwk": readiness.qwk,
            "qwk_defined": readiness.qwk_defined,
        }

    nmae_values = [dataset_metrics[dataset]["nmae"] for dataset in dataset_order]
    qwk_values = [dataset_metrics[dataset]["qwk"] for dataset in dataset_order]
    stop_ready = all((dataset_metrics[dataset]["stop_count"] or 0) > 0 for dataset in dataset_order)
    qwk_ready = all(readiness_records[dataset]["qwk_defined"] for dataset in dataset_order)
    datasets_nonempty = all((dataset_metrics[dataset]["item_count"] or 0) > 0 for dataset in dataset_order)
    total_items = len(item_rows)
    stop_count = sum(bool(row["is_stop"]) for row in item_rows)
    unsafe_count = sum(bool(row["unsafe_stop"]) for row in item_rows)
    macro_nmae = sum(float(value) for value in nmae_values) / len(nmae_values) if datasets_nonempty else None
    macro_qwk = sum(float(value) for value in qwk_values) / len(qwk_values) if qwk_ready else None
    return {
        "datasets": dataset_metrics,
        "qwk_readiness": readiness_records,
        "macro_nmae": macro_nmae,
        "micro_nmae": sum(float(row["gate_error"]) for row in item_rows) / total_items if total_items else None,
        "macro_qwk": macro_qwk,
        "worst_dataset_severe": max((dataset_metrics[d]["severe_rate"] for d in dataset_order), default=None) if datasets_nonempty else None,
        "worst_dataset_unsafe_stop": max((dataset_metrics[d]["unsafe_stop_rate"] for d in dataset_order), default=None) if stop_ready else None,
        "stop_count": stop_count,
        "unsafe_stop_count": unsafe_count,
        "unsafe_stop_rate": unsafe_count / stop_count if stop_count else None,
        "stop_coverage": stop_count / total_items if total_items else 0.0,
        "deferral_count": sum(bool(row["is_deferral"]) for row in item_rows),
        "deferral_rate": sum(bool(row["is_deferral"]) for row in item_rows) / total_items if total_items else 0.0,
        "stop_readiness": stop_ready,
        "qwk_ready": qwk_ready,
        "quality_metrics_defined": datasets_nonempty and stop_ready and qwk_ready and macro_nmae is not None and macro_qwk is not None,
        "items": item_rows,
        "protocol_hash": protocol_fingerprint(protocol),
    }
