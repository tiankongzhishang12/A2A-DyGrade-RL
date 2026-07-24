"""小规模机制验证：使用 train fixture cache 评价静态与置信度路由策略。"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from a2a_dygrade_rl.evaluation.metrics_quality import quadratic_weighted_kappa


@dataclass(frozen=True)
class PolicyResult:
    method: str
    split: str
    sample_count: int
    normalized_mae: float
    normalized_qwk: float
    total_cost: float
    mean_cost: float
    mean_latency: float
    upgrade_rate: float
    threshold: float | None = None


def load_agent_cache(cache_dir: Path, agent_ids: Iterable[str]) -> dict[str, dict[str, dict]]:
    """按 Agent 和 item_id 加载成功的缓存记录，并验证共同样本集合。"""
    caches: dict[str, dict[str, dict]] = {}
    for agent_id in agent_ids:
        path = cache_dir / f"{agent_id}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"缺少 Agent cache：{path}")
        records: dict[str, dict] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("status", "success") == "success":
                    records[row["item_id"]] = row
        caches[agent_id] = records
    item_sets = [set(records) for records in caches.values()]
    if not item_sets or not set.intersection(*item_sets):
        raise ValueError("Agent cache 没有共同样本")
    if any(items != item_sets[0] for items in item_sets[1:]):
        raise ValueError("不同 Agent cache 的 item_id 集合不一致")
    return caches


def deterministic_partition(item_ids: Iterable[str], calibration_fraction: float = 0.5) -> tuple[list[str], list[str]]:
    """仅依据 item_id 哈希进行可复现拆分，不使用 gold score。"""
    ordered = sorted(item_ids, key=lambda item_id: hashlib.sha256(item_id.encode("utf-8")).hexdigest())
    cut = max(1, min(len(ordered) - 1, round(len(ordered) * calibration_fraction)))
    return ordered[:cut], ordered[cut:]


def _normalized_score(row: dict, key: str) -> float:
    metadata = row["metadata"]
    low = float(metadata["score_min"])
    high = float(metadata["score_max"])
    if high <= low:
        raise ValueError(f"非法分数范围：{low}..{high}")
    return (float(row[key]) - low) / (high - low)


def evaluate_selections(
    method: str,
    split: str,
    item_ids: list[str],
    caches: dict[str, dict[str, dict]],
    selections: dict[str, str],
    threshold: float | None = None,
) -> PolicyResult:
    truths: list[int] = []
    predictions: list[int] = []
    absolute_errors: list[float] = []
    costs: list[float] = []
    latencies: list[float] = []
    upgrades = 0
    for item_id in item_ids:
        agent_id = selections[item_id]
        row = caches[agent_id][item_id]
        gold = _normalized_score(row, "gold_score")
        pred = min(1.0, max(0.0, _normalized_score(row, "pred_score")))
        truths.append(round(gold * 10))
        predictions.append(round(pred * 10))
        absolute_errors.append(abs(gold - pred))
        costs.append(float(row["cost"]))
        latencies.append(float(row["latency"]))
        upgrades += int(agent_id != "CheapAgent")
    return PolicyResult(
        method=method,
        split=split,
        sample_count=len(item_ids),
        normalized_mae=sum(absolute_errors) / len(absolute_errors),
        normalized_qwk=quadratic_weighted_kappa(truths, predictions),
        total_cost=sum(costs),
        mean_cost=sum(costs) / len(costs),
        mean_latency=sum(latencies) / len(latencies),
        upgrade_rate=upgrades / len(item_ids),
        threshold=threshold,
    )


def static_policy(agent_id: str, item_ids: list[str]) -> dict[str, str]:
    return {item_id: agent_id for item_id in item_ids}


def confidence_policy(
    item_ids: list[str],
    caches: dict[str, dict[str, dict]],
    threshold: float,
    fallback_agent: str = "MidAgent",
) -> dict[str, str]:
    return {
        item_id: ("CheapAgent" if float(caches["CheapAgent"][item_id]["confidence"]) >= threshold else fallback_agent)
        for item_id in item_ids
    }


def oracle_policy(
    item_ids: list[str], caches: dict[str, dict[str, dict]], agent_ids: Iterable[str]
) -> dict[str, str]:
    """使用 gold 选择逐题最优 Agent，仅用于估计路由潜力上界，不能部署。"""
    selections: dict[str, str] = {}
    for item_id in item_ids:
        selections[item_id] = min(
            agent_ids,
            key=lambda agent_id: (
                abs(
                    _normalized_score(caches[agent_id][item_id], "gold_score")
                    - _normalized_score(caches[agent_id][item_id], "pred_score")
                ),
                float(caches[agent_id][item_id]["cost"]),
            ),
        )
    return selections

def select_threshold(
    calibration_ids: list[str],
    caches: dict[str, dict[str, dict]],
    thresholds: Iterable[float],
    cost_weight: float,
) -> tuple[float, list[dict]]:
    """在 calibration 子集上最小化 normalized MAE + cost_weight * mean cost。"""
    trials: list[dict] = []
    for threshold in thresholds:
        result = evaluate_selections(
            method="Confidence Router",
            split="calibration",
            item_ids=calibration_ids,
            caches=caches,
            selections=confidence_policy(calibration_ids, caches, threshold),
            threshold=threshold,
        )
        objective = result.normalized_mae + cost_weight * result.mean_cost
        trials.append({**result.__dict__, "objective": objective, "cost_weight": cost_weight})
    best = min(trials, key=lambda row: (row["objective"], row["mean_cost"], row["threshold"]))
    return float(best["threshold"]), trials


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

