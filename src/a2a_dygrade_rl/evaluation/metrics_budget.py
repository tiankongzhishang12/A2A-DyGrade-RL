"""四维预算耗尽与违规指标。"""

from __future__ import annotations

import math
from typing import Any

from a2a_dygrade_rl.utils.validation import canonical_budget


def budget_violation_rate(violations: list[bool]) -> float:
    if not violations:
        raise ValueError("budget_violation_rate 至少需要一个样本")
    return sum(bool(item) for item in violations) / len(violations)


def budget_exhausted(usage: dict[str, Any], budget: dict[str, Any]) -> bool:
    limits = canonical_budget(budget)
    used = {
        "max_cost": float(usage.get("cost", usage.get("total_cost", 0.0))),
        "max_elapsed_time": float(usage.get("elapsed_time", usage.get("latency", usage.get("total_elapsed_time", 0.0)))),
        "max_agent_calls": int(usage.get("agent_calls", 0)),
        "max_a2a_exchanges": int(usage.get("a2a_exchanges", usage.get("a2a_messages", 0))),
    }
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in used.values()):
        raise ValueError("预算使用量必须为非负有限数值")
    return any(float(used[key]) >= float(limit) for key, limit in limits.items())


def budget_exhaustion_rate(usages: list[dict[str, Any]], budget: dict[str, Any]) -> float:
    if not usages:
        raise ValueError("budget_exhaustion_rate 至少需要一个 Paper")
    return sum(budget_exhausted(usage, budget) for usage in usages) / len(usages)
