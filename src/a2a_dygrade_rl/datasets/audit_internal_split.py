"""V1.4 内部 Item split 与重建 Paper 的阻塞性审计。"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.datasets.internal_split import INTERNAL_SPLITS
from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_csv, read_jsonl, write_csv
from a2a_dygrade_rl.utils.validation import (
    validate_internal_item_split_manifest,
    validate_internal_paper_manifest_record,
    validate_leftover_record,
)


@dataclass(frozen=True)
class InternalSplitAuditResult:
    passed: bool
    summary: dict[str, Any]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    distribution_rows: tuple[dict[str, Any], ...]


def _quota_matches(counts: Counter[str], strict_quotas: tuple[dict[str, int], ...]) -> bool:
    return any(all(counts.get(dataset, 0) == count for dataset, count in quota.items()) and sum(counts.values()) == sum(quota.values()) for quota in strict_quotas)


def audit_internal_split(
    *,
    items: Iterable[dict[str, Any]],
    item_manifest_rows: list[dict[str, Any]],
    papers_by_split: dict[str, list[dict[str, Any]]],
    paper_manifest_rows: list[dict[str, Any]],
    leftover_rows: list[dict[str, Any]],
    strict_quotas: Iterable[dict[str, int]],
    external_paper_ids: set[str] | None = None,
) -> InternalSplitAuditResult:
    errors: list[str] = []
    warnings: list[str] = []
    quota_tuple = tuple({str(key): int(value) for key, value in quota.items()} for quota in strict_quotas)
    external_paper_ids = external_paper_ids or set()

    try:
        validate_internal_item_split_manifest(item_manifest_rows)
    except ValueError as exc:
        errors.append(str(exc))
    for row in paper_manifest_rows:
        try:
            validate_internal_paper_manifest_record(row)
        except ValueError as exc:
            errors.append(str(exc))
    for row in leftover_rows:
        try:
            validate_leftover_record(row)
        except ValueError as exc:
            errors.append(str(exc))

    item_by_id: dict[str, dict[str, Any]] = {}
    duplicate_source_items = 0
    for item in items:
        item_id = str(item.get("item_id", ""))
        if item_id in item_by_id:
            duplicate_source_items += 1
        item_by_id[item_id] = dict(item)
    manifest_by_item = {str(row["item_id"]): row for row in item_manifest_rows}

    item_sets = {
        split: {str(row["item_id"]) for row in item_manifest_rows if row.get("internal_split") == split}
        for split in INTERNAL_SPLITS
    }
    prompt_sets = {
        split: {
            (str(row.get("dataset", "")), str(row.get("prompt_group", "")))
            for row in item_manifest_rows
            if row.get("internal_split") == split
        }
        for split in INTERNAL_SPLITS
    }
    component_sets = {
        split: {
            str(row.get("component_id", ""))
            for row in item_manifest_rows
            if row.get("internal_split") == split
        }
        for split in INTERNAL_SPLITS
    }
    paper_sets = {
        split: {str(paper.get("paper_id", "")) for paper in papers_by_split.get(split, [])}
        for split in INTERNAL_SPLITS
    }

    all_paper_ids = [
        str(paper.get("paper_id", ""))
        for split in INTERNAL_SPLITS
        for paper in papers_by_split.get(split, [])
    ]
    duplicate_paper_ids = sum(count - 1 for count in Counter(all_paper_ids).values() if count > 1)

    item_overlap = item_sets["train_fit"] & item_sets["train_calibration"]
    prompt_overlap = prompt_sets["train_fit"] & prompt_sets["train_calibration"]
    component_overlap = component_sets["train_fit"] & component_sets["train_calibration"]
    paper_overlap = paper_sets["train_fit"] & paper_sets["train_calibration"]

    legacy_assignment_count = sum(row.get("assignment_unit") != "item_component" for row in item_manifest_rows)
    internal_paper_ids = paper_sets["train_fit"] | paper_sets["train_calibration"]
    legacy_id_reuse = internal_paper_ids & external_paper_ids
    # 没提供外部 ID 时，也阻止旧式 paper_train_<纯数字> ID。
    legacy_pattern_ids = {paper_id for paper_id in internal_paper_ids if re.fullmatch(r"paper_train_\d+", paper_id)}
    legacy_assignment_count += len(legacy_id_reuse | legacy_pattern_ids)

    referenced_items: list[str] = []
    cross_split_refs = 0
    missing_refs = 0
    non_five = 0
    strict_violations = 0
    paper_metadata_split_mismatches = 0
    for split in INTERNAL_SPLITS:
        for paper in papers_by_split.get(split, []):
            paper_id = str(paper.get("paper_id", ""))
            paper_items = [str(item_id) for item_id in paper.get("items", [])]
            referenced_items.extend(paper_items)
            if len(paper_items) != 5:
                non_five += 1
            if paper.get("metadata", {}).get("internal_split") != split:
                paper_metadata_split_mismatches += 1
            counts = Counter(
                str(item_by_id[item_id].get("dataset", ""))
                for item_id in paper_items
                if item_id in item_by_id
            )
            if not _quota_matches(counts, quota_tuple):
                strict_violations += 1
            for item_id in paper_items:
                if item_id not in item_by_id or item_id not in manifest_by_item:
                    missing_refs += 1
                    continue
                if manifest_by_item[item_id].get("internal_split") != split:
                    cross_split_refs += 1

    duplicate_item_refs = sum(count - 1 for count in Counter(referenced_items).values() if count > 1)
    used_set = set(referenced_items)
    leftover_ids = [str(row["item_id"]) for row in leftover_rows]
    duplicate_leftovers = sum(count - 1 for count in Counter(leftover_ids).values() if count > 1)
    leftover_manifest_mismatches = 0
    for row in leftover_rows:
        item_id = str(row.get("item_id", ""))
        manifest_row = manifest_by_item.get(item_id)
        if manifest_row is None or any(
            str(row.get(field_name, "")) != str(manifest_row.get(field_name, ""))
            for field_name in ("internal_split", "dataset", "component_id")
        ):
            leftover_manifest_mismatches += 1
    used_leftover_overlap = used_set & set(leftover_ids)
    manifest_ids = set(manifest_by_item)
    unaccounted_items = manifest_ids - used_set - set(leftover_ids)
    unexpected_accounted_items = (used_set | set(leftover_ids)) - manifest_ids

    manifest_pair_list = [(str(row["paper_id"]), str(row["item_id"])) for row in paper_manifest_rows]
    manifest_paper_pairs = set(manifest_pair_list)
    duplicate_paper_manifest_pairs = sum(
        count - 1 for count in Counter(manifest_pair_list).values() if count > 1
    )
    actual_pair_details: dict[tuple[str, str], dict[str, Any]] = {}
    for split in INTERNAL_SPLITS:
        for paper in papers_by_split.get(split, []):
            for position, item_id in enumerate(paper.get("items", [])):
                item_id = str(item_id)
                manifest_row = manifest_by_item.get(item_id, {})
                actual_pair_details[(str(paper["paper_id"]), item_id)] = {
                    "internal_split": split,
                    "paper_position": position,
                    "dataset": str(item_by_id.get(item_id, {}).get("dataset", "")),
                    "component_id": str(manifest_row.get("component_id", "")),
                }
    actual_paper_pairs = set(actual_pair_details)
    missing_manifest_pairs = actual_paper_pairs - manifest_paper_pairs
    stale_manifest_pairs = manifest_paper_pairs - actual_paper_pairs
    paper_manifest_mismatches = 0
    for row in paper_manifest_rows:
        pair = (str(row["paper_id"]), str(row["item_id"]))
        actual = actual_pair_details.get(pair)
        item_manifest = manifest_by_item.get(str(row["item_id"]))
        if actual is None or item_manifest is None:
            continue
        try:
            manifest_position = int(row.get("paper_position", -1))
        except (TypeError, ValueError):
            manifest_position = -1
        if (
            str(row.get("internal_split", "")) != actual["internal_split"]
            or manifest_position != actual["paper_position"]
            or str(row.get("dataset", "")) != actual["dataset"]
            or str(row.get("component_id", "")) != actual["component_id"]
            or str(row.get("internal_split", "")) != str(item_manifest.get("internal_split", ""))
        ):
            paper_manifest_mismatches += 1


    summary: dict[str, Any] = {
        "legacy_paper_assignment_count": int(legacy_assignment_count),
        "item_overlap_count": len(item_overlap),
        "prompt_group_overlap_count": len(prompt_overlap),
        "component_overlap_count": len(component_overlap),
        "paper_overlap_count": len(paper_overlap),
        "duplicate_paper_id_count": duplicate_paper_ids,
        "cross_split_reference_count": cross_split_refs,
        "missing_item_reference_count": missing_refs,
        "non_five_item_paper_count": non_five,
        "strict_mix_violation_count": strict_violations,
        "duplicate_item_reference_count": duplicate_item_refs,
        "duplicate_leftover_count": duplicate_leftovers,
        "leftover_manifest_mismatch_count": leftover_manifest_mismatches,
        "used_leftover_overlap_count": len(used_leftover_overlap),
        "unaccounted_item_count": len(unaccounted_items),
        "unexpected_accounted_item_count": len(unexpected_accounted_items),
        "paper_metadata_split_mismatch_count": paper_metadata_split_mismatches,
        "missing_paper_manifest_pair_count": len(missing_manifest_pairs),
        "stale_paper_manifest_pair_count": len(stale_manifest_pairs),
        "duplicate_paper_manifest_pair_count": duplicate_paper_manifest_pairs,
        "paper_manifest_mismatch_count": paper_manifest_mismatches,
        "duplicate_source_item_count": duplicate_source_items,
        "source_item_count": len(manifest_ids),
        "used_item_count": len(used_set),
        "leftover_item_count": len(leftover_ids),
        "paper_count": sum(len(papers_by_split.get(split, [])) for split in INTERNAL_SPLITS),
    }

    blocking = {
        key: value
        for key, value in summary.items()
        if key.endswith("_count")
        and key
        not in {
            "source_item_count",
            "used_item_count",
            "leftover_item_count",
            "paper_count",
        }
        and int(value) != 0
    }
    for key, value in blocking.items():
        errors.append(f"阻塞性内部数据审计失败: {key}={value}")

    if not item_sets["train_fit"] or not item_sets["train_calibration"]:
        errors.append("train_fit/train_calibration 均必须非空")
    expected_datasets = {dataset for quota in quota_tuple for dataset in quota}
    for split in INTERNAL_SPLITS:
        observed = {str(manifest_by_item[item_id].get("dataset", "")) for item_id in item_sets[split]}
        if observed != expected_datasets:
            errors.append(f"{split} 数据集覆盖不完整: {sorted(observed)}")

    distribution_rows: list[dict[str, Any]] = []
    for split in INTERNAL_SPLITS:
        dataset_counts = Counter(
            str(row.get("dataset", "")) for row in item_manifest_rows if row.get("internal_split") == split
        )
        distribution_rows.append(
            {"category": "items", "internal_split": split, "dataset": "ALL", "value": sum(dataset_counts.values())}
        )
        for dataset, count in sorted(dataset_counts.items()):
            distribution_rows.append(
                {"category": "items", "internal_split": split, "dataset": dataset, "value": count}
            )
        distribution_rows.append(
            {"category": "papers", "internal_split": split, "dataset": "ALL", "value": len(papers_by_split.get(split, []))}
        )
        distribution_rows.append(
            {
                "category": "leftovers",
                "internal_split": split,
                "dataset": "ALL",
                "value": sum(row.get("internal_split") == split for row in leftover_rows),
            }
        )

    summary["status"] = "PASS" if not errors else "FAIL"
    total = len(manifest_ids)
    summary["train_fit_ratio"] = len(item_sets["train_fit"]) / total if total else 0.0
    summary["train_calibration_ratio"] = len(item_sets["train_calibration"]) / total if total else 0.0
    return InternalSplitAuditResult(
        passed=not errors,
        summary=summary,
        errors=tuple(errors),
        warnings=tuple(warnings),
        distribution_rows=tuple(distribution_rows),
    )


def write_internal_split_audit(
    result: InternalSplitAuditResult,
    run_id: str,
    *,
    output_root: str | Path = "outputs/runs",
    overwrite: bool = False,
) -> dict[str, Path]:
    report_dir = ensure_dir(Path(output_root) / run_id / "reports")
    report_path = report_dir / "internal_split_audit.md"
    if report_path.exists() and not overwrite:
        raise FileExistsError(f"审计报告已存在: {report_path}")
    lines = [
        "# Internal Split 与 Rebuilt Paper 审计报告",
        "",
        f"- run_id: `{run_id}`",
        f"- 审计状态: **{result.summary.get('status', 'UNKNOWN')}**",
        f"- source Item: {result.summary.get('source_item_count', 0)}",
        f"- train_fit 比例: {result.summary.get('train_fit_ratio', 0):.6f}",
        f"- train_calibration 比例: {result.summary.get('train_calibration_ratio', 0):.6f}",
        f"- rebuilt Paper: {result.summary.get('paper_count', 0)}",
        f"- used Item: {result.summary.get('used_item_count', 0)}",
        f"- leftover Item: {result.summary.get('leftover_item_count', 0)}",
        "",
        "## 审计产物指纹",
        "",
    ]
    artifact_hashes = result.summary.get("audited_artifact_hashes", {})
    if artifact_hashes:
        lines.extend(f"- `{name}`: `{value}`" for name, value in sorted(artifact_hashes.items()))
    else:
        lines.append("- 未提供（仅内存 fixture 审计）")
    lines.extend([
        "",
        "## 阻塞性门禁",
        "",
        "| 检查项 | 数量 |",
        "|---|---:|",
    ])
    gate_keys = (
        "legacy_paper_assignment_count",
        "item_overlap_count",
        "prompt_group_overlap_count",
        "component_overlap_count",
        "paper_overlap_count",
        "duplicate_paper_id_count",
        "cross_split_reference_count",
        "missing_item_reference_count",
        "non_five_item_paper_count",
        "strict_mix_violation_count",
        "duplicate_item_reference_count",
        "duplicate_leftover_count",
        "leftover_manifest_mismatch_count",
        "used_leftover_overlap_count",
        "unaccounted_item_count",
        "unexpected_accounted_item_count",
        "paper_metadata_split_mismatch_count",
        "missing_paper_manifest_pair_count",
        "stale_paper_manifest_pair_count",
        "duplicate_paper_manifest_pair_count",
        "paper_manifest_mismatch_count",
        "duplicate_source_item_count",
    )
    for key in gate_keys:
        lines.append(f"| `{key}` | {result.summary.get(key, 0)} |")
    lines.extend(["", "## 错误", ""])
    lines.extend(f"- {error}" for error in result.errors) if result.errors else lines.append("- 无")
    lines.extend(["", "## 警告", ""])
    lines.extend(f"- {warning}" for warning in result.warnings) if result.warnings else lines.append("- 无")
    tmp = report_path.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(report_path)
    distribution_path = write_csv(
        report_dir / "internal_split_distribution.csv",
        result.distribution_rows,
        ["category", "internal_split", "dataset", "value"],
        overwrite=overwrite,
    )
    return {"report": report_path, "distribution": distribution_path}


def audit_internal_split_artifacts(
    *,
    items_path: str | Path,
    item_manifest_path: str | Path,
    papers_train_fit_path: str | Path,
    papers_train_calibration_path: str | Path,
    paper_manifest_path: str | Path,
    leftover_path: str | Path,
    strict_quotas: Iterable[dict[str, int]],
    external_paper_manifest_path: str | Path | None = None,
) -> InternalSplitAuditResult:
    external_ids: set[str] = set()
    if external_paper_manifest_path is not None:
        external_ids = {
            str(row.get("paper_id", ""))
            for row in read_csv(external_paper_manifest_path)
            if row.get("split") == "train"
        }
    result = audit_internal_split(
        items=read_jsonl(items_path),
        item_manifest_rows=read_csv(item_manifest_path),
        papers_by_split={
            "train_fit": read_jsonl(papers_train_fit_path),
            "train_calibration": read_jsonl(papers_train_calibration_path),
        },
        paper_manifest_rows=read_csv(paper_manifest_path),
        leftover_rows=read_csv(leftover_path),
        strict_quotas=strict_quotas,
        external_paper_ids=external_ids,
    )
    result.summary["audited_artifact_hashes"] = {
        "items_train_sha256": file_sha256(items_path),
        "internal_item_split_manifest_sha256": file_sha256(item_manifest_path),
        "papers_train_fit_sha256": file_sha256(papers_train_fit_path),
        "papers_train_calibration_sha256": file_sha256(papers_train_calibration_path),
        "internal_paper_manifest_sha256": file_sha256(paper_manifest_path),
        "leftover_items_sha256": file_sha256(leftover_path),
        "external_paper_manifest_sha256": file_sha256(external_paper_manifest_path)
        if external_paper_manifest_path is not None
        else "",
    }
    return result

