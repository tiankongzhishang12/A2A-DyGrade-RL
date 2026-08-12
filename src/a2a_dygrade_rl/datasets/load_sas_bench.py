"""SAS-Bench Dataset Semantic V2 whole-response loader。"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.dataset_result import DatasetLoadResult, quarantine_record, source_file_record
from a2a_dygrade_rl.datasets.normalize import normalize_record


WHOLE_RESPONSE_RUBRIC = (
    "Evaluate the student's complete response against the question, reference answer, and solution analysis. "
    "Assign one holistic score on the original 0-to-total scale. Do not grade or expose individual step labels."
)


def _question_type_from_name(path: Path) -> str:
    name = path.name.lower()
    if "choice" in name:
        return "choice"
    if "gapfilling" in name:
        return "gap_filling"
    return "short_answer"


def _subject_from_name(path: Path) -> str:
    base = path.name.split(".translated.jsonl", 1)[0]
    parts = base.split("_")
    return parts[1] if len(parts) > 1 else ""


def _finite_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("非有限数值")
    return number


def _prompt_group(subject: str, question: str) -> str:
    normalized = " ".join(question.lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"sas_bench_{subject.lower()}_{digest}"


def _read_indexed_jsonl(
    path: Path,
    *,
    dataset: str,
    role: str,
    quarantine: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, int], set[str]]:
    records: dict[str, dict[str, Any]] = {}
    line_numbers: dict[str, int] = {}
    duplicates: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                quarantine.append(
                    quarantine_record(
                        dataset=dataset,
                        source_file=path.name,
                        source_record_id=f"line_{line_number}",
                        reason=f"invalid_{role}_json",
                        detail=str(exc),
                    )
                )
                continue
            if not isinstance(parsed, dict):
                quarantine.append(
                    quarantine_record(
                        dataset=dataset,
                        source_file=path.name,
                        source_record_id=str(parsed)[:120] or f"line_{line_number}",
                        reason=f"invalid_{role}_record_type",
                        detail=type(parsed).__name__,
                    )
                )
                continue
            record_id = str(parsed.get("id", "")).strip()
            if not record_id:
                quarantine.append(
                    quarantine_record(
                        dataset=dataset,
                        source_file=path.name,
                        source_record_id=f"line_{line_number}",
                        reason=f"missing_{role}_record_id",
                    )
                )
                continue
            if record_id in records:
                duplicates.add(record_id)
                quarantine.append(
                    quarantine_record(
                        dataset=dataset,
                        source_file=path.name,
                        source_record_id=record_id,
                        reason=f"duplicate_{role}_record_id",
                        detail=f"lines={line_numbers[record_id]},{line_number}",
                    )
                )
                continue
            records[record_id] = parsed
            line_numbers[record_id] = line_number
    for duplicate in duplicates:
        records.pop(duplicate, None)
        line_numbers.pop(duplicate, None)
    return records, line_numbers, duplicates


def _annotation_filename(translated_path: Path) -> str:
    suffix = ".translated.jsonl"
    return translated_path.name[: -len(suffix)] + ".jsonl" if translated_path.name.endswith(suffix) else translated_path.name


def load_sas_bench_result(dataset_config: dict[str, Any]) -> DatasetLoadResult:
    root = Path(dataset_config["raw_path"])
    annotation_root = Path(dataset_config.get("annotation_raw_path") or (root.parent / "datasets"))
    pattern = str(dataset_config.get("pattern", "*.translated.jsonl"))
    result = DatasetLoadResult(dataset=str(dataset_config.get("name", "sas_bench")))
    if not root.exists():
        result.summary["status"] = "missing_english_raw_root"
        return result.finalize()
    if not annotation_root.exists():
        result.summary["status"] = "missing_annotation_raw_root"
        return result.finalize()

    accepted_by_file: dict[str, int] = {}
    aligned_file_count = 0
    english_paths = sorted(root.glob(pattern))
    for english_path in english_paths:
        annotation_path = annotation_root / _annotation_filename(english_path)
        result.source_files.append(source_file_record(english_path, role="english_model_visible_text"))
        accepted_by_file[english_path.name] = 0
        if not annotation_path.exists():
            result.quarantine.append(
                quarantine_record(
                    dataset=result.dataset,
                    source_file=english_path.name,
                    source_record_id="file",
                    reason="missing_annotation_source_file",
                    detail=str(annotation_path),
                )
            )
            continue
        aligned_file_count += 1
        result.source_files.append(source_file_record(annotation_path, role="authoritative_numeric_labels"))
        english_records, english_lines, _ = _read_indexed_jsonl(
            english_path,
            dataset=result.dataset,
            role="english",
            quarantine=result.quarantine,
        )
        annotations, annotation_lines, _ = _read_indexed_jsonl(
            annotation_path,
            dataset=result.dataset,
            role="annotation",
            quarantine=result.quarantine,
        )

        for record_id, english in english_records.items():
            annotation = annotations.get(record_id)
            reason = ""
            detail = ""
            response_parts: list[str] = []
            step_labels: list[float] = []
            step_errors: list[Any] = []
            total = 0.0
            manual_label = 0.0
            if annotation is None:
                reason = "missing_aligned_annotation_record"
            else:
                question = str(english.get("question", "")).strip()
                english_steps = english.get("steps")
                annotation_steps = annotation.get("steps")
                if not question:
                    reason = "missing_question_text"
                elif not isinstance(english_steps, list) or not english_steps:
                    reason = "missing_english_steps"
                elif not isinstance(annotation_steps, list) or not annotation_steps:
                    reason = "missing_annotation_steps"
                elif len(english_steps) != len(annotation_steps):
                    reason, detail = "step_count_mismatch", f"english={len(english_steps)} annotation={len(annotation_steps)}"
                else:
                    try:
                        total = _finite_float(annotation.get("total"))
                        manual_label = _finite_float(annotation.get("manual_label"))
                    except (TypeError, ValueError):
                        reason, detail = "invalid_total_or_manual_label", (
                            f"total={annotation.get('total')!r}; manual_label={annotation.get('manual_label')!r}"
                        )
                    else:
                        if total <= 0:
                            reason, detail = "nonpositive_total_score", str(total)
                        elif not 0.0 <= manual_label <= total:
                            reason, detail = "manual_label_out_of_range", f"{manual_label} not in [0,{total}]"
                if not reason:
                    assert isinstance(english_steps, list) and isinstance(annotation_steps, list)
                    for step_index, (english_step, annotation_step) in enumerate(
                        zip(english_steps, annotation_steps, strict=True), start=1
                    ):
                        if not isinstance(english_step, dict) or not isinstance(annotation_step, dict):
                            reason, detail = "invalid_step_record_type", f"step={step_index}"
                            break
                        response = str(english_step.get("response", "")).strip()
                        try:
                            label = _finite_float(annotation_step.get("label"))
                        except (TypeError, ValueError):
                            reason, detail = "invalid_step_label", f"step={step_index} value={annotation_step.get('label')!r}"
                            break
                        if not response and label != 0.0:
                            reason, detail = "empty_step_with_nonzero_label", f"step={step_index} label={label}"
                            break
                        step_labels.append(label)
                        step_errors.append(annotation_step.get("errors", []))
                        if response:
                            response_parts.append(f"[Step {step_index}]\n{response}")
                    if not reason and not response_parts:
                        reason = "empty_whole_response"
                    if not reason and abs(sum(step_labels) - manual_label) > 1e-6:
                        reason, detail = "manual_label_step_sum_mismatch", (
                            f"manual_label={manual_label}; step_sum={sum(step_labels)}"
                        )
            if reason:
                result.quarantine.append(
                    quarantine_record(
                        dataset=result.dataset,
                        source_file=english_path.name,
                        source_record_id=record_id,
                        reason=reason,
                        detail=detail,
                    )
                )
                continue

            assert annotation is not None
            question = str(english["question"]).strip()
            reference = str(english.get("reference", "")).strip()
            analysis = str(english.get("analysis", "")).strip()
            reference_answer = reference
            if analysis:
                reference_answer = f"{reference}\n\nSolution analysis:\n{analysis}".strip()
            subject = _subject_from_name(english_path)
            item = normalize_record(
                {
                    "id": f"semantic_v2_{record_id}",
                    "prompt_id": _prompt_group(subject, question),
                    "prompt": question,
                    "answer": "\n\n".join(response_parts),
                    "reference": reference_answer,
                    "rubric": f"{WHOLE_RESPONSE_RUBRIC} Maximum score: {total:g}.",
                    "score": manual_label,
                    "score_min": 0,
                    "score_max": total,
                    "question_type": _question_type_from_name(english_path),
                    "subject": subject,
                    "schema_version": dataset_config.get("schema_version", "item_semantic_v2"),
                    "scoring_unit": "whole_response",
                    "scoring_mode": "holistic_total_score",
                    "source_assets": [],
                    "formal_eligible": True,
                },
                dataset_config,
            )
            item["metadata"].update(
                {
                    "source_file": english_path.name,
                    "annotation_source_file": annotation_path.name,
                    "source_record_id": record_id,
                    "source_line_number": english_lines[record_id],
                    "annotation_line_number": annotation_lines[record_id],
                    "source_lineage_id": f"{english_path.name}:{record_id}",
                    "question_id": record_id,
                    "scoring_unit": "whole_response",
                    "manual_label": manual_label,
                    "source_total": total,
                    "gold_source": "manual_label",
                    "gold_transform": "identity",
                    "hidden_step_labels": step_labels,
                    "hidden_step_errors": step_errors,
                    "source_step_count": len(step_labels),
                    "visible_nonempty_step_count": len(response_parts),
                    "translated_numeric_labels_used": False,
                    "anchor_mode": "none",
                }
            )
            result.items.append(item)
            accepted_by_file[english_path.name] += 1

        for record_id in sorted(set(annotations) - set(english_records)):
            result.quarantine.append(
                quarantine_record(
                    dataset=result.dataset,
                    source_file=annotation_path.name,
                    source_record_id=record_id,
                    reason="annotation_without_english_record",
                    detail=f"line={annotation_lines.get(record_id, '')}",
                )
            )

    structural_counts: dict[str, int] = {}
    for row in result.quarantine:
        reason = str(row.get("reason", ""))
        structural_counts[reason] = structural_counts.get(reason, 0) + 1

    result.summary.update(
        {
            "status": "loaded",
            "schema_version": dataset_config.get("schema_version", "item_semantic_v2"),
            "scoring_unit": "whole_response",
            "gold_source": "manual_label",
            "english_file_count": len(english_paths),
            "aligned_file_count": aligned_file_count,
            "accepted_by_file": accepted_by_file,
            "quarantine_by_reason": dict(sorted(structural_counts.items())),
        }
    )
    return result.finalize()


def load_sas_bench(dataset_config: dict[str, Any]) -> list[dict[str, Any]]:
    return load_sas_bench_result(dataset_config).items