"""Dataset Semantic V2 外部 strict Paper 构建与 leftover 审计。"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

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
from a2a_dygrade_rl.utils.schemas import Paper, PaperBudget
from a2a_dygrade_rl.utils.seed import set_seed
from a2a_dygrade_rl.utils.validation import validate_paper


SPLITS = ("train", "dev", "test")


def _mix_label(counts: Counter[str]) -> str:
    return ";".join(f"{dataset}:{counts[dataset]}" for dataset in sorted(counts))


def _build_relaxed_chunks(items: list[dict[str, Any]], target_items: int, min_items: int, max_items: int) -> list[list[dict[str, Any]]]:
    chunks = []
    for index in range(0, len(items), target_items):
        chunk = items[index : index + target_items]
        if len(chunk) < min_items or len(chunk) > max_items:
            continue
        chunks.append(chunk)
    return chunks


def _build_strict_chunks(
    items: list[dict[str, Any]],
    quotas: list[dict[str, int]],
) -> list[tuple[list[dict[str, Any]], dict[str, int], int]]:
    items_by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        items_by_dataset[str(item["dataset"])].append(item)
    chunks: list[tuple[list[dict[str, Any]], dict[str, int], int]] = []
    while True:
        feasible = [
            (index, quota)
            for index, quota in enumerate(quotas, start=1)
            if all(len(items_by_dataset[dataset]) >= count for dataset, count in quota.items())
        ]
        if not feasible:
            break
        quota_index, quota = min(
            feasible,
            key=lambda pair: (
                max(len(items_by_dataset[dataset]) - count for dataset, count in pair[1].items())
                - min(len(items_by_dataset[dataset]) - count for dataset, count in pair[1].items()),
                pair[0],
            ),
        )
        chunk: list[dict[str, Any]] = []
        for dataset in sorted(quota):
            for _ in range(int(quota[dataset])):
                chunk.append(items_by_dataset[dataset].pop())
        chunks.append((chunk, dict(quota), quota_index))
    return chunks


def _paper_id_prefix(config: dict[str, Any]) -> str:
    paper_config = config.get("paper", {})
    explicit = str(paper_config.get("id_prefix", "")).strip()
    if explicit:
        return explicit
    rule = str(paper_config.get("rule_version") or config.get("run", {}).get("rule_version", ""))
    return "paper_semantic_v2" if "semantic" in rule.lower() else "paper"


def _update_split_manifest(output_dir: Path, paper_by_item: dict[str, str]) -> Path | None:
    split_manifest = output_dir / "split_manifest.csv"
    if not split_manifest.exists():
        return None
    rows = read_csv(split_manifest)
    if not rows:
        return split_manifest
    fieldnames = list(rows[0])
    if "paper_id" not in fieldnames:
        fieldnames.append("paper_id")
    for row in rows:
        row["paper_id"] = paper_by_item.get(str(row.get("item_id", "")), "")
    return write_csv(split_manifest, rows, fieldnames, overwrite=True)


def _update_dataset_build_manifest(processed_dir: Path, paths: dict[str, Path], summary: dict[str, Any]) -> None:
    manifest_path = processed_dir / "dataset_build_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = dict(manifest.get("artifacts", {}))
    for name, path in paths.items():
        if name == "summary" or not path.exists() or path == manifest_path:
            continue
        artifacts[name] = {
            "relative_path": path.relative_to(processed_dir).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    manifest["artifacts"] = artifacts
    manifest["paper_build"] = summary
    write_json(manifest_path, manifest, overwrite=True)


def build_papers(
    config_path: str | Path,
    input_dir: str | Path,
    output_dir: str | Path,
    run_id: str,
    seed: int | None = None,
    overwrite: bool = False,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Path]:
    config_path = Path(config_path)
    config = read_yaml(config_path)
    effective_seed = int(seed if seed is not None else config.get("run", {}).get("seed", 42))
    rng = set_seed(effective_seed)
    paper_config = config.get("paper", {})
    target_items = int(paper_config.get("target_items", 5))
    min_items = int(paper_config.get("min_items", 5))
    max_items = int(paper_config.get("max_items", 8))
    mix_mode = str(paper_config.get("mix_mode", "relaxed"))
    strict_quotas = [{str(key): int(value) for key, value in quota.items()} for quota in paper_config.get("strict_quotas", [])]
    if mix_mode == "strict":
        if not strict_quotas:
            raise ValueError("strict Paper 构建必须配置 strict_quotas")
        invalid_quotas = [quota for quota in strict_quotas if sum(quota.values()) != target_items]
        if invalid_quotas:
            raise ValueError(f"strict quota 总 Item 数必须等于 target_items={target_items}: {invalid_quotas}")
    budgets = paper_config.get("budgets", {})
    budget = PaperBudget(
        max_cost=float(budgets.get("max_cost", 0.2)),
        max_elapsed_time=float(budgets.get("max_elapsed_time", budgets.get("max_latency", 30.0))),
        max_agent_calls=int(budgets.get("max_agent_calls", 12)),
        max_a2a_exchanges=int(budgets.get("max_a2a_exchanges", budgets.get("max_a2a_messages", 6))),
    )
    rule_version = str(paper_config.get("rule_version") or config.get("run", {}).get("rule_version", "dataset_semantic_paper_v2"))
    id_prefix = _paper_id_prefix(config)
    output = Path(output_dir)
    paths: dict[str, Path] = {}
    manifest_rows: list[dict[str, Any]] = []
    leftover_rows: list[dict[str, Any]] = []
    paper_by_item: dict[str, str] = {}
    split_summary: dict[str, Any] = {}

    for split in SPLITS:
        item_path = Path(input_dir) / f"items_{split}.jsonl"
        if not item_path.exists():
            continue
        items = read_jsonl(item_path)
        items_by_id = {str(item["item_id"]): item for item in items}
        rng.shuffle(items)
        if mix_mode == "strict":
            chunks = _build_strict_chunks(items, strict_quotas)
        else:
            chunks = [(chunk, {}, 0) for chunk in _build_relaxed_chunks(items, target_items, min_items, max_items)]
        papers: list[dict[str, Any]] = []
        used_item_ids: set[str] = set()
        quota_counts: Counter[int] = Counter()
        for chunk, quota, quota_index in chunks:
            paper_id = f"{id_prefix}_{split}_{len(papers):05d}"
            dataset_counts = Counter(str(item["dataset"]) for item in chunk)
            mix_status = "strict" if quota and all(dataset_counts.get(dataset, 0) == count for dataset, count in quota.items()) else "relaxed"
            deviation_reason = "" if mix_status == "strict" else "未配置 strict quota 或数据不足，使用 relaxed chunk 构造"
            paper = Paper(
                paper_id=paper_id,
                items=[str(item["item_id"]) for item in chunk],
                paper_budget=budget,
                metadata={
                    "split": split,
                    "seed": effective_seed,
                    "construction_rule_version": rule_version,
                    "dataset_mix": dict(sorted(dataset_counts.items())),
                    "mix_status": mix_status,
                    "strict_quota_id": f"quota_{quota_index}" if quota_index else "",
                    "deviation_reason": deviation_reason,
                    "budget_status": str(paper_config.get("budget_status", "provisional_pre_agent_cache")),
                },
            ).to_dict()
            validate_paper(paper, items_by_id)
            papers.append(paper)
            quota_counts[quota_index] += 1
            for position, item_id in enumerate(paper["items"], start=1):
                if item_id in used_item_ids:
                    raise ValueError(f"外部 Paper 重复引用 Item: {item_id}")
                used_item_ids.add(item_id)
                paper_by_item[item_id] = paper_id
                item = items_by_id[item_id]
                manifest_rows.append(
                    {
                        "item_id": item_id,
                        "dataset": item["dataset"],
                        "question_type": item.get("question_type", ""),
                        "prompt_group": item.get("metadata", {}).get("prompt_group", ""),
                        "leakage_component_id": item.get("metadata", {}).get("leakage_component_id", ""),
                        "paper_id": paper_id,
                        "paper_position": position,
                        "split": split,
                        "seed": effective_seed,
                        "rule_version": rule_version,
                        "split_scope": item.get("metadata", {}).get("split_scope", ""),
                        "paper_dataset_mix": _mix_label(dataset_counts),
                        "strict_quota_id": f"quota_{quota_index}" if quota_index else "",
                        "mix_status": mix_status,
                        "deviation_reason": deviation_reason,
                    }
                )
        for item in items:
            item_id = str(item["item_id"])
            if item_id in used_item_ids:
                continue
            leftover_rows.append(
                {
                    "item_id": item_id,
                    "dataset": item["dataset"],
                    "split": split,
                    "prompt_group": item.get("metadata", {}).get("prompt_group", ""),
                    "leakage_component_id": item.get("metadata", {}).get("leakage_component_id", ""),
                    "reason": "strict_capacity_exhausted_without_cross_split_borrowing" if mix_mode == "strict" else "relaxed_chunk_outside_size_bounds",
                    "seed": effective_seed,
                    "rule_version": rule_version,
                }
            )
        paths[split] = write_jsonl(output / f"papers_{split}.jsonl", papers, overwrite=overwrite)
        split_summary[split] = {
            "input_item_count": len(items),
            "paper_count": len(papers),
            "used_item_count": len(used_item_ids),
            "leftover_item_count": len(items) - len(used_item_ids),
            "quota_counts": {f"quota_{index}": count for index, count in sorted(quota_counts.items()) if index},
        }

    paths["paper_manifest"] = write_csv(
        output / "paper_manifest.csv",
        manifest_rows,
        [
            "item_id",
            "dataset",
            "question_type",
            "prompt_group",
            "leakage_component_id",
            "paper_id",
            "paper_position",
            "split",
            "seed",
            "rule_version",
            "split_scope",
            "paper_dataset_mix",
            "strict_quota_id",
            "mix_status",
            "deviation_reason",
        ],
        overwrite=overwrite,
    )
    paths["external_leftovers"] = write_csv(
        output / "external_leftover_items.csv",
        leftover_rows,
        [
            "item_id",
            "dataset",
            "split",
            "prompt_group",
            "leakage_component_id",
            "reason",
            "seed",
            "rule_version",
        ],
        overwrite=overwrite,
    )
    updated_split_manifest = _update_split_manifest(output, paper_by_item)
    if updated_split_manifest is not None:
        paths["split_manifest"] = updated_split_manifest

    summary = {
        "schema_version": "external_paper_build_summary_v2",
        "run_id": run_id,
        "seed": effective_seed,
        "rule_version": rule_version,
        "mix_mode": mix_mode,
        "strict_quotas": strict_quotas,
        "target_items": target_items,
        "split_summary": split_summary,
        "total_paper_count": sum(value["paper_count"] for value in split_summary.values()),
        "total_used_item_count": len(manifest_rows),
        "total_leftover_item_count": len(leftover_rows),
        "cross_split_borrow_count": 0,
        "duplicate_item_reference_count": 0,
    }
    paths["summary"] = write_json(
        Path(output_root) / run_id / "reports" / "external_paper_build_summary.json",
        summary,
        overwrite=overwrite,
    )
    _update_dataset_build_manifest(output, paths, summary)
    copy_config_snapshot(config_path, run_id, output_root=output_root)
    return paths