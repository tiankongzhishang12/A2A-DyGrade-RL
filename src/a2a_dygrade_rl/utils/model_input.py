"""Model-visible Item projection shared by audits and Agent wrappers."""

from __future__ import annotations

from typing import Any


VISIBLE_ITEM_FIELDS = (
    "item_id",
    "dataset",
    "question_type",
    "subject",
    "prompt",
    "student_answer",
    "reference_answer",
    "rubric",
    "schema_version",
    "scoring_unit",
    "scoring_mode",
    "source_assets",
)

BANNED_MODEL_VISIBLE_KEYS = {
    "gold_score",
    "gold_dimensions",
    "score1",
    "score2",
    "manual_label",
    "hidden_step_labels",
    "hidden_step_errors",
    "raw_total",
    "derived_total",
}


def strip_banned_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_banned_fields(child)
            for key, child in value.items()
            if str(key).lower() not in BANNED_MODEL_VISIBLE_KEYS
        }
    if isinstance(value, list):
        return [strip_banned_fields(child) for child in value]
    return value


def project_model_visible_item(item: dict[str, Any]) -> dict[str, Any]:
    visible = {field: item.get(field, [] if field == "source_assets" else "") for field in VISIBLE_ITEM_FIELDS}
    visible["score_range"] = {"min": float(item["score_min"]), "max": float(item["score_max"])}
    return strip_banned_fields(visible)


def find_banned_keys(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in BANNED_MODEL_VISIBLE_KEYS:
                findings.append(child_path)
            findings.extend(find_banned_keys(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_banned_keys(child, path=f"{path}[{index}]"))
    return findings
