"""dataset-aware prompt-level train/dev/test 划分与泄漏检查。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from a2a_dygrade_rl.utils.io import write_csv, write_jsonl
from a2a_dygrade_rl.utils.seed import set_seed
from a2a_dygrade_rl.utils.validation import validate_no_split_leakage


def _split_counts(total: int, ratios: dict[str, float]) -> tuple[int, int, int]:
    if total <= 0:
        return 0, 0, 0
    if total == 1:
        return 1, 0, 0
    if total == 2:
        return 1, 0, 1
    train_count = int(total * float(ratios.get("train", 0.7)))
    dev_count = int(total * float(ratios.get("dev", 0.1)))
    if train_count <= 0:
        train_count = 1
    if dev_count <= 0:
        dev_count = 1
    if train_count + dev_count >= total:
        train_count = max(1, total - 2)
        dev_count = 1
    test_count = total - train_count - dev_count
    if test_count <= 0:
        test_count = 1
        train_count = max(1, train_count - 1)
    return train_count, dev_count, test_count


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def _leakage_components(items: list[dict]) -> dict[str, list[dict]]:
    dsu = _DisjointSet(len(items))
    prompt_seen: dict[str, int] = {}
    exact_seen: dict[str, int] = {}
    for index, item in enumerate(items):
        prompt_group = _normalized_text(item.get("metadata", {}).get("prompt_group") or item.get("prompt"))
        exact_key = "\n".join(
            [
                _normalized_text(item.get("dataset")),
                _normalized_text(item.get("prompt")),
                _normalized_text(item.get("student_answer")),
            ]
        )
        if prompt_group in prompt_seen:
            dsu.union(prompt_seen[prompt_group], index)
        else:
            prompt_seen[prompt_group] = index
        if exact_key in exact_seen:
            dsu.union(exact_seen[exact_key], index)
        else:
            exact_seen[exact_key] = index
    grouped: dict[int, list[dict]] = defaultdict(list)
    for index, item in enumerate(items):
        grouped[dsu.find(index)].append(item)
    components: dict[str, list[dict]] = {}
    for group_items in grouped.values():
        component_id = "|".join(sorted(str(item["item_id"]) for item in group_items)[:3])
        components[component_id] = group_items
    return components


def assign_prompt_splits(items: list[dict], ratios: dict[str, float], seed: int, rule_version: str) -> list[dict]:
    rng = set_seed(seed)
    dataset_items: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        dataset_items[str(item["dataset"])].append(item)
    split_items = []
    for dataset in sorted(dataset_items):
        groups = _leakage_components(dataset_items[dataset])
        component_ids = sorted(groups)
        rng.shuffle(component_ids)
        train_count, dev_count, _ = _split_counts(len(component_ids), ratios)
        split_by_group = {}
        for index, group in enumerate(component_ids):
            if index < train_count:
                split = "train"
            elif index < train_count + dev_count:
                split = "dev"
            else:
                split = "test"
            split_by_group[group] = split
        for group in component_ids:
            for item in groups[group]:
                copied = dict(item)
                copied["metadata"] = dict(item.get("metadata", {}))
                copied["metadata"].update(
                    {
                        "split": split_by_group[group],
                        "split_seed": seed,
                        "split_rule_version": rule_version,
                        "split_scope": "dataset_aware_prompt_exact_answer",
                        "dataset_prompt_group_count": len(component_ids),
                        "leakage_component_id": group,
                    }
                )
                split_items.append(copied)
    validate_no_split_leakage(split_items)
    return sorted(split_items, key=lambda row: row["item_id"])


def write_split_items(items: list[dict], output_dir: str | Path, overwrite: bool = False) -> dict[str, Path]:
    output = Path(output_dir)
    paths: dict[str, Path] = {}
    for split in ("train", "dev", "test"):
        split_rows = [item for item in items if item["metadata"]["split"] == split]
        paths[split] = write_jsonl(output / f"items_{split}.jsonl", split_rows, overwrite=overwrite)
    manifest_rows = [
        {
            "item_id": item["item_id"],
            "dataset": item["dataset"],
            "prompt_group": item["metadata"].get("prompt_group", ""),
            "paper_id": "",
            "split": item["metadata"]["split"],
            "seed": item["metadata"]["split_seed"],
            "rule_version": item["metadata"]["split_rule_version"],
            "split_scope": item["metadata"].get("split_scope", ""),
        }
        for item in items
    ]
    write_csv(
        output / "split_manifest.csv",
        manifest_rows,
        ["item_id", "dataset", "prompt_group", "paper_id", "split", "seed", "rule_version", "split_scope"],
        overwrite=overwrite,
    )
    return paths
