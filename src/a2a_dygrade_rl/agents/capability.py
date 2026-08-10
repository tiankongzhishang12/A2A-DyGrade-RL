"""Agent capability profile：train_fit 拟合主体，train_calibration 只校准支持度边界。"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.evaluation.metrics_quality import quadratic_weighted_kappa_details
from a2a_dygrade_rl.evaluation.qwk_readiness import score_to_fixed_bin
from a2a_dygrade_rl.router.difficulty import normalized_score_error
from a2a_dygrade_rl.utils.io import write_json
from a2a_dygrade_rl.utils.validation import validate_agent_output


CAPABILITY_SCHEMA_VERSION = "agent_capability_v1"
FORMAL_CAPABILITY_MANIFEST_VERSION = "agent_capability_manifest_v1"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_sha256(value: str, label: str) -> str:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"{label} 必须是64位 SHA-256 hex")
    return normalized


def _item_split(item: dict[str, Any]) -> str:
    return str(item.get("metadata", {}).get("split", ""))


def _validate_inputs_for_split(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    difficulty_rows: list[dict[str, Any]],
    *,
    expected_split: str,
    allow_fixture: bool,
) -> None:
    item_splits = {_item_split(item) for item in items}
    record_splits = {str(record.get("split", "")) for record in records}
    difficulty_splits = {str(row.get("source_split", "")) for row in difficulty_rows}
    if item_splits != {expected_split}:
        raise ValueError(f"Capability profiles require {expected_split} items, got: {sorted(item_splits)}")
    if record_splits != {expected_split}:
        raise ValueError(f"Capability profiles require {expected_split} cache, got: {sorted(record_splits)}")
    if difficulty_splits != {expected_split}:
        raise ValueError(f"Capability profiles require {expected_split} difficulty rows, got: {sorted(difficulty_splits)}")
    for record in records:
        validate_agent_output(record)
    identities = {
        (str(record.get("run_id", "")), str(record.get("execution_mode", "")), record.get("is_fixture"))
        for record in records
    }
    if len(identities) != 1:
        raise ValueError("Capability profiles cannot mix cache runs, execution modes, or fixture states")
    fixture_item_ids = [
        str(item.get("item_id", ""))
        for item in items
        if item.get("metadata", {}).get("fixture") is True
        or item.get("metadata", {}).get("is_fixture") is True
        or item.get("metadata", {}).get("formal_eligible") is False
    ]
    fixture_record_ids = [
        str(record.get("item_id", ""))
        for record in records
        if record.get("is_fixture") is True
        or record.get("execution_mode") == "fixture_smoke"
        or record.get("formal_eligible") is False
    ]
    if (fixture_item_ids or fixture_record_ids) and not allow_fixture:
        examples = sorted(set(fixture_item_ids + fixture_record_ids))[:10]
        raise ValueError(f"Fixture Item/cache 不得进入 Formal capability 流水线: {examples}")
    if not allow_fixture and {identity[1] for identity in identities} != {"formal_experiment"}:
        raise ValueError("Formal capability 只接受 formal_experiment cache")
    if not allow_fixture and {identity[2] for identity in identities} != {False}:
        raise ValueError("Formal capability 只接受 is_fixture=false 的 cache")


def _build_profiles(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    difficulty_rows: list[dict[str, Any]],
    *,
    source_split: str,
    low_support_threshold: int,
    allow_fixture: bool,
) -> list[dict[str, Any]]:
    _validate_inputs_for_split(items, records, difficulty_rows, expected_split=source_split, allow_fixture=allow_fixture)
    if low_support_threshold < 1:
        raise ValueError("low_support_threshold must be positive")
    items_by_id = {str(item["item_id"]): item for item in items}
    difficulty_by_id = {str(row["item_id"]): str(row["difficulty_label"]) for row in difficulty_rows}
    if set(items_by_id) != set(difficulty_by_id):
        missing = sorted(set(items_by_id) ^ set(difficulty_by_id))[:10]
        raise ValueError(f"Difficulty rows and items must have identical item IDs, examples: {missing}")

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
            qwk_defined = False
            raw_mae = normalized_mae = 1.0
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
                true_scores.append(score_to_fixed_bin(gold, score_min, score_max))
                predicted_scores.append(score_to_fixed_bin(prediction, score_min, score_max))
                raw_errors.append(abs(prediction - gold))
                normalized_errors.append(normalized_error)
                calibration_scores.append(1.0 - abs(float(record["confidence"]) - correctness))
            qwk_result = quadratic_weighted_kappa_details(true_scores, predicted_scores)
            qwk_defined = qwk_result.qwk is not None
            qwk = qwk_result.qwk if qwk_defined else 0.0
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
            "qwk_defined": qwk_defined,
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
            "source_split": source_split,
            "schema_version": CAPABILITY_SCHEMA_VERSION,
            "capability_vector": [accuracy, normalized_mae, cost, latency, calibration, load],
            "capability_vector_fields": ["accuracy", "normalized_mae", "cost", "latency", "calibration", "load"],
        })
    return profiles


def build_capability_profiles(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    difficulty_rows: list[dict[str, Any]],
    low_support_threshold: int = 30,
) -> list[dict[str, Any]]:
    """Legacy train-only fixture 接口。"""
    return _build_profiles(
        items,
        records,
        difficulty_rows,
        source_split="train",
        low_support_threshold=low_support_threshold,
        allow_fixture=True,
    )


def build_formal_capability_profiles(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    difficulty_rows: list[dict[str, Any]],
    low_support_threshold: int = 30,
    *,
    allow_fixture: bool = False,
) -> list[dict[str, Any]]:
    """正式画像主体只能由 train_fit 拟合。"""
    return _build_profiles(
        items,
        records,
        difficulty_rows,
        source_split="train_fit",
        low_support_threshold=low_support_threshold,
        allow_fixture=allow_fixture,
    )


def _nearest_rank(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("capability support calibration 缺少支持度")
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(float(probability) * len(ordered)))
    return ordered[rank - 1]


def calibrate_capability_support(
    profiles: list[dict[str, Any]],
    calibration_items: list[dict[str, Any]],
    calibration_records: list[dict[str, Any]],
    calibration_difficulty_rows: list[dict[str, Any]],
    *,
    support_quantile: float,
    internal_manifest_hash: str,
    cache_hash: str,
    seed: int,
    output_path: str | Path | None = None,
    allow_fixture: bool = False,
) -> dict[str, Any]:
    if not profiles or {str(row.get("source_split", "")) for row in profiles} != {"train_fit"}:
        raise ValueError("能力画像主体必须来自 train_fit")
    prohibited = {"best_agent", "oracle_agent", "optimal_agent", "item_level_best_agent"}
    if any(prohibited & set(row) for row in profiles):
        raise ValueError("能力画像不得包含 Item 级 oracle Agent 标签")
    if not 0.0 < float(support_quantile) <= 1.0:
        raise ValueError("support_quantile 必须位于 (0,1]")
    _validate_inputs_for_split(
        calibration_items,
        calibration_records,
        calibration_difficulty_rows,
        expected_split="train_calibration",
        allow_fixture=allow_fixture,
    )
    item_by_id = {str(item["item_id"]): item for item in calibration_items}
    difficulty_by_id = {str(row["item_id"]): str(row["difficulty_label"]) for row in calibration_difficulty_rows}
    grouped: dict[tuple[str, str, str, str], int] = defaultdict(int)
    for record in calibration_records:
        item_id = str(record["item_id"])
        if item_id not in item_by_id or item_id not in difficulty_by_id:
            raise ValueError(f"calibration cache/difficulty 引用未知 Item: {item_id}")
        item = item_by_id[item_id]
        key = (
            str(record["agent_id"]),
            str(item["dataset"]),
            str(item["question_type"]),
            difficulty_by_id[item_id],
        )
        grouped[key] += 1
    counts = list(grouped.values())
    support_boundary = int(_nearest_rank([float(value) for value in counts], float(support_quantile)))
    uncertainties = [1.0 / math.sqrt(value) for value in counts]
    uncertainty_boundary = _nearest_rank(uncertainties, 1.0 - float(support_quantile) + 1e-12)
    manifest = {
        "manifest_version": FORMAL_CAPABILITY_MANIFEST_VERSION,
        "fit_split": "train_fit",
        "calibration_split": "train_calibration",
        "support_quantile": float(support_quantile),
        "quantile_method": "nearest_rank",
        "low_support_count_boundary": support_boundary,
        "uncertainty_boundary": uncertainty_boundary,
        "fit_profile_hash": _stable_hash(profiles),
        "calibration_support_hash": _stable_hash({"groups": sorted((list(key), value) for key, value in grouped.items())}),
        "internal_manifest_hash": _validate_sha256(internal_manifest_hash, "internal_manifest_hash"),
        "cache_hash": _validate_sha256(cache_hash, "cache_hash"),
        "seed": int(seed),
        "calibration_no_gradient": True,
        "calibration_gradient_updates": 0,
        "no_item_oracle_labels": True,
        "profile_count": len(profiles),
        "calibration_group_count": len(grouped),
    }
    if output_path is not None:
        write_json(output_path, manifest, overwrite=True)
    return manifest
