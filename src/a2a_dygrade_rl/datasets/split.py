"""Dataset Semantic V2 的全局 prompt/source-lineage train/dev/test 划分。"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.io import write_csv, write_jsonl
from a2a_dygrade_rl.utils.seed import set_seed
from a2a_dygrade_rl.utils.validation import validate_no_split_leakage


SPLITS = ("train", "dev", "test")


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def _connect(mapping: dict[Any, int], key: Any, index: int, dsu: _DisjointSet) -> None:
    if key is None or key == "" or (isinstance(key, tuple) and any(value == "" for value in key)):
        return
    previous = mapping.get(key)
    if previous is None:
        mapping[key] = index
    else:
        dsu.union(previous, index)


def _leakage_components(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """构建跨数据集全局连通分量，防止 Router 通过 split 记住数据来源。"""

    ordered = sorted((dict(item) for item in items), key=lambda row: str(row.get("item_id", "")))
    dsu = _DisjointSet(len(ordered))
    prompt_group_seen: dict[tuple[str, str], int] = {}
    prompt_text_seen: dict[str, int] = {}
    exact_seen: dict[tuple[str, str], int] = {}
    lineage_seen: dict[tuple[str, str, str], int] = {}
    existing_component_seen: dict[tuple[str, str], int] = {}
    for index, item in enumerate(ordered):
        metadata = item.get("metadata", {})
        dataset = _normalized_text(item.get("dataset"))
        prompt_group = _normalized_text(metadata.get("prompt_group") or item.get("prompt"))
        prompt = _normalized_text(item.get("prompt"))
        answer = _normalized_text(item.get("student_answer"))
        source_file = _normalized_text(metadata.get("source_file"))
        source_record_id = _normalized_text(metadata.get("source_record_id"))
        existing_component = _normalized_text(metadata.get("leakage_component_id"))
        _connect(prompt_group_seen, (dataset, prompt_group), index, dsu)
        _connect(prompt_text_seen, prompt, index, dsu)
        _connect(exact_seen, (prompt, answer), index, dsu)
        _connect(lineage_seen, (dataset, source_file, source_record_id), index, dsu)
        if existing_component:
            _connect(existing_component_seen, (dataset, existing_component), index, dsu)

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(ordered):
        grouped[dsu.find(index)].append(item)
    components: dict[str, list[dict[str, Any]]] = {}
    for group_items in grouped.values():
        item_ids = sorted(str(item["item_id"]) for item in group_items)
        digest = hashlib.sha256("\n".join(item_ids).encode("utf-8")).hexdigest()[:20]
        components[f"leakage_{digest}"] = group_items
    return components


def _normalized_ratios(ratios: dict[str, float]) -> dict[str, float]:
    values = {split: max(0.0, float(ratios.get(split, 0.0))) for split in SPLITS}
    total = sum(values.values())
    if total <= 0:
        raise ValueError("split ratios 总和必须大于0")
    return {split: value / total for split, value in values.items()}


def _assign_components(
    components: dict[str, list[dict[str, Any]]],
    ratios: dict[str, float],
    seed: int,
) -> dict[str, str]:
    normalized_ratios = _normalized_ratios(ratios)
    rng = set_seed(seed)
    shuffled_ids = sorted(components)
    rng.shuffle(shuffled_ids)
    tie_order = {component_id: index for index, component_id in enumerate(shuffled_ids)}
    component_counts = {
        component_id: Counter(str(item["dataset"]) for item in group)
        for component_id, group in components.items()
    }

    dataset_totals: Counter[str] = Counter()
    dataset_components: dict[str, set[str]] = defaultdict(set)
    for component_id, counts in component_counts.items():
        dataset_totals.update(counts)
        for dataset in counts:
            dataset_components[dataset].add(component_id)
    targets = {
        dataset: {split: total * normalized_ratios[split] for split in SPLITS}
        for dataset, total in dataset_totals.items()
    }
    assigned = {dataset: {split: 0 for split in SPLITS} for dataset in dataset_totals}
    total_target = {split: sum(dataset_totals.values()) * normalized_ratios[split] for split in SPLITS}
    assigned_total = {split: 0 for split in SPLITS}
    split_by_component: dict[str, str] = {}

    def commit(component_id: str, split: str) -> None:
        split_by_component[component_id] = split
        group_size = len(components[component_id])
        assigned_total[split] += group_size
        for dataset, count in component_counts[component_id].items():
            assigned[dataset][split] += count

    # 先建立覆盖锚点：只要数据集拥有至少3个独立 component，就必须先各放一个到 train/dev/test。
    # 优先选择单数据集且较小的 component，尽量减少对目标比例的扰动。
    for dataset in sorted(dataset_components, key=lambda name: (len(dataset_components[name]), name)):
        if len(dataset_components[dataset]) < 3:
            continue
        for split in SPLITS:
            if any(
                split_by_component.get(component_id) == split
                for component_id in dataset_components[dataset]
            ):
                continue
            candidates = [
                component_id
                for component_id in dataset_components[dataset]
                if component_id not in split_by_component
            ]
            if not candidates:
                raise ValueError(f"无法为数据集 {dataset} 建立 {split} 覆盖锚点")
            selected = min(
                candidates,
                key=lambda component_id: (
                    len(component_counts[component_id]) - 1,
                    len(components[component_id]),
                    tie_order[component_id],
                    component_id,
                ),
            )
            commit(selected, split)

    remaining_ids = [component_id for component_id in shuffled_ids if component_id not in split_by_component]
    remaining_ids.sort(key=lambda component_id: len(components[component_id]), reverse=True)
    for component_id in remaining_ids:
        group = components[component_id]
        counts = component_counts[component_id]
        candidate_scores: list[tuple[float, int, str]] = []
        for split_index, split in enumerate(SPLITS):
            error = 0.0
            for dataset in dataset_totals:
                for candidate_split in SPLITS:
                    value = assigned[dataset][candidate_split]
                    if candidate_split == split:
                        value += counts.get(dataset, 0)
                    target = targets[dataset][candidate_split]
                    error += ((value - target) ** 2) / max(target, 1.0)
            for candidate_split in SPLITS:
                value = assigned_total[candidate_split]
                if candidate_split == split:
                    value += len(group)
                target = total_target[candidate_split]
                error += ((value - target) ** 2) / max(target, 1.0)
            candidate_scores.append((error, split_index, split))
        _, _, selected = min(candidate_scores)
        commit(component_id, selected)

    dataset_splits: dict[str, set[str]] = defaultdict(set)
    for component_id, split in split_by_component.items():
        for dataset in component_counts[component_id]:
            dataset_splits[dataset].add(split)
    uncovered = {
        dataset: sorted(set(SPLITS) - dataset_splits[dataset])
        for dataset in dataset_components
        if len(dataset_components[dataset]) >= 3 and set(SPLITS) - dataset_splits[dataset]
    }
    if uncovered:
        raise ValueError(f"全局 component 划分未覆盖全部 split: {uncovered}")
    return split_by_component

def assign_prompt_splits(
    items: list[dict[str, Any]],
    ratios: dict[str, float],
    seed: int,
    rule_version: str,
) -> list[dict[str, Any]]:
    if not items:
        return []
    components = _leakage_components(items)
    split_by_component = _assign_components(components, ratios, seed)
    dataset_component_counts: Counter[str] = Counter()
    for group in components.values():
        dataset_component_counts.update({str(item["dataset"]) for item in group})

    split_items: list[dict[str, Any]] = []
    for component_id in sorted(components):
        group = components[component_id]
        component_dataset_counts = Counter(str(item["dataset"]) for item in group)
        for item in group:
            copied = dict(item)
            copied["metadata"] = dict(item.get("metadata", {}))
            copied["metadata"].update(
                {
                    "split": split_by_component[component_id],
                    "split_seed": seed,
                    "split_rule_version": rule_version,
                    "split_scope": "global_prompt_lineage_exact_answer_semantic_v2",
                    "dataset_prompt_group_count": dataset_component_counts[str(item["dataset"])],
                    "leakage_component_id": component_id,
                    "leakage_component_size": len(group),
                    "leakage_component_dataset_counts": dict(sorted(component_dataset_counts.items())),
                }
            )
            split_items.append(copied)
    validate_no_split_leakage(split_items)
    return sorted(split_items, key=lambda row: str(row["item_id"]))


def write_split_items(
    items: list[dict[str, Any]],
    output_dir: str | Path,
    overwrite: bool = False,
) -> dict[str, Path]:
    output = Path(output_dir)
    paths: dict[str, Path] = {}
    for split in SPLITS:
        split_rows = [item for item in items if item["metadata"]["split"] == split]
        paths[split] = write_jsonl(output / f"items_{split}.jsonl", split_rows, overwrite=overwrite)
    manifest_rows = [
        {
            "item_id": item["item_id"],
            "dataset": item["dataset"],
            "prompt_group": item["metadata"].get("prompt_group", ""),
            "source_lineage_id": item["metadata"].get("source_lineage_id", ""),
            "leakage_component_id": item["metadata"].get("leakage_component_id", ""),
            "component_size": item["metadata"].get("leakage_component_size", ""),
            "component_datasets": json.dumps(
                item["metadata"].get("leakage_component_dataset_counts", {}),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "paper_id": "",
            "split": item["metadata"]["split"],
            "seed": item["metadata"]["split_seed"],
            "rule_version": item["metadata"]["split_rule_version"],
            "split_scope": item["metadata"].get("split_scope", ""),
        }
        for item in items
    ]
    paths["split_manifest"] = write_csv(
        output / "split_manifest.csv",
        manifest_rows,
        [
            "item_id",
            "dataset",
            "prompt_group",
            "source_lineage_id",
            "leakage_component_id",
            "component_size",
            "component_datasets",
            "paper_id",
            "split",
            "seed",
            "rule_version",
            "split_scope",
        ],
        overwrite=overwrite,
    )
    return paths