"""严重错分、Extreme Error、Unsafe Stop 与 Deferral 指标。"""

from __future__ import annotations

import math
from typing import Any


INVALID_STATUSES = {
    "deferred",
    "deferral",
    "budget_exhausted",
    "missing_score",
    "illegal_score",
    "parse_failure",
    "missing_active_cache",
    "failed",
    "incomplete",
}


def is_legal_completed_prediction(record: dict[str, Any]) -> bool:
    status = str(record.get("status", "completed")).strip().lower()
    if status in INVALID_STATUSES or record.get("deferred") is True or record.get("completed") is False:
        return False
    if record.get("active_cache_valid", True) is not True:
        return False
    try:
        pred = float(record["pred_score"])
        gold = float(record["gold_score"])
        score_min = float(record["score_min"])
        score_max = float(record["score_max"])
    except (KeyError, TypeError, ValueError):
        return False
    return (
        math.isfinite(pred)
        and math.isfinite(gold)
        and math.isfinite(score_min)
        and math.isfinite(score_max)
        and score_max > score_min
        and score_min <= gold <= score_max
        and score_min <= pred <= score_max
    )


def normalized_gate_error(record: dict[str, Any], invalid_value: float = 1.0) -> float:
    if not is_legal_completed_prediction(record):
        return float(invalid_value)
    return abs(float(record["pred_score"]) - float(record["gold_score"])) / (
        float(record["score_max"]) - float(record["score_min"])
    )


def is_severe(error: float, threshold: float = 0.25) -> bool:
    return float(error) > float(threshold)


def is_extreme(error: float, threshold: float = 0.50) -> bool:
    return float(error) >= float(threshold)


def is_stop(record: dict[str, Any]) -> bool:
    action = record.get("terminal_action", record.get("decision", record.get("action", "")))
    return str(action).strip().upper() in {"STOP", "STOP_ITEM"}


def is_deferral(record: dict[str, Any]) -> bool:
    status = str(record.get("status", "completed")).strip().lower()
    return status in {"deferred", "deferral", "budget_exhausted", "incomplete"} or record.get("deferred") is True


def unsafe_stop_summary(records: list[dict[str, Any]], *, severe_threshold: float = 0.25) -> dict[str, float | int | bool | None]:
    stop_records = [record for record in records if is_stop(record)]
    unsafe_count = sum(is_severe(normalized_gate_error(record), severe_threshold) for record in stop_records)
    stop_count = len(stop_records)
    return {
        "stop_count": stop_count,
        "unsafe_stop_count": unsafe_count,
        "unsafe_stop_rate": unsafe_count / stop_count if stop_count else None,
        "stop_readiness": stop_count > 0,
        "stop_coverage": stop_count / len(records) if records else 0.0,
    }
