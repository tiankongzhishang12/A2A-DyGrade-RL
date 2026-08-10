"""Dev-only 三层 Policy Package / checkpoint 自动选择器。"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.evaluation.quality_protocol import protocol_fingerprint
from a2a_dygrade_rl.utils.io import write_csv, write_json
from a2a_dygrade_rl.utils.schemas import PolicyFreezeManifest, QualityMetricProtocol
from a2a_dygrade_rl.utils.validation import (
    validate_paired_bootstrap_gate_result,
    validate_policy_package,
)


@dataclass(frozen=True)
class CheckpointSelectionResult:
    status: str
    reference_admission_feasible_ids: tuple[str, ...]
    quality_champion_package_id: str | None
    quality_protection_feasible_ids: tuple[str, ...]
    selected_package_id: str | None
    selected_checkpoint_id: str | None
    dev_boundary_update_count: int
    quality_champion_resource_read_count: int
    quality_champion_manual_override_count: int
    selection_rows: tuple[dict[str, Any], ...]
    freeze_manifest: dict[str, Any] | None


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是数值") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值")
    return number


def _bounded(value: Any, label: str, lower: float, upper: float) -> float:
    number = _finite(value, label)
    if not lower <= number <= upper:
        raise ValueError(f"{label} 必须位于 [{lower},{upper}]")
    return number


def _nonnegative(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number < 0.0:
        raise ValueError(f"{label} 必须是非负数值")
    return number


_RESOURCE_METRIC_FIELDS = frozenset({
    "cost_per_paper",
    "elapsed_time_per_paper",
    "agent_calls_per_paper",
    "a2a_exchanges_per_paper",
})


class _QualityChampionEvaluation(dict[str, Any]):
    """在冠军质量排序阶段阻断并审计任何资源字段读取。"""

    def __init__(self, value: dict[str, Any], audit: dict[str, int]) -> None:
        super().__init__({key: item for key, item in value.items() if key not in _RESOURCE_METRIC_FIELDS})
        self._audit = audit

    def _guard(self, key: Any) -> None:
        if key in _RESOURCE_METRIC_FIELDS:
            self._audit["resource_reads"] += 1
            raise ValueError(f"Quality Champion resource field access is forbidden: {key}")

    def __getitem__(self, key: Any) -> Any:
        self._guard(key)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        self._guard(key)
        return super().get(key, default)


def _quality_champion_evaluation_index(
    evaluation_index: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, int]]:
    audit = {"resource_reads": 0}
    guarded = {
        key: _QualityChampionEvaluation(value, audit)
        for key, value in evaluation_index.items()
    }
    return guarded, audit


def _package_hash(package: dict[str, Any]) -> str:
    payload = json.dumps(package, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _evaluation_index(evaluations: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for evaluation in evaluations:
        key = (str(evaluation.get("package_id", "")), str(evaluation.get("budget_id", "")))
        if not all(key):
            raise ValueError("Dev evaluation 缺少 package_id 或 budget_id")
        if key in index:
            raise ValueError(f"Dev evaluation 重复: {key}")
        index[key] = dict(evaluation)
    return index


def _validate_evaluation(evaluation: dict[str, Any], protocol: QualityMetricProtocol) -> None:
    required = {
        "dataset_severe",
        "dataset_unsafe_stop",
        "macro_nmae",
        "macro_qwk",
        "cost_per_paper",
        "elapsed_time_per_paper",
        "agent_calls_per_paper",
        "a2a_exchanges_per_paper",
        "quality_metrics_defined",
        "stop_readiness",
        "qwk_ready",
        "budget_feasible",
    }
    missing = sorted(required - set(evaluation))
    if missing:
        raise ValueError(f"Dev evaluation 缺少字段: {missing}")
    for field in ("quality_metrics_defined", "stop_readiness", "qwk_ready", "budget_feasible"):
        if not isinstance(evaluation[field], bool):
            raise ValueError(f"{field} 必须是布尔值")
    if not (
        evaluation["quality_metrics_defined"]
        and evaluation["stop_readiness"]
        and evaluation["qwk_ready"]
    ):
        raise ValueError("Dev evaluation 的质量指标、STOP readiness 与 QWK readiness 必须全部定义")
    for metric_name in ("dataset_severe", "dataset_unsafe_stop"):
        values = evaluation[metric_name]
        if not isinstance(values, dict) or set(values) != set(protocol.datasets):
            raise ValueError(f"{metric_name} 必须完整覆盖冻结 datasets")
        for dataset, value in values.items():
            _bounded(value, f"{metric_name}.{dataset}", 0.0, 1.0)
    _bounded(evaluation["macro_nmae"], "macro_nmae", 0.0, 1.0)
    _bounded(evaluation["macro_qwk"], "macro_qwk", -1.0, 1.0)
    for metric_name in _RESOURCE_METRIC_FIELDS:
        _nonnegative(evaluation[metric_name], metric_name)

def _gate_index(gate_results: Iterable[dict[str, Any]], protocol: QualityMetricProtocol) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for gate in gate_results:
        record = dict(gate)
        validate_paired_bootstrap_gate_result(record)
        if record["quality_protocol_hash"] != protocol_fingerprint(protocol):
            raise ValueError("Gate quality_protocol_hash 与冻结协议不一致")
        if int(record["replicates"]) != protocol.bootstrap_replicates:
            raise ValueError("Gate Bootstrap replicates 与冻结协议不一致")
        if int(record["seed"]) != protocol.bootstrap_seed:
            raise ValueError("Gate Bootstrap seed 与冻结协议不一致")
        if float(record["confidence_level"]) != protocol.bootstrap_confidence_level:
            raise ValueError("Gate confidence level 与冻结协议不一致")
        if float(record["noninferiority_margin"]) != protocol.noninferiority_margin:
            raise ValueError("Gate 非劣效边界与冻结协议不一致")
        key = (
            str(record["candidate_id"]),
            str(record["comparator_id"]),
            str(record["budget_id"]),
            str(record["comparison_kind"]),
        )
        if key in seen:
            raise ValueError(f"重复 Gate result: {key}")
        seen.add(key)
        rows.append(record)
    return rows


def _fixed_reference_gate(
    gates: list[dict[str, Any]], package_id: str, budget_id: str, reference_id: str
) -> dict[str, Any] | None:
    matches = [
        gate
        for gate in gates
        if gate["candidate_id"] == package_id
        and gate["comparator_id"] == reference_id
        and gate["budget_id"] == budget_id
        and gate["comparison_kind"] == "fixed_reference"
    ]
    if len(matches) > 1:
        raise ValueError(f"固定参考 Gate 不唯一: {package_id} {budget_id}")
    return matches[0] if matches else None


def _champion_gate(
    gates: list[dict[str, Any]], package_id: str, champion_id: str, budget_id: str
) -> dict[str, Any] | None:
    matches = [
        gate
        for gate in gates
        if gate["candidate_id"] == package_id
        and gate["comparator_id"] == champion_id
        and gate["budget_id"] == budget_id
        and gate["comparison_kind"] in {"quality_champion", "candidate_to_champion"}
    ]
    if len(matches) > 1:
        raise ValueError(f"Quality Champion Gate 不唯一: {package_id} {champion_id} {budget_id}")
    return matches[0] if matches else None


def _quality_key(
    package_id: str,
    evaluation_index: dict[tuple[str, str], dict[str, Any]],
    budget_ids: tuple[str, ...],
    datasets: tuple[str, ...],
) -> tuple[Any, ...]:
    evaluations = [evaluation_index[(package_id, budget)] for budget in budget_ids]
    worst_severe = max(float(evaluation["dataset_severe"][dataset]) for evaluation in evaluations for dataset in datasets)
    worst_unsafe = max(float(evaluation["dataset_unsafe_stop"][dataset]) for evaluation in evaluations for dataset in datasets)
    mean_nmae = sum(float(evaluation["macro_nmae"]) for evaluation in evaluations) / len(evaluations)
    mean_qwk = sum(float(evaluation["macro_qwk"]) for evaluation in evaluations) / len(evaluations)
    return (worst_severe, worst_unsafe, mean_nmae, -mean_qwk, package_id)


def _resource_key(
    package_id: str,
    evaluation_index: dict[tuple[str, str], dict[str, Any]],
    budget_ids: tuple[str, ...],
) -> tuple[Any, ...]:
    evaluations = [evaluation_index[(package_id, budget)] for budget in budget_ids]
    count = len(evaluations)
    return (
        sum(float(evaluation["cost_per_paper"]) for evaluation in evaluations) / count,
        sum(float(evaluation["elapsed_time_per_paper"]) for evaluation in evaluations) / count,
        sum(float(evaluation["agent_calls_per_paper"]) for evaluation in evaluations) / count,
        sum(float(evaluation["a2a_exchanges_per_paper"]) for evaluation in evaluations) / count,
        package_id,
    )


@dataclass(frozen=True)
class QualityChampionPreview:
    reference_admission_feasible_ids: tuple[str, ...]
    quality_champion_package_id: str | None
    quality_champion_resource_read_count: int
    rejection_reasons: dict[str, tuple[str, ...]]


def determine_quality_champion_after_reference_admission(
    packages: Iterable[dict[str, Any]],
    evaluations: Iterable[dict[str, Any]],
    fixed_reference_gate_results: Iterable[dict[str, Any]],
    *,
    protocol: QualityMetricProtocol,
    reference_policy_by_budget: dict[str, str],
) -> QualityChampionPreview:
    """在生成候选对冠军 Bootstrap 前，先用正式规则确定唯一质量冠军。"""

    required_budgets = tuple(protocol.budget_ids)
    if set(reference_policy_by_budget) != set(required_budgets):
        raise ValueError("quality reference manifest 必须完整覆盖冻结预算档位")
    expected_protocol_hash = protocol_fingerprint(protocol)
    package_rows = [dict(package) for package in packages if package.get("package_role") == "router_candidate"]
    if not package_rows:
        raise ValueError("Quality Champion preview 没有 Router candidate")
    for package in package_rows:
        validate_policy_package(package, expected_protocol_hash=expected_protocol_hash)
    evaluation_by_key = _evaluation_index(evaluations)
    gates = _gate_index(fixed_reference_gate_results, protocol)
    candidate_ids = tuple(sorted(str(package["package_id"]) for package in package_rows))
    reasons: dict[str, list[str]] = {package_id: [] for package_id in candidate_ids}
    admitted: list[str] = []
    for package_id in candidate_ids:
        package_ok = True
        for budget_id in required_budgets:
            evaluation = evaluation_by_key.get((package_id, budget_id))
            if evaluation is None:
                reasons[package_id].append(f"missing_dev_evaluation:{budget_id}")
                package_ok = False
                continue
            try:
                _validate_evaluation(evaluation, protocol)
            except ValueError as exc:
                reasons[package_id].append(f"invalid_dev_evaluation:{budget_id}:{exc}")
                package_ok = False
            if evaluation.get("budget_feasible") is not True:
                reasons[package_id].append(f"budget_infeasible:{budget_id}")
                package_ok = False
            gate = _fixed_reference_gate(gates, package_id, budget_id, str(reference_policy_by_budget[budget_id]))
            if gate is None or gate.get("quality_feasible") is not True or gate.get("status") != "quality_noninferiority_pass":
                reasons[package_id].append(f"fixed_reference_admission_failed:{budget_id}")
                package_ok = False
        if package_ok:
            admitted.append(package_id)
    champion_evaluations, champion_audit = _quality_champion_evaluation_index(evaluation_by_key)
    champion = (
        min(admitted, key=lambda package_id: _quality_key(package_id, champion_evaluations, required_budgets, protocol.datasets))
        if admitted
        else None
    )
    return QualityChampionPreview(
        reference_admission_feasible_ids=tuple(sorted(admitted)),
        quality_champion_package_id=champion,
        quality_champion_resource_read_count=int(champion_audit["resource_reads"]),
        rejection_reasons={key: tuple(value) for key, value in sorted(reasons.items())},
    )


def select_policy_package(
    packages: Iterable[dict[str, Any]],
    evaluations: Iterable[dict[str, Any]],
    gate_results: Iterable[dict[str, Any]],
    *,
    protocol: QualityMetricProtocol | None = None,
    budget_ids: Iterable[str] | None = None,
    reference_policy_by_budget: dict[str, str] | None = None,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
) -> CheckpointSelectionResult:
    """执行固定参考准入 -> Quality Champion -> 冠军保护 -> 资源词典序。"""

    protocol = protocol or QualityMetricProtocol.formal_v13()
    required_budgets = tuple(budget_ids) if budget_ids is not None else tuple(protocol.budget_ids)
    if required_budgets != tuple(protocol.budget_ids):
        # 允许测试传入与 protocol 相同的显式 tuple；正式运行不得漏预算档位。
        if set(required_budgets) != set(protocol.budget_ids):
            raise ValueError("Dev selector 必须完整覆盖冻结预算档位")
        required_budgets = tuple(protocol.budget_ids)
    expected_protocol_hash = protocol_fingerprint(protocol)

    package_rows = [dict(package) for package in packages]
    for package in package_rows:
        if not str(package.get("package_id", "")).strip() or not str(package.get("package_role", "")).strip():
            raise ValueError("每个 Dev Package 必须包含非空 package_id 与 package_role")
    package_ids = [str(package["package_id"]) for package in package_rows]
    if len(package_ids) != len(set(package_ids)):
        raise ValueError("Policy Package ID 必须唯一")
    package_by_id = {str(package["package_id"]): package for package in package_rows}
    router_candidates: list[dict[str, Any]] = []
    for package in package_rows:
        role = str(package.get("package_role", ""))
        if role == "router_candidate":
            validate_policy_package(package, expected_protocol_hash=expected_protocol_hash)
            router_candidates.append(package)
        elif role not in {"reference", "baseline", "ablation"}:
            raise ValueError(f"未知 Package role: {role}")
    if not router_candidates:
        raise ValueError("Dev selector 没有候选 Router Policy Package")

    for hash_field in (
        "quality_protocol_hash",
        "internal_manifest_hash",
        "quality_reference_manifest_hash",
        "budget_manifest_hash",
        "support_manifest_hash",
    ):
        values = {str(package[hash_field]) for package in router_candidates}
        if len(values) != 1:
            raise ValueError(f"候选 Package 的 {hash_field} 不一致，无法公平比较")

    evaluation_by_key = _evaluation_index(evaluations)
    gates = _gate_index(gate_results, protocol)
    candidate_ids = tuple(sorted(str(package["package_id"]) for package in router_candidates))
    if reference_policy_by_budget is None:
        inferred_references: dict[str, str] = {}
        for budget_id in required_budgets:
            comparators = {
                str(gate["comparator_id"])
                for gate in gates
                if gate["comparison_kind"] == "fixed_reference"
                and gate["budget_id"] == budget_id
                and gate["candidate_id"] in candidate_ids
            }
            if len(comparators) != 1:
                raise ValueError(f"预算 {budget_id} 的冻结固定参考不唯一或缺失: {sorted(comparators)}")
            inferred_references[budget_id] = next(iter(comparators))
        reference_policy_by_budget = inferred_references
    elif set(reference_policy_by_budget) != set(required_budgets):
        raise ValueError("quality reference manifest 必须完整覆盖冻结预算档位")
    rejection_reasons: dict[str, list[str]] = {package_id: [] for package_id in package_ids}
    admitted: list[str] = []

    for package_id in candidate_ids:
        package_ok = True
        for budget_id in required_budgets:
            evaluation = evaluation_by_key.get((package_id, budget_id))
            if evaluation is None:
                rejection_reasons[package_id].append(f"missing_dev_evaluation:{budget_id}")
                package_ok = False
                continue
            try:
                _validate_evaluation(evaluation, protocol)
            except ValueError as exc:
                rejection_reasons[package_id].append(f"invalid_dev_evaluation:{budget_id}:{exc}")
                package_ok = False
            if evaluation.get("budget_feasible") is not True:
                rejection_reasons[package_id].append(f"budget_infeasible:{budget_id}")
                package_ok = False
            gate = _fixed_reference_gate(gates, package_id, budget_id, str(reference_policy_by_budget[budget_id]))
            if gate is None or gate.get("quality_feasible") is not True or gate.get("status") != "quality_noninferiority_pass":
                rejection_reasons[package_id].append(f"fixed_reference_admission_failed:{budget_id}")
                package_ok = False
        if package_ok:
            admitted.append(package_id)

    if not admitted:
        rows = _selection_rows(
            package_rows,
            rejection_reasons,
            admitted=(),
            champion=None,
            protected=(),
            selected=None,
            evaluation_index=evaluation_by_key,
            budget_ids=required_budgets,
            protocol=protocol,
        )
        result = CheckpointSelectionResult(
            status="no_reference_admission_feasible_package",
            reference_admission_feasible_ids=(),
            quality_champion_package_id=None,
            quality_protection_feasible_ids=(),
            selected_package_id=None,
            selected_checkpoint_id=None,
            dev_boundary_update_count=0,
            quality_champion_resource_read_count=0,
            quality_champion_manual_override_count=0,
            selection_rows=tuple(rows),
            freeze_manifest=None,
        )
        if output_dir is not None:
            output = Path(output_dir)
            fieldnames = list(rows[0]) if rows else ["package_id"]
            write_csv(output / "checkpoint_selection.csv", rows, fieldnames, overwrite=overwrite)
        return result

    champion_evaluations, champion_audit = _quality_champion_evaluation_index(evaluation_by_key)
    champion = min(
        admitted,
        key=lambda package_id: _quality_key(package_id, champion_evaluations, required_budgets, protocol.datasets),
    )

    protected: list[str] = [champion]
    for package_id in admitted:
        if package_id == champion:
            continue
        all_pass = True
        for budget_id in required_budgets:
            gate = _champion_gate(gates, package_id, champion, budget_id)
            if gate is None or gate.get("quality_feasible") is not True or gate.get("status") != "quality_noninferiority_pass":
                rejection_reasons[package_id].append(f"quality_champion_protection_failed:{budget_id}")
                all_pass = False
        if all_pass:
            protected.append(package_id)

    selected = min(
        protected,
        key=lambda package_id: _resource_key(package_id, evaluation_by_key, required_budgets),
    )
    selected_package = package_by_id[selected]
    freeze = PolicyFreezeManifest(
        manifest_version="policy_freeze_v1.4",
        selected_package_id=selected,
        selected_checkpoint_id=str(selected_package["checkpoint_id"]),
        quality_champion_package_id=champion,
        budget_ids=required_budgets,
        stop_boundary=float(selected_package["stop_boundary"]),
        package_hash=_package_hash(selected_package),
        quality_protocol_hash=str(selected_package["quality_protocol_hash"]),
        internal_manifest_hash=str(selected_package["internal_manifest_hash"]),
        quality_reference_manifest_hash=str(selected_package["quality_reference_manifest_hash"]),
        budget_manifest_hash=str(selected_package["budget_manifest_hash"]),
        support_manifest_hash=str(selected_package["support_manifest_hash"]),
        dev_boundary_update_count=0,
        quality_champion_manual_override_count=0,
        selection_rule_version="dev_three_layer_selector_v1.4",
    ).to_dict()
    rows = _selection_rows(
        package_rows,
        rejection_reasons,
        admitted=tuple(admitted),
        champion=champion,
        protected=tuple(protected),
        selected=selected,
        evaluation_index=evaluation_by_key,
        budget_ids=required_budgets,
        protocol=protocol,
    )
    result = CheckpointSelectionResult(
        status="selected",
        reference_admission_feasible_ids=tuple(sorted(admitted)),
        quality_champion_package_id=champion,
        quality_protection_feasible_ids=tuple(sorted(protected)),
        selected_package_id=selected,
        selected_checkpoint_id=str(selected_package["checkpoint_id"]),
        dev_boundary_update_count=0,
        quality_champion_resource_read_count=int(champion_audit["resource_reads"]),
        quality_champion_manual_override_count=0,
        selection_rows=tuple(rows),
        freeze_manifest=freeze,
    )
    if output_dir is not None:
        output = Path(output_dir)
        fieldnames = list(rows[0]) if rows else ["package_id"]
        write_csv(output / "checkpoint_selection.csv", rows, fieldnames, overwrite=overwrite)
        write_json(output / "policy_freeze_manifest.json", freeze, overwrite=overwrite)
    return result


def _selection_rows(
    packages: list[dict[str, Any]],
    rejection_reasons: dict[str, list[str]],
    *,
    admitted: tuple[str, ...],
    champion: str | None,
    protected: tuple[str, ...],
    selected: str | None,
    evaluation_index: dict[tuple[str, str], dict[str, Any]],
    budget_ids: tuple[str, ...],
    protocol: QualityMetricProtocol,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for package in sorted(packages, key=lambda row: str(row.get("package_id", ""))):
        package_id = str(package.get("package_id", ""))
        role = str(package.get("package_role", ""))
        quality_key: tuple[Any, ...] | None = None
        resource_key: tuple[Any, ...] | None = None
        if role == "router_candidate" and all((package_id, budget) in evaluation_index for budget in budget_ids):
            try:
                quality_key = _quality_key(package_id, evaluation_index, budget_ids, protocol.datasets)
                resource_key = _resource_key(package_id, evaluation_index, budget_ids)
            except (KeyError, TypeError, ValueError) as exc:
                rejection_reasons.setdefault(package_id, []).append(
                    f"selection_metric_unavailable:{type(exc).__name__}:{exc}"
                )
        if role != "router_candidate":
            rejection_reasons.setdefault(package_id, []).append("role_not_eligible_for_champion_or_final_selection")
        rows.append(
            {
                "package_id": package_id,
                "checkpoint_id": str(package.get("checkpoint_id", "")),
                "package_role": role,
                "reference_admission_feasible": package_id in admitted,
                "quality_champion": package_id == champion,
                "quality_protection_feasible": package_id in protected,
                "selected": package_id == selected,
                "worst_budget_dataset_severe": quality_key[0] if quality_key else "",
                "worst_budget_dataset_unsafe_stop": quality_key[1] if quality_key else "",
                "mean_budget_macro_nmae": quality_key[2] if quality_key else "",
                "mean_budget_macro_qwk": -quality_key[3] if quality_key else "",
                "mean_budget_cost_per_paper": resource_key[0] if resource_key else "",
                "mean_budget_elapsed_time_per_paper": resource_key[1] if resource_key else "",
                "mean_budget_agent_calls_per_paper": resource_key[2] if resource_key else "",
                "mean_budget_a2a_exchanges_per_paper": resource_key[3] if resource_key else "",
                "rejection_reason": ";".join(rejection_reasons.get(package_id, [])),
                "dev_boundary_updates": int(package.get("dev_boundary_updates", 0) or 0),
                "quality_champion_manual_override_count": 0,
            }
        )
    return rows

