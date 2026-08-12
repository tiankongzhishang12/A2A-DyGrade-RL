"""将不同公开评分数据集记录规范化为统一 Item。"""

from __future__ import annotations

import hashlib
from typing import Any

from a2a_dygrade_rl.utils.schemas import Item
from a2a_dygrade_rl.utils.validation import validate_item


FIELD_ALIASES = {
    "item_id": ("item_id", "id", "response_id", "essay_id"),
    "prompt": ("prompt", "question", "question_text", "essay_prompt"),
    "student_answer": ("student_answer", "answer", "response", "essay", "student_response"),
    "reference_answer": ("reference_answer", "reference", "model_answer"),
    "rubric": ("rubric", "scoring_rubric", "criteria"),
    "gold_score": ("gold_score", "score", "label", "domain1_score"),
    "score_min": ("score_min", "min_score"),
    "score_max": ("score_max", "max_score"),
    "prompt_group": ("prompt_group", "prompt_id", "question_id", "essay_set"),
    "subject": ("subject", "domain"),
}


def first_present(record: dict[str, Any], names: tuple[str, ...], default: Any = "") -> Any:
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def stable_id(dataset: str, prompt_group: str, answer: str, fallback: str = "") -> str:
    if fallback:
        return f"{dataset}_{fallback}"
    digest = hashlib.sha1(f"{dataset}\n{prompt_group}\n{answer}".encode("utf-8")).hexdigest()[:16]
    return f"{dataset}_{digest}"


def score_range(score_min: float, score_max: float) -> float:
    """返回单题分数范围 R_i，非法范围直接失败。"""

    value = float(score_max) - float(score_min)
    if value <= 0:
        raise ValueError(f"score_max 必须大于 score_min，当前 R_i={value}")
    return value


def normalized_score_error(pred_score: float, gold_score: float, score_min: float, score_max: float) -> float:
    """按实验设计方案计算归一化评分误差 E_i。"""

    return abs(float(pred_score) - float(gold_score)) / score_range(score_min, score_max)


def normalize_record(record: dict[str, Any], dataset_config: dict[str, Any]) -> dict[str, Any]:
    dataset = str(dataset_config["name"])
    prompt = str(first_present(record, FIELD_ALIASES["prompt"])).strip()
    answer = str(first_present(record, FIELD_ALIASES["student_answer"])).strip()
    prompt_group = str(first_present(record, FIELD_ALIASES["prompt_group"], prompt[:80])).strip()
    item_id = stable_id(dataset, prompt_group, answer, str(first_present(record, FIELD_ALIASES["item_id"])).strip())
    score_min = float(first_present(record, FIELD_ALIASES["score_min"], dataset_config.get("score_min", 0)))
    score_max = float(first_present(record, FIELD_ALIASES["score_max"], dataset_config.get("score_max", 1)))
    schema_version = str(record.get("schema_version") or dataset_config.get("schema_version") or "item_v1")
    scoring_unit = str(record.get("scoring_unit") or dataset_config.get("scoring_unit") or "response")
    scoring_mode = str(record.get("scoring_mode") or dataset_config.get("scoring_mode") or "holistic")
    source_assets = [dict(asset) for asset in (record.get("source_assets") or [])]
    reference_answer = str(first_present(record, FIELD_ALIASES["reference_answer"], ""))
    rubric = str(
        first_present(
            record,
            FIELD_ALIASES["rubric"],
            dataset_config.get("default_rubric", "按数据集原始评分标准评分。"),
        )
    )
    metadata = dict(record.get("metadata") or {})
    metadata.update(
        {
            "prompt_group": prompt_group,
            "source_fields": sorted(record.keys()),
            "prompt_length": len(prompt),
            "answer_length": len(answer),
            "rubric_length": len(rubric),
            "has_reference": bool(reference_answer.strip()),
            "formal_eligible": record.get("formal_eligible", dataset_config.get("formal_eligible", True)),
            "semantic_version": schema_version,
            "scoring_unit": scoring_unit,
            "scoring_mode": scoring_mode,
            "source_asset_count": len(source_assets),
        }
    )
    item = Item(
        item_id=item_id,
        dataset=dataset,
        question_type=str(record.get("question_type") or dataset_config.get("question_type") or "short_answer"),
        subject=str(first_present(record, FIELD_ALIASES["subject"], "")),
        prompt=prompt,
        student_answer=answer,
        reference_answer=reference_answer,
        rubric=rubric,
        gold_score=float(first_present(record, FIELD_ALIASES["gold_score"])),
        score_min=score_min,
        score_max=score_max,
        schema_version=schema_version,
        scoring_unit=scoring_unit,
        scoring_mode=scoring_mode,
        source_assets=source_assets,
        metadata=metadata,
    ).to_dict()
    validate_item(item)
    return item