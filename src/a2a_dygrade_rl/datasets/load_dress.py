"""DREsS Dataset Semantic V2 loader。"""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.dataset_result import DatasetLoadResult, quarantine_record, source_file_record
from a2a_dygrade_rl.datasets.load_common import load_dataset
from a2a_dygrade_rl.datasets.normalize import normalize_record


MAIN_FILES = ("DREsS_Std.tsv", "DREsS_New.tsv")
TRAITS = ("content", "organization", "language")
DRESS_RUBRIC = (
    "Score the complete essay on three independent dimensions: Content (0-5), "
    "Organization (0-5), and Language (0-5). The final score is the arithmetic sum "
    "of the three dimension scores, ranging from 0 to 15. No anchor essays are provided."
)


def _finite_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("非有限数值")
    return number


def _prompt_group(prompt: str) -> str:
    digest = hashlib.sha256(" ".join(prompt.lower().split()).encode("utf-8")).hexdigest()[:20]
    return f"dress_prompt_{digest}"


def load_dress_result(dataset_config: dict[str, Any]) -> DatasetLoadResult:
    root = Path(dataset_config["raw_path"])
    result = DatasetLoadResult(dataset=str(dataset_config.get("name", "dress")))
    if not root.exists():
        result.summary["status"] = "missing_raw_root"
        return result.finalize()
    if not any((root / filename).exists() for filename in MAIN_FILES):
        # 历史 fixture 兼容：只有通用 JSONL/CSV 时继续使用通用 loader。
        result.items = load_dataset(dataset_config)
        result.summary.update(status="legacy_generic_loader", anchor_mode="none")
        return result.finalize()

    quarantine_by_reason: dict[str, int] = {}
    raw_total_status_counts: dict[str, int] = {}
    accepted_by_file: dict[str, int] = {}
    for filename in MAIN_FILES:
        path = root / filename
        if not path.exists():
            result.quarantine.append(
                quarantine_record(
                    dataset=result.dataset,
                    source_file=filename,
                    source_record_id="file",
                    reason="missing_main_file",
                    detail=str(path),
                )
            )
            continue
        result.source_files.append(source_file_record(path, role="main_scored_essays"))
        accepted_by_file[filename] = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            required_columns = {"id", "prompt", "essay", *TRAITS, "total"}
            missing_columns = sorted(required_columns - set(reader.fieldnames or []))
            if missing_columns:
                result.quarantine.append(
                    quarantine_record(
                        dataset=result.dataset,
                        source_file=filename,
                        source_record_id="header",
                        reason="missing_required_columns",
                        detail=",".join(missing_columns),
                    )
                )
                continue
            for line_number, row in enumerate(reader, start=2):
                source_id = str(row.get("id", "")).strip() or f"line_{line_number}"
                prompt = str(row.get("prompt", "")).strip()
                essay = str(row.get("essay", "")).strip()
                reason = ""
                detail = ""
                if not str(row.get("id", "")).strip():
                    reason = "missing_source_record_id"
                elif not prompt:
                    reason = "missing_prompt"
                elif not essay:
                    reason = "missing_student_essay"
                else:
                    dimensions: dict[str, float] = {}
                    try:
                        dimensions = {trait: _finite_float(row.get(trait)) for trait in TRAITS}
                    except (TypeError, ValueError):
                        reason, detail = "invalid_dimension_score", repr({trait: row.get(trait) for trait in TRAITS})
                    else:
                        invalid = {trait: score for trait, score in dimensions.items() if not 0.0 <= score <= 5.0}
                        if invalid:
                            reason, detail = "dimension_score_out_of_range", repr(invalid)
                if reason:
                    result.quarantine.append(
                        quarantine_record(
                            dataset=result.dataset,
                            source_file=filename,
                            source_record_id=source_id,
                            reason=reason,
                            detail=detail,
                        )
                    )
                    quarantine_by_reason[reason] = quarantine_by_reason.get(reason, 0) + 1
                    continue

                dimensions = {trait: _finite_float(row[trait]) for trait in TRAITS}
                derived_total = sum(dimensions.values())
                raw_total_text = str(row.get("total", "")).strip()
                if not raw_total_text:
                    raw_total = None
                    raw_total_status = "missing"
                else:
                    try:
                        raw_total = _finite_float(raw_total_text)
                    except (TypeError, ValueError):
                        raw_total = None
                        raw_total_status = "invalid"
                    else:
                        raw_total_status = "match" if abs(raw_total - derived_total) <= 1e-6 else "conflict"
                raw_total_status_counts[raw_total_status] = raw_total_status_counts.get(raw_total_status, 0) + 1
                source = str(row.get("source") or path.stem).strip()
                item = normalize_record(
                    {
                        "id": f"semantic_v2_{path.stem}_{source_id}",
                        "prompt_id": _prompt_group(prompt),
                        "prompt": prompt,
                        "answer": essay,
                        "rubric": DRESS_RUBRIC,
                        "score": derived_total,
                        "score_min": 0,
                        "score_max": 15,
                        "question_type": dataset_config.get("question_type", "essay"),
                        "subject": "writing",
                        "schema_version": dataset_config.get("schema_version", "item_semantic_v2"),
                        "scoring_unit": "whole_response",
                        "scoring_mode": "analytic_three_dimension",
                        "source_assets": [],
                        "formal_eligible": True,
                    },
                    dataset_config,
                )
                item["metadata"].update(
                    {
                        "source_file": filename,
                        "source_record_id": source_id,
                        "source_line_number": line_number,
                        "source_lineage_id": f"{filename}:{source_id}",
                        "source": source,
                        "gold_dimensions": dimensions,
                        "gold_source": "content_plus_organization_plus_language",
                        "gold_transform": "dimension_sum",
                        "derived_total": derived_total,
                        "raw_total": raw_total,
                        "raw_total_status": raw_total_status,
                        "anchor_mode": "none",
                        "scoring_dimensions": ["content", "organization", "language"],
                    }
                )
                result.items.append(item)
                accepted_by_file[filename] += 1

    result.summary.update(
        {
            "status": "loaded",
            "schema_version": dataset_config.get("schema_version", "item_semantic_v2"),
            "main_files": list(MAIN_FILES),
            "case_file_read_count": 0,
            "anchor_mode": "none",
            "gold_source": "content_plus_organization_plus_language",
            "accepted_by_file": accepted_by_file,
            "quarantine_by_reason": dict(sorted(quarantine_by_reason.items())),
            "raw_total_status_counts": dict(sorted(raw_total_status_counts.items())),
        }
    )
    return result.finalize()


def load_dress(dataset_config: dict[str, Any]) -> list[dict[str, Any]]:
    return load_dress_result(dataset_config).items