"""在 train_fit 与 train_calibration Item 池内分别重建固定5题 strict Paper。"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.datasets.internal_split import DEFAULT_STRICT_QUOTAS, INTERNAL_SPLITS, strict_paper_plan
from a2a_dygrade_rl.utils.io import (
    copy_config_snapshot,
    file_sha256,
    read_csv,
    read_jsonl,
    read_yaml,
    write_csv,
    write_json,
    write_jsonl,
)
from a2a_dygrade_rl.utils.schemas import InternalPaperManifest, LeftoverRecord, Paper, PaperBudget
from a2a_dygrade_rl.utils.validation import (
    canonical_budget,
    validate_internal_item_split_manifest,
    validate_internal_paper_manifest_record,
    validate_leftover_record,
    validate_paper,
)


def _stable_hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _mix_label(counts: Counter[str]) -> str:
    return ";".join(f"{dataset}:{counts[dataset]}" for dataset in sorted(counts))


@dataclass(frozen=True)
class InternalPaperBuildResult:
    papers_by_split: dict[str, list[dict[str, Any]]]
    paper_manifest_rows: list[dict[str, Any]]
    leftover_rows: list[dict[str, Any]]
    summary: dict[str, Any]


def rebuild_internal_papers(
    items: Iterable[dict[str, Any]],
    item_manifest_rows: list[dict[str, Any]],
    *,
    strict_quotas: Iterable[dict[str, int]] = DEFAULT_STRICT_QUOTAS,
    budget: dict[str, Any],
    seed: int = 20260729,
    rule_version: str = "internal_strict_paper_v1.4",
) -> InternalPaperBuildResult:
    """严格使用各自内部 split 的 Item，禁止跨 split 借题或继承旧 Paper。"""

    validate_internal_item_split_manifest(item_manifest_rows)
    if any(row.get("assignment_unit") != "item_component" for row in item_manifest_rows):
        raise ValueError("禁止直接拆分旧 Paper；必须先按 Item component 冻结内部 split")

    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        item_id = str(item.get("item_id", ""))
        if item_id in item_by_id:
            raise ValueError(f"Item 输入存在重复 item_id: {item_id}")
        item_by_id[item_id] = dict(item)
    manifest_ids = {str(row["item_id"]) for row in item_manifest_rows}
    missing_items = sorted(manifest_ids - set(item_by_id))
    if missing_items:
        raise ValueError(f"internal manifest 引用不存在 Item: {missing_items[:10]}")

    quota_tuple = tuple({str(key): int(value) for key, value in quota.items()} for quota in strict_quotas)
    if not quota_tuple or any(sum(quota.values()) != 5 for quota in quota_tuple):
        raise ValueError("内部 strict quota 必须固定为每份5题")
    canonical = canonical_budget(budget)
    paper_budget = PaperBudget(**canonical)
    manifest_by_item = {str(row["item_id"]): row for row in item_manifest_rows}

    papers_by_split: dict[str, list[dict[str, Any]]] = {split: [] for split in INTERNAL_SPLITS}
    paper_manifest_rows: list[dict[str, Any]] = []
    leftover_rows: list[dict[str, Any]] = []
    split_summary: dict[str, Any] = {}

    for split in INTERNAL_SPLITS:
        split_rows = [row for row in item_manifest_rows if row["internal_split"] == split]
        items_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in split_rows:
            item = item_by_id[str(row["item_id"])]
            if str(item.get("metadata", {}).get("split", "")) != "train":
                raise ValueError(f"内部 Paper 只能使用外部 train Item: {item['item_id']}")
            if str(item.get("dataset")) != str(row["dataset"]):
                raise ValueError(f"Item dataset 与 internal manifest 不一致: {item['item_id']}")
            items_by_dataset[str(item["dataset"])].append(item)

        for dataset in items_by_dataset:
            items_by_dataset[dataset].sort(
                key=lambda item: (_stable_hash(seed, split, item["item_id"]), str(item["item_id"]))
            )

        available_counts = {dataset: len(rows) for dataset, rows in items_by_dataset.items()}
        paper_count, quota_counts, used_counts = strict_paper_plan(available_counts, quota_tuple)
        quota_sequence: list[tuple[int, dict[str, int]]] = []
        for quota_index, count in enumerate(quota_counts):
            quota_sequence.extend((quota_index, quota_tuple[quota_index]) for _ in range(count))
        quota_sequence.sort(key=lambda entry: _stable_hash(seed, split, "quota", entry[0], len(quota_sequence)))

        cursor = {dataset: 0 for dataset in items_by_dataset}
        used_item_ids: set[str] = set()
        for paper_index, (quota_index, quota) in enumerate(quota_sequence):
            chunk: list[dict[str, Any]] = []
            for dataset in sorted(quota):
                count = quota[dataset]
                start = cursor.get(dataset, 0)
                end = start + count
                selected = items_by_dataset.get(dataset, [])[start:end]
                if len(selected) != count:
                    raise RuntimeError(f"strict planner 与 builder 不一致: {split} {dataset}")
                cursor[dataset] = end
                chunk.extend(selected)
            chunk.sort(key=lambda item: (_stable_hash(seed, split, paper_index, item["item_id"]), str(item["item_id"])))
            paper_id = f"paper_{split}_{paper_index:05d}"
            counts = Counter(str(item["dataset"]) for item in chunk)
            quota_id = f"quota_{quota_index + 1}"
            source_paper_ids = sorted(
                {
                    source_id
                    for item in chunk
                    for source_id in str(manifest_by_item[str(item["item_id"])].get("source_paper_ids", "")).split(";")
                    if source_id
                }
            )
            paper = Paper(
                paper_id=paper_id,
                items=[str(item["item_id"]) for item in chunk],
                paper_budget=paper_budget,
                metadata={
                    "source_split": "train",
                    "internal_split": split,
                    "seed": seed,
                    "construction_rule_version": rule_version,
                    "dataset_mix": dict(sorted(counts.items())),
                    "mix_status": "strict",
                    "strict_quota_id": quota_id,
                    "source_paper_ids": source_paper_ids,
                    "assignment_unit": "item_component",
                },
            ).to_dict()
            validate_paper(paper, {item["item_id"]: item for item in chunk}, required_item_count=5)
            papers_by_split[split].append(paper)
            for position, item in enumerate(chunk):
                item_id = str(item["item_id"])
                if item_id in used_item_ids:
                    raise ValueError(f"内部 split 重复引用 Item: {split} {item_id}")
                used_item_ids.add(item_id)
                manifest_row = manifest_by_item[item_id]
                paper_record = InternalPaperManifest(
                    paper_id=paper_id,
                    internal_split=split,
                    item_id=item_id,
                    paper_position=position,
                    dataset=str(item["dataset"]),
                    prompt_group=str(manifest_row["prompt_group"]),
                    component_id=str(manifest_row["component_id"]),
                    strict_quota_id=quota_id,
                    paper_dataset_mix=_mix_label(counts),
                    seed=seed,
                    rule_version=rule_version,
                    source_paper_ids=str(manifest_row.get("source_paper_ids", "")),
                ).to_dict()
                validate_internal_paper_manifest_record(paper_record)
                paper_manifest_rows.append(paper_record)

        split_item_ids = {str(row["item_id"]) for row in split_rows}
        for item_id in sorted(split_item_ids - used_item_ids):
            item = item_by_id[item_id]
            manifest_row = manifest_by_item[item_id]
            leftover = LeftoverRecord(
                item_id=item_id,
                dataset=str(item["dataset"]),
                internal_split=split,
                prompt_group=str(manifest_row["prompt_group"]),
                component_id=str(manifest_row["component_id"]),
                reason="strict_capacity_exhausted_without_cross_split_borrowing",
                seed=seed,
                rule_version=rule_version,
                source_paper_ids=str(manifest_row.get("source_paper_ids", "")),
            ).to_dict()
            validate_leftover_record(leftover)
            leftover_rows.append(leftover)

        split_summary[split] = {
            "input_items": len(split_rows),
            "papers": paper_count,
            "used_items": len(used_item_ids),
            "leftover_items": len(split_item_ids - used_item_ids),
            "dataset_input_counts": dict(sorted(available_counts.items())),
            "dataset_used_counts": dict(sorted(used_counts.items())),
            "quota_counts": {f"quota_{index + 1}": count for index, count in enumerate(quota_counts)},
        }

    summary = {
        "rule_version": rule_version,
        "seed": seed,
        "fixed_item_count": 5,
        "assignment_unit": "item_component",
        "legacy_paper_assignment_count": 0,
        "splits": split_summary,
        "total_papers": sum(len(rows) for rows in papers_by_split.values()),
        "total_used_items": len(paper_manifest_rows),
        "total_leftover_items": len(leftover_rows),
    }
    return InternalPaperBuildResult(
        papers_by_split=papers_by_split,
        paper_manifest_rows=sorted(paper_manifest_rows, key=lambda row: (row["internal_split"], row["paper_id"], int(row["paper_position"]))),
        leftover_rows=sorted(leftover_rows, key=lambda row: (row["internal_split"], row["item_id"])),
        summary=summary,
    )


def build_internal_paper_artifacts(
    config_path: str | Path,
    items_path: str | Path,
    internal_item_manifest_path: str | Path,
    output_dir: str | Path,
    run_id: str,
    *,
    seed: int | None = None,
    overwrite: bool = False,
    output_root: str | Path = "outputs/runs",
) -> tuple[InternalPaperBuildResult, dict[str, Path]]:
    config = read_yaml(config_path)
    split_config = config.get("internal_split", {})
    paper_config = config.get("paper", {})
    internal_paper_config = config.get("internal_paper", {})
    if split_config.get("assignment_unit", "item_component") != "item_component":
        raise ValueError("禁止直接拆分旧 Paper")
    if internal_paper_config.get("rebuild_separately") is not True:
        raise ValueError("内部 Paper 必须在两个 split 中分别重建")
    effective_seed = int(seed if seed is not None else split_config.get("seed", 20260729))
    rule_version = str(internal_paper_config.get("rule_version", "internal_strict_paper_v1.4"))

    item_manifest_rows = read_csv(internal_item_manifest_path)
    expected_count = split_config.get("expected_source_item_count")
    if expected_count is not None and len(item_manifest_rows) != int(expected_count):
        raise ValueError(
            f"internal item manifest 数量与冻结范围不一致: {len(item_manifest_rows)} != {int(expected_count)}"
        )
    result = rebuild_internal_papers(
        read_jsonl(items_path),
        item_manifest_rows,
        strict_quotas=paper_config.get("strict_quotas", DEFAULT_STRICT_QUOTAS),
        budget=paper_config.get("budgets", {}),
        seed=effective_seed,
        rule_version=rule_version,
    )
    output = Path(output_dir)
    paths: dict[str, Path] = {}
    for split in INTERNAL_SPLITS:
        paths[split] = write_jsonl(
            output / f"papers_{split}.jsonl",
            result.papers_by_split[split],
            overwrite=overwrite,
        )
    paths["paper_manifest"] = write_csv(
        output / "internal_paper_manifest.csv",
        result.paper_manifest_rows,
        list(InternalPaperManifest.__dataclass_fields__),
        overwrite=overwrite,
    )
    paths["leftovers"] = write_csv(
        output / "leftover_items.csv",
        result.leftover_rows,
        list(LeftoverRecord.__dataclass_fields__),
        overwrite=overwrite,
    )
    result.summary["input_artifacts"] = {
        "items_train_sha256": file_sha256(items_path),
        "internal_item_split_manifest_sha256": file_sha256(internal_item_manifest_path),
        "dataset_config_sha256": file_sha256(config_path),
    }
    result.summary["output_artifacts"] = {
        "papers_train_fit_sha256": file_sha256(paths["train_fit"]),
        "papers_train_calibration_sha256": file_sha256(paths["train_calibration"]),
        "internal_paper_manifest_sha256": file_sha256(paths["paper_manifest"]),
        "leftover_items_sha256": file_sha256(paths["leftovers"]),
    }
    paths["summary"] = write_json(
        Path(output_root) / run_id / "reports" / "internal_paper_build_summary.json",
        result.summary,
        overwrite=overwrite,
    )
    copy_config_snapshot(config_path, run_id, output_root=output_root)
    return result, paths
