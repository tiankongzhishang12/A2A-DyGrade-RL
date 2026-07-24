"""Train-only Agent capability profile construction."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from a2a_dygrade_rl.evaluation.metrics_quality import quadratic_weighted_kappa
from a2a_dygrade_rl.router.difficulty import normalized_score_error


CAPABILITY_SCHEMA_VERSION = "agent_capability_v1"


def _item_split(item: dict[str, Any]) -> str:
    return str(item.get("metadata", {}).get("split", ""))


def _round_score(value: float, score_min: float, score_max: float) -> int:
    return int(round(max(score_min, min(score_max, value))))


def _validate_train_inputs(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    difficulty_rows: list[dict[str, Any]],
) -> None:
    item_splits = {_item_split(item) for item in items}
    record_splits = {str(record.get("split", "")) for record in records}
    difficulty_splits = {str(row.get("source_split", "")) for row in difficulty_rows}
    if item_splits != {"train"}:
        raise ValueError(f"Capability profiles require train items, got: {sorted(item_splits)}")
    if record_splits != {"train"}:
        raise ValueError(f"Capability profiles require train cache, got: {sorted(record_splits)}")
    if difficulty_splits != {"train"}:
        raise ValueError(f"Capability profiles require train difficulty rows, got: {sorted(difficulty_splits)}")
    identities = {
        (str(record.get("run_id", "")), str(record.get("execution_mode", "")), bool(record.get("is_fixture")))
        for record in records
    }
    if len(identities) != 1:
        raise ValueError("Capability profiles cannot mix cache runs, execution modes, or fixture states")


def build_capability_profiles(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    difficulty_rows: list[dict[str, Any]],
    low_support_threshold: int = 30,
) -> list[dict[str, Any]]:
    _validate_train_inputs(items, records, difficulty_rows)
    if low_support_threshold < 1:
        raise ValueError("low_support_threshold must be positive")
    items_by_id = {str(item["item_id"]): item for item in items}
    difficulty_by_id = {str(row["item_id"]): str(row["difficulty_label"]) for row in difficulty_rows}
    if set(items_by_id) != set(difficulty_by_id):
        missing = sorted(set(items_by_id) ^ set(difficulty_by_id))[:10]
        raise ValueError(f"Difficulty rows and train items must have identical item IDs, examples: {missing}")

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        item_id = str(record["item_id"])
        item = items_by_id.get(item_id)
        if item is None:
            raise ValueError(f"Capability cache references an item outside the input: {item_id}")
        key = (
            str(record["agent_id"]),
            str(item.get("dataset", "unknown")),
            str(item.get("question_type", "unknown")),
            difficulty_by_id[item_id],
        )
        grouped[key].append({"record": record, "item": item})

    total_by_agent: dict[str, int] = defaultdict(int)
    for key, rows in grouped.items():
        total_by_agent[key[0]] += len(rows)

    profiles: list[dict[str, Any]] = []
    for key in sorted(grouped):
        agent_id, dataset, question_type, difficulty_label = key
        rows = grouped[key]
        successful = [row for row in rows if row["record"].get("status") == "success"]
        if not successful:
            qwk = 0.0
            raw_mae = 1.0
            normalized_mae = 1.0
            cost = latency = token_usage = calibration = 0.0
        else:
            true_scores: list[int] = []
            predicted_scores: list[int] = []
            raw_errors: list[float] = []
            normalized_errors: list[float] = []
            calibration_scores: list[float] = []
            for row in successful:
                item, record = row["item"], row["record"]
                score_min, score_max = float(item["score_min"]), float(item["score_max"])
                gold, prediction = float(item["gold_score"]), float(record["pred_score"])
                normalized_error = normalized_score_error(prediction, gold, score_min, score_max)
                correctness = max(0.0, 1.0 - normalized_error)
                true_scores.append(_round_score(gold, score_min, score_max))
                predicted_scores.append(_round_score(prediction, score_min, score_max))
                raw_errors.append(abs(prediction - gold))
                normalized_errors.append(normalized_error)
                calibration_scores.append(1.0 - abs(float(record["confidence"]) - correctness))
            qwk = quadratic_weighted_kappa(true_scores, predicted_scores)
            raw_mae = sum(raw_errors) / len(raw_errors)
            normalized_mae = sum(normalized_errors) / len(normalized_errors)
            cost = sum(float(row["record"]["cost"]) for row in successful) / len(successful)
            latency = sum(float(row["record"]["latency"]) for row in successful) / len(successful)
            token_usage = sum(int(row["record"]["token_usage"]) for row in successful) / len(successful)
            calibration = sum(calibration_scores) / len(calibration_scores)

        sample_count = len(rows)
        success_count = len(successful)
        failure_rate = (sample_count - success_count) / sample_count
        accuracy = max(0.0, 1.0 - normalized_mae)
        load = sample_count / max(1, total_by_agent[agent_id])
        profiles.append({
            "agent_id": agent_id,
            "dataset": dataset,
            "question_type": question_type,
            "difficulty_label": difficulty_label,
            "qwk": qwk,
            "mae": raw_mae,
            "normalized_mae": normalized_mae,
            "cost": cost,
            "latency": latency,
            "token_usage": token_usage,
            "calibration": calibration,
            "sample_count": sample_count,
            "success_count": success_count,
            "failure_rate": failure_rate,
            "low_support": sample_count < low_support_threshold,
            "source_split": "train",
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "capability_vector": [accuracy, normalized_mae, cost, latency, calibration, load],
            "capability_vector_fields": ["accuracy", "normalized_mae", "cost", "latency", "calibration", "load"],
        })
    return profiles
