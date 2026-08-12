"""ASAP-SAS Dataset Semantic V2 loader。"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.asap_resource_catalog import build_asap_resource_catalog
from a2a_dygrade_rl.datasets.dataset_result import DatasetLoadResult, quarantine_record, source_file_record
from a2a_dygrade_rl.datasets.normalize import normalize_record


ASAP_SCORE_RANGES = {
    "1": (0, 3),
    "2": (0, 3),
    "3": (0, 2),
    "4": (0, 2),
    "5": (0, 3),
    "6": (0, 3),
    "7": (0, 2),
    "8": (0, 2),
    "9": (0, 2),
    "10": (0, 2),
}


def _finite_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("非有限数值")
    return number


def load_asap_sas_result(
    dataset_config: dict[str, Any],
    *,
    resources_root: str | Path | None = None,
    overwrite: bool = False,
) -> DatasetLoadResult:
    root = Path(dataset_config["raw_path"])
    result = DatasetLoadResult(dataset=str(dataset_config.get("name", "asap_sas")))
    if not root.exists():
        result.summary["status"] = "missing_raw_root"
        return result.finalize()

    required_sets = [str(value) for value in dataset_config.get("required_essay_sets", ASAP_SCORE_RANGES)]
    catalog = build_asap_resource_catalog(
        root,
        resources_root=resources_root,
        required_essay_sets=required_sets,
        overwrite=overwrite,
    )
    description_path = root / "Data_Set_Descriptions.zip"
    if description_path.exists():
        result.source_files.append(source_file_record(description_path, role="official_prompt_rubric_archive"))
    result.resources.extend(
        asset
        for record in catalog.get("essay_sets", {}).values()
        for asset in record.get("source_assets", [])
    )
    for issue in catalog.get("issues", []):
        result.quarantine.append(
            quarantine_record(
                dataset=result.dataset,
                source_file=description_path.name,
                source_record_id=str(issue.get("essay_set", "dataset_resource")),
                reason=str(issue.get("reason", "resource_catalog_issue")),
                detail=str(issue.get("detail", "")),
            )
        )

    train_candidates = [root / "train_rel_2.tsv", root / "train.tsv"]
    train_path = next((path for path in train_candidates if path.exists()), None)
    if train_path is None:
        result.summary.update(status="missing_training_tsv", resource_catalog=catalog)
        return result.finalize()
    result.source_files.append(source_file_record(train_path, role="scored_student_responses"))

    accepted_by_set: dict[str, int] = {essay_set: 0 for essay_set in required_sets}
    quarantine_by_reason: dict[str, int] = {}
    with train_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required_columns = {"Id", "EssaySet", "Score1", "Score2", "EssayText"}
        missing_columns = sorted(required_columns - set(reader.fieldnames or []))
        if missing_columns:
            result.quarantine.append(
                quarantine_record(
                    dataset=result.dataset,
                    source_file=train_path.name,
                    source_record_id="header",
                    reason="missing_required_columns",
                    detail=",".join(missing_columns),
                )
            )
            result.summary.update(status="invalid_training_header", resource_catalog=catalog)
            return result.finalize()

        for line_number, row in enumerate(reader, start=2):
            source_id = str(row.get("Id", "")).strip() or f"line_{line_number}"
            essay_set = str(row.get("EssaySet", "")).strip()
            reason = ""
            detail = ""
            resource = catalog.get("essay_sets", {}).get(essay_set)
            if essay_set not in ASAP_SCORE_RANGES or essay_set not in required_sets:
                reason, detail = "unsupported_essay_set", essay_set
            elif resource is None:
                reason, detail = "missing_official_prompt_or_rubric", essay_set
            elif not str(row.get("EssayText", "")).strip():
                reason = "missing_student_answer"
            else:
                try:
                    score1 = _finite_float(row.get("Score1"))
                    score2 = _finite_float(row.get("Score2"))
                except (TypeError, ValueError):
                    reason, detail = "invalid_score", f"Score1={row.get('Score1')!r}; Score2={row.get('Score2')!r}"
                else:
                    score_min, score_max = ASAP_SCORE_RANGES[essay_set]
                    if not score_min <= score1 <= score_max:
                        reason, detail = "score1_out_of_range", f"{score1} not in [{score_min}, {score_max}]"
                    elif not score_min <= score2 <= score_max:
                        reason, detail = "score2_out_of_range", f"{score2} not in [{score_min}, {score_max}]"
            if reason:
                result.quarantine.append(
                    quarantine_record(
                        dataset=result.dataset,
                        source_file=train_path.name,
                        source_record_id=source_id,
                        reason=reason,
                        detail=detail,
                    )
                )
                quarantine_by_reason[reason] = quarantine_by_reason.get(reason, 0) + 1
                continue

            assert resource is not None
            score_min, score_max = ASAP_SCORE_RANGES[essay_set]
            score1 = _finite_float(row["Score1"])
            score2 = _finite_float(row["Score2"])
            item = normalize_record(
                {
                    "id": f"semantic_v2_set_{int(essay_set):02d}_{source_id}",
                    "prompt_id": f"asap_sas_set_{int(essay_set):02d}",
                    "prompt": resource["prompt"],
                    "answer": row["EssayText"],
                    "rubric": resource["rubric"],
                    "score": score1,
                    "score_min": score_min,
                    "score_max": score_max,
                    "question_type": dataset_config.get("question_type", "short_answer"),
                    "subject": str(resource.get("subject") or "science"),
                    "schema_version": dataset_config.get("schema_version", "item_semantic_v2"),
                    "scoring_unit": "whole_response",
                    "scoring_mode": "holistic",
                    "source_assets": resource.get("source_assets", []),
                    "formal_eligible": True,
                },
                dataset_config,
            )
            item["metadata"].update(
                {
                    "source_file": train_path.name,
                    "source_record_id": source_id,
                    "source_line_number": line_number,
                    "source_lineage_id": f"{train_path.name}:{source_id}",
                    "essay_set": essay_set,
                    "score1": score1,
                    "score2": score2,
                    "gold_source": "Score1",
                    "gold_transform": "identity",
                    "anchor_mode": "none",
                    "training_materials_used": False,
                    "resource_docx": resource.get("docx_name", ""),
                    "resource_document_sha256": resource.get("document_sha256", ""),
                    "resource_catalog_sha256": catalog.get("catalog_sha256", ""),
                }
            )
            result.items.append(item)
            accepted_by_set[essay_set] = accepted_by_set.get(essay_set, 0) + 1

    result.summary.update(
        {
            "status": "loaded",
            "schema_version": dataset_config.get("schema_version", "item_semantic_v2"),
            "gold_source": "Score1",
            "anchor_mode": "none",
            "training_materials_read_count": 0,
            "required_essay_sets": required_sets,
            "available_essay_sets": sorted(catalog.get("essay_sets", {}), key=int),
            "accepted_by_essay_set": accepted_by_set,
            "quarantine_by_reason": dict(sorted(quarantine_by_reason.items())),
            "resource_catalog_path": catalog.get("catalog_path", ""),
            "resource_catalog_sha256": catalog.get("catalog_sha256", ""),
        }
    )
    return result.finalize()


def load_asap_sas(dataset_config: dict[str, Any]) -> list[dict[str, Any]]:
    """保留历史列表接口；正式 Semantic V2 构建应调用 result 接口并传 resources_root。"""

    return load_asap_sas_result(dataset_config).items