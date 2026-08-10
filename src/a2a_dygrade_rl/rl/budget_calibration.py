"""只用 train_calibration 固定 behavior/reference traces 自动产生四维预算档位。"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.utils.io import write_json


FORMAL_BUDGET_IDS = ("Tight", "Medium", "Loose")
_RESOURCE_INPUT_TO_OUTPUT = {
    "cost": "max_cost",
    "elapsed_time": "max_elapsed_time",
    "agent_calls": "max_agent_calls",
    "a2a_exchanges": "max_a2a_exchanges",
}
_PROHIBITED_FIELDS = {"checkpoint_id", "checkpoint_hash", "package_id", "router_id"}


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_hash(value: str, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{label} 必须是64位 SHA-256 hex")
    return normalized


def _finite_nonnegative(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是数值") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} 必须是非负有限数值")
    return number


def _nearest_rank(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("预算分位数缺少观察值")
    if not 0.0 < float(probability) <= 1.0:
        raise ValueError("预算分位数必须位于 (0,1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(float(probability) * len(ordered)))
    return ordered[rank - 1]


def calibrate_budget_tiers(
    observations: Iterable[dict[str, Any]],
    *,
    quantiles: dict[str, float],
    internal_manifest_hash: str,
    cache_hash: str,
    config: dict[str, Any],
    seed: int,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    rows = [dict(row) for row in observations]
    if not rows:
        raise ValueError("budget calibration observations 不能为空")
    if tuple(quantiles) != FORMAL_BUDGET_IDS:
        raise ValueError("预算档位顺序必须固定为 Tight/Medium/Loose")
    probabilities = [float(quantiles[budget]) for budget in FORMAL_BUDGET_IDS]
    if probabilities != [0.25, 0.50, 0.75]:
        raise ValueError("正式预算分位数必须固定为0.25/0.50/0.75")
    if str(config.get("quantile_method", "")) != "nearest_rank":
        raise ValueError("正式预算 quantile_method 必须固定为 nearest_rank")

    values: dict[str, list[float]] = {field: [] for field in _RESOURCE_INPUT_TO_OUTPUT}
    policy_ids: set[str] = set()
    paper_ids: set[str] = set()
    seen_traces: set[tuple[str, str]] = set()
    for row in rows:
        prohibited = sorted(_PROHIBITED_FIELDS & set(row))
        if prohibited:
            raise ValueError(f"budget calibration 禁止读取 checkpoint/router 字段: {prohibited}")
        if row.get("split") != "train_calibration":
            raise ValueError("budget calibration 只能使用 train_calibration")
        policy_id = str(row.get("policy_id", "")).strip()
        paper_id = str(row.get("paper_id", "")).strip()
        if not policy_id or not paper_id:
            raise ValueError("budget calibration 缺少 policy_id 或 paper_id")
        trace_key = (policy_id, paper_id)
        if trace_key in seen_traces:
            raise ValueError(f"budget calibration duplicate policy/paper trace: {trace_key}")
        seen_traces.add(trace_key)
        policy_ids.add(policy_id)
        paper_ids.add(paper_id)
        for field in values:
            values[field].append(_finite_nonnegative(row.get(field), field))

    budgets: dict[str, dict[str, float | int]] = {}
    for budget_id in FORMAL_BUDGET_IDS:
        probability = float(quantiles[budget_id])
        budget: dict[str, float | int] = {}
        for input_field, output_field in _RESOURCE_INPUT_TO_OUTPUT.items():
            selected = _nearest_rank(values[input_field], probability)
            budget[output_field] = int(math.ceil(selected)) if input_field in {"agent_calls", "a2a_exchanges"} else float(selected)
        budgets[budget_id] = budget

    manifest = {
        "manifest_version": "budget_calibration_manifest_v1",
        "split": "train_calibration",
        "budgets": budgets,
        "quantiles": {budget: float(quantiles[budget]) for budget in FORMAL_BUDGET_IDS},
        "quantile_method": "nearest_rank",
        "policy_ids": sorted(policy_ids),
        "paper_count": len(paper_ids),
        "observation_count": len(rows),
        "internal_manifest_hash": _validate_hash(internal_manifest_hash, "internal_manifest_hash"),
        "cache_hash": _validate_hash(cache_hash, "cache_hash"),
        "config_hash": _stable_hash(config),
        "seed": int(seed),
        "checkpoint_read_count": 0,
        "dev_test_read_count": 0,
    }
    if output_path is not None:
        write_json(output_path, manifest, overwrite=True)
    return manifest
