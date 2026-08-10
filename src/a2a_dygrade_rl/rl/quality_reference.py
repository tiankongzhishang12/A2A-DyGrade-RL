"""train_calibration 上按预算自动冻结固定质量参考策略。"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.evaluation.quality_protocol import protocol_fingerprint
from a2a_dygrade_rl.utils.io import write_json
from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol


REFERENCE_POLICY_IDS = (
    "Always-Cheap",
    "Always-Mid",
    "Always-Strong",
    "Fixed-Full-Multi-Agent",
)
_RESOURCE_FIELDS = (
    "cost_per_paper",
    "elapsed_time_per_paper",
    "agent_calls_per_paper",
    "a2a_exchanges_per_paper",
)
_PROHIBITED_ROUTER_FIELDS = {
    "checkpoint_id",
    "checkpoint_hash",
    "package_id",
    "calibration_package_hash",
    "dev_rank",
}


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是数值") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值")
    return number


def _validate_hash(value: str, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{label} 必须是64位 SHA-256 hex")
    return normalized


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


def _quality_key(row: dict[str, Any], protocol: QualityMetricProtocol) -> tuple[Any, ...]:
    severe = row.get("dataset_severe", {})
    unsafe = row.get("dataset_unsafe_stop", {})
    if set(severe) != set(protocol.datasets) or set(unsafe) != set(protocol.datasets):
        raise ValueError("reference candidate 必须完整覆盖冻结 datasets")
    worst_severe = max(_bounded(severe[dataset], f"dataset_severe.{dataset}", 0.0, 1.0) for dataset in protocol.datasets)
    worst_unsafe = max(_bounded(unsafe[dataset], f"dataset_unsafe_stop.{dataset}", 0.0, 1.0) for dataset in protocol.datasets)
    macro_nmae = _bounded(row.get("macro_nmae"), "macro_nmae", 0.0, 1.0)
    macro_qwk = _bounded(row.get("macro_qwk"), "macro_qwk", -1.0, 1.0)
    resources = tuple(_nonnegative(row.get(field), field) for field in _RESOURCE_FIELDS)
    return (worst_severe, worst_unsafe, macro_nmae, -macro_qwk, *resources, str(row["policy_id"]))


def select_quality_references(
    candidates: Iterable[dict[str, Any]],
    *,
    protocol: QualityMetricProtocol,
    internal_manifest_hash: str,
    cache_hash: str,
    seed: int,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """只选择固定参考，不读取或排名 Router checkpoint。"""

    internal_hash = _validate_hash(internal_manifest_hash, "internal_manifest_hash")
    resolved_cache_hash = _validate_hash(cache_hash, "cache_hash")
    rows = [dict(row) for row in candidates]
    if not rows:
        raise ValueError("quality reference candidates 不能为空")
    enriched: list[dict[str, Any]] = []
    mapping: dict[str, str] = {}
    failures: dict[str, str] = {}
    seen_candidates: set[tuple[str, str]] = set()

    for row in rows:
        prohibited = sorted(_PROHIBITED_ROUTER_FIELDS & set(row))
        if prohibited:
            raise ValueError(f"quality reference 禁止读取 checkpoint/package 字段: {prohibited}")
        if row.get("split") != "train_calibration":
            raise ValueError("quality reference 只能使用 train_calibration")
        policy_id = str(row.get("policy_id", ""))
        if policy_id not in REFERENCE_POLICY_IDS:
            raise ValueError(f"未预注册 reference policy: {policy_id}")
        budget_id = str(row.get("budget_id", ""))
        if budget_id not in protocol.budget_ids:
            raise ValueError(f"未预注册 budget_id: {budget_id}")
        candidate_key = (policy_id, budget_id)
        if candidate_key in seen_candidates:
            raise ValueError(f"reference candidate 重复 policy/budget: {candidate_key}")
        seen_candidates.add(candidate_key)
        for field in ("quality_metrics_defined", "stop_readiness", "qwk_ready", "budget_feasible"):
            if not isinstance(row.get(field), bool):
                raise ValueError(f"reference candidate {field} 必须是显式布尔值")
        ready = row["quality_metrics_defined"] and row["stop_readiness"] and row["qwk_ready"]
        selection_key = _quality_key(row, protocol) if ready else None
        feasible = ready and row["budget_feasible"]
        output = dict(row)
        output["reference_ready"] = ready
        output["reference_eligible"] = feasible
        output["selection_key"] = list(selection_key) if feasible and selection_key is not None else None
        output["selection_status"] = "eligible" if feasible else "readiness_or_budget_failure"
        enriched.append(output)

    for budget_id in protocol.budget_ids:
        eligible = [row for row in enriched if row["budget_id"] == budget_id and row["reference_eligible"]]
        if not eligible:
            failures[budget_id] = "no_reference_policy_with_quality_stop_qwk_and_budget_readiness"
            continue
        selected = min(eligible, key=lambda row: tuple(row["selection_key"]))
        mapping[budget_id] = str(selected["policy_id"])
        selected["selection_status"] = "selected_reference"

    manifest = {
        "manifest_version": "quality_reference_manifest_v1",
        "split": "train_calibration",
        "budget_to_reference_policy": dict(sorted(mapping.items())),
        "budget_failures": dict(sorted(failures.items())),
        "candidates": sorted(enriched, key=lambda row: (str(row["budget_id"]), str(row["policy_id"]))),
        "quality_protocol_hash": protocol_fingerprint(protocol),
        "internal_manifest_hash": internal_hash,
        "cache_hash": resolved_cache_hash,
        "seed": int(seed),
        "checkpoint_read_count": 0,
        "checkpoint_ranking_count": 0,
    }
    if output_path is not None:
        write_json(output_path, manifest, overwrite=True)
    return manifest
