"""冻结 checkpoint 的 train_calibration-only STOP 安全边界校准。"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Iterable

from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol


def _validate_sha256(value: str, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{label} 必须是64位 SHA-256 hex")
    return normalized


def _wilson_upper(unsafe_count: int, support: int, confidence_level: float) -> float:
    if support <= 0:
        return 1.0
    z = NormalDist().inv_cdf(float(confidence_level))
    p = unsafe_count / support
    denominator = 1.0 + z * z / support
    center = p + z * z / (2.0 * support)
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * support)) / support)
    return min(1.0, (center + radius) / denominator)


def calibrate_stop_boundary(
    *,
    checkpoint_id: str,
    checkpoint_hash: str,
    rows: Iterable[dict[str, Any]],
    protocol: QualityMetricProtocol,
    risk_limit: float,
    confidence_level: float,
    min_stops_per_dataset: int,
) -> dict[str, Any]:
    calibration_rows = [dict(row) for row in rows]
    if not calibration_rows:
        raise ValueError("STOP calibration rows 不能为空")
    if {str(row.get("split", "")) for row in calibration_rows} != {"train_calibration"}:
        raise ValueError("STOP boundary 只能使用 train_calibration")
    if not 0.0 < float(risk_limit) < 1.0:
        raise ValueError("risk_limit 必须位于 (0,1)")
    if not 0.5 < float(confidence_level) < 1.0:
        raise ValueError("confidence_level 必须位于 (0.5,1)")
    if int(min_stops_per_dataset) < 1:
        raise ValueError("min_stops_per_dataset 必须为正数")
    checkpoint_id = str(checkpoint_id).strip()
    if not checkpoint_id:
        raise ValueError("checkpoint_id 不能为空")
    resolved_hash = _validate_sha256(checkpoint_hash, "checkpoint_hash")

    normalized_rows: list[dict[str, Any]] = []
    seen_units: set[tuple[str, str, str]] = set()
    for row in calibration_rows:
        dataset = str(row.get("dataset", ""))
        if dataset not in protocol.datasets:
            raise ValueError(f"STOP calibration 遇到未注册 dataset: {dataset}")
        paper_id = str(row.get("paper_id", "")).strip()
        item_id = str(row.get("item_id", "")).strip()
        if not paper_id or not item_id:
            raise ValueError("STOP calibration 缺少 paper_id/item_id")
        unit = (paper_id, item_id, dataset)
        if unit in seen_units:
            raise ValueError(f"STOP calibration 出现重复 Paper/Item/Dataset: {unit}")
        seen_units.add(unit)
        try:
            risk = float(row["predicted_stop_risk"])
            gate_error = float(row["gate_error"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("STOP calibration 缺少合法 predicted_stop_risk/gate_error") from exc
        if not math.isfinite(risk) or not 0.0 <= risk <= 1.0:
            raise ValueError("predicted_stop_risk 必须位于 [0,1]")
        if not math.isfinite(gate_error) or not 0.0 <= gate_error <= 1.0:
            raise ValueError("STOP calibration gate_error 必须位于 [0,1] 且为有限数值")
        normalized_rows.append({
            **row,
            "dataset": dataset,
            "paper_id": paper_id,
            "item_id": item_id,
            "predicted_stop_risk": risk,
            "gate_error": gate_error,
            "unsafe": gate_error > protocol.severe_threshold,
        })

    feasible: list[dict[str, Any]] = []
    thresholds = sorted({float(row["predicted_stop_risk"]) for row in normalized_rows})
    for threshold in thresholds:
        selected = [row for row in normalized_rows if row["predicted_stop_risk"] <= threshold]
        per_dataset: dict[str, dict[str, Any]] = {}
        candidate_ok = True
        worst_ucb = 0.0
        for dataset in protocol.datasets:
            dataset_rows = [row for row in selected if row["dataset"] == dataset]
            support = len(dataset_rows)
            unsafe_count = sum(bool(row["unsafe"]) for row in dataset_rows)
            upper = _wilson_upper(unsafe_count, support, confidence_level)
            per_dataset[dataset] = {
                "stop_count": support,
                "unsafe_stop_count": unsafe_count,
                "unsafe_stop_rate": unsafe_count / support if support else None,
                "ucb": upper,
            }
            worst_ucb = max(worst_ucb, upper)
            if support < int(min_stops_per_dataset) or upper > float(risk_limit):
                candidate_ok = False
        if candidate_ok:
            feasible.append(
                {
                    "threshold": threshold,
                    "coverage": len(selected) / len(normalized_rows),
                    "worst_ucb": worst_ucb,
                    "per_dataset_support": per_dataset,
                }
            )

    common = {
        "checkpoint_id": checkpoint_id,
        "checkpoint_hash": resolved_hash,
        "calibration_split": "train_calibration",
        "risk_limit": float(risk_limit),
        "confidence_level": float(confidence_level),
        "min_stops_per_dataset": int(min_stops_per_dataset),
        "candidate_boundary_count": len(thresholds),
        "feasible_boundary_count": len(feasible),
        "selection_rule": "max_coverage_then_lower_worst_ucb_then_lower_boundary",
        "calibration_no_gradient": True,
        "calibration_no_replay": True,
        "calibration_no_checkpoint_ranking": True,
        "gradient_update_count": 0,
        "replay_write_count": 0,
        "checkpoint_ranking_count": 0,
        "main_method_upgrade_thresholds": {},
    }
    if not feasible:
        return {
            **common,
            "calibration_status": "failure",
            "stop_boundary": None,
            "coverage": 0.0,
            "worst_ucb": None,
            "per_dataset_support": {},
            "failure_reason": "no_safe_stop_boundary",
        }
    selected = min(feasible, key=lambda row: (-row["coverage"], row["worst_ucb"], row["threshold"]))
    return {
        **common,
        "calibration_status": "success",
        "stop_boundary": selected["threshold"],
        "coverage": selected["coverage"],
        "worst_ucb": selected["worst_ucb"],
        "per_dataset_support": selected["per_dataset_support"],
        "failure_reason": "",
    }
