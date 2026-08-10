"""V1.4 外部 train 主路由 Item 的内部 component 原子拆分。"""

from __future__ import annotations

import hashlib
import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.utils.io import (
    copy_config_snapshot,
    file_sha256,
    read_csv,
    read_jsonl,
    read_yaml,
    write_csv,
    write_json,
)
from a2a_dygrade_rl.utils.schemas import InternalItemSplitManifest
from a2a_dygrade_rl.utils.validation import validate_internal_item_split_manifest


DEFAULT_STRICT_QUOTAS: tuple[dict[str, int], ...] = (
    {"asap_sas": 2, "sas_bench": 2, "dress": 1},
    {"asap_sas": 3, "sas_bench": 1, "dress": 1},
)
INTERNAL_SPLITS = ("train_fit", "train_calibration")


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _stable_hash(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class InternalComponent:
    component_id: str
    dataset: str
    item_ids: tuple[str, ...]
    prompt_groups: tuple[str, ...]
    leakage_component_ids: tuple[str, ...]
    stable_hash: str

    @property
    def size(self) -> int:
        return len(self.item_ids)


@dataclass(frozen=True)
class InternalSplitResult:
    manifest_rows: list[dict[str, Any]]
    summary: dict[str, Any]
    components: tuple[InternalComponent, ...]


def build_internal_components(items: Iterable[dict[str, Any]]) -> tuple[InternalComponent, ...]:
    """按 dataset+prompt group、exact prompt-answer 与既有 leakage id 建传递分量。"""

    ordered = sorted((dict(item) for item in items), key=lambda row: str(row.get("item_id", "")))
    if not ordered:
        raise ValueError("内部拆分输入 Item 不能为空")
    item_ids = [str(item.get("item_id", "")) for item in ordered]
    if any(not item_id for item_id in item_ids):
        raise ValueError("内部拆分 Item 缺少 item_id")
    duplicate_ids = sorted(item_id for item_id, count in Counter(item_ids).items() if count > 1)
    if duplicate_ids:
        raise ValueError(f"内部拆分输入存在重复 item_id: {duplicate_ids[:10]}")

    for item in ordered:
        source_split = str(item.get("metadata", {}).get("split", ""))
        if source_split != "train":
            raise ValueError(f"内部拆分仅允许外部 train Item: {item['item_id']} split={source_split or 'missing'}")
        if not str(item.get("dataset", "")).strip():
            raise ValueError(f"内部拆分 Item 缺少 dataset: {item['item_id']}")

    dsu = _DisjointSet(len(ordered))
    prompt_seen: dict[tuple[str, str], int] = {}
    exact_seen: dict[tuple[str, str, str], int] = {}
    leakage_seen: dict[tuple[str, str], int] = {}

    def connect(mapping: dict[Any, int], key: Any, index: int) -> None:
        if not key or (isinstance(key, tuple) and any(not value for value in key)):
            return
        previous = mapping.get(key)
        if previous is None:
            mapping[key] = index
        else:
            dsu.union(previous, index)

    for index, item in enumerate(ordered):
        metadata = item.get("metadata", {})
        dataset = _normalized_text(item.get("dataset"))
        prompt_group = _normalized_text(metadata.get("prompt_group") or item.get("prompt"))
        exact_key = (
            dataset,
            _normalized_text(item.get("prompt")),
            _normalized_text(item.get("student_answer")),
        )
        leakage_id = _normalized_text(metadata.get("leakage_component_id"))
        connect(prompt_seen, (dataset, prompt_group), index)
        connect(exact_seen, exact_key, index)
        if leakage_id:
            connect(leakage_seen, (dataset, leakage_id), index)

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(ordered):
        groups[dsu.find(index)].append(item)

    components: list[InternalComponent] = []
    for group_items in groups.values():
        datasets = {str(item["dataset"]) for item in group_items}
        if len(datasets) != 1:
            raise ValueError(f"内部 leakage component 跨 dataset: {sorted(datasets)}")
        ids = tuple(sorted(str(item["item_id"]) for item in group_items))
        prompt_groups = tuple(
            sorted(
                {
                    str(item.get("metadata", {}).get("prompt_group") or item.get("prompt") or "")
                    for item in group_items
                }
            )
        )
        leakage_ids = tuple(
            sorted(
                {
                    str(item.get("metadata", {}).get("leakage_component_id") or "")
                    for item in group_items
                    if str(item.get("metadata", {}).get("leakage_component_id") or "").strip()
                }
            )
        )
        digest = _stable_hash("internal_component_v1.4", *ids)
        components.append(
            InternalComponent(
                component_id=f"ic_{digest[:20]}",
                dataset=next(iter(datasets)),
                item_ids=ids,
                prompt_groups=prompt_groups,
                leakage_component_ids=leakage_ids,
                stable_hash=digest,
            )
        )
    return tuple(sorted(components, key=lambda component: (component.dataset, component.stable_hash)))


class _SubsetIndex:
    """组件大小的确定性 subset-sum 索引，并保留可重建前驱。"""

    def __init__(self, components: list[InternalComponent], seed: int) -> None:
        self.components = sorted(
            components,
            key=lambda component: (_stable_hash(seed, component.stable_hash), component.component_id),
        )
        self.total = sum(component.size for component in self.components)
        self._reachable_bits = 1
        self._predecessor: dict[int, tuple[int, int]] = {}
        mask = (1 << (self.total + 1)) - 1
        for index, component in enumerate(self.components):
            shifted = (self._reachable_bits << component.size) & mask
            new_bits = shifted & ~self._reachable_bits
            cursor = new_bits
            while cursor:
                lowest = cursor & -cursor
                value = lowest.bit_length() - 1
                self._predecessor[value] = (value - component.size, index)
                cursor ^= lowest
            self._reachable_bits |= shifted

    def contains(self, value: int) -> bool:
        return 0 <= value <= self.total and bool((self._reachable_bits >> value) & 1)

    def reachable_values(self, *, exclude_edges: bool = False) -> list[int]:
        start = 1 if exclude_edges else 0
        end = self.total if exclude_edges else self.total + 1
        return [value for value in range(start, end) if self.contains(value)]

    def select(self, value: int) -> set[str]:
        if not self.contains(value):
            raise ValueError(f"不可达 component Item 数: {value}")
        selected: set[str] = set()
        cursor = value
        while cursor:
            previous, index = self._predecessor[cursor]
            selected.add(self.components[index].component_id)
            cursor = previous
        return selected


def strict_paper_plan(counts: dict[str, int], quotas: tuple[dict[str, int], ...]) -> tuple[int, tuple[int, ...], dict[str, int]]:
    """返回可构造的最大 Paper 数、各 quota 数和消耗量。"""

    datasets = tuple(sorted({dataset for quota in quotas for dataset in quota}))
    if not quotas:
        return 0, (), {dataset: 0 for dataset in datasets}
    if len(quotas) > 2:
        raise ValueError("当前 strict planner 只支持至多两种预注册 quota")

    def feasible_count(quota: dict[str, int], available: dict[str, int]) -> int:
        return min((available.get(dataset, 0) // count for dataset, count in quota.items() if count > 0), default=0)

    best: tuple[int, tuple[int, ...], dict[str, int]] | None = None
    if len(quotas) == 1:
        number = feasible_count(quotas[0], counts)
        used = {dataset: number * quotas[0].get(dataset, 0) for dataset in datasets}
        return number, (number,), used

    first, second = quotas
    max_first = feasible_count(first, counts)
    for first_count in range(max_first + 1):
        remaining = {
            dataset: counts.get(dataset, 0) - first_count * first.get(dataset, 0)
            for dataset in datasets
        }
        second_count = feasible_count(second, remaining)
        used = {
            dataset: first_count * first.get(dataset, 0) + second_count * second.get(dataset, 0)
            for dataset in datasets
        }
        candidate = (first_count + second_count, (first_count, second_count), used)
        if best is None:
            best = candidate
            continue
        # Paper 数优先；并列时总 leftover、dataset leftover 最大值及 quota 计数稳定排序。
        best_left = [counts.get(dataset, 0) - best[2].get(dataset, 0) for dataset in datasets]
        candidate_left = [counts.get(dataset, 0) - used.get(dataset, 0) for dataset in datasets]
        best_key = (-best[0], sum(best_left), max(best_left, default=0), best[1])
        candidate_key = (-candidate[0], sum(candidate_left), max(candidate_left, default=0), candidate[1])
        if candidate_key < best_key:
            best = candidate
    assert best is not None
    return best


def _find_full_use_allocation(
    indexes: dict[str, _SubsetIndex],
    totals: dict[str, int],
    quotas: tuple[dict[str, int], ...],
    calibration_ratio: float,
    seed: int,
) -> dict[str, int] | None:
    total_papers, global_quota_counts, used = strict_paper_plan(totals, quotas)
    if total_papers <= 1 or any(used.get(dataset, 0) != totals.get(dataset, 0) for dataset in totals):
        return None

    target_papers = total_papers * calibration_ratio
    paper_candidates = sorted(
        range(1, total_papers),
        key=lambda count: (abs(count - target_papers), _stable_hash(seed, "paper_count", count)),
    )
    datasets = tuple(sorted(totals))

    for calibration_papers in paper_candidates:
        quota_vectors: Iterable[tuple[int, ...]]
        if len(quotas) == 1:
            if calibration_papers > global_quota_counts[0]:
                continue
            quota_vectors = ((calibration_papers,),)
        else:
            first_min = max(0, calibration_papers - global_quota_counts[1])
            first_max = min(calibration_papers, global_quota_counts[0])
            quota_vectors = (
                (first_count, calibration_papers - first_count)
                for first_count in range(first_min, first_max + 1)
            )

        feasible: list[tuple[tuple[Any, ...], dict[str, int]]] = []
        for quota_counts in quota_vectors:
            calibration_counts = {
                dataset: sum(quota_counts[index] * quotas[index].get(dataset, 0) for index in range(len(quotas)))
                for dataset in datasets
            }
            if any(value <= 0 or value >= totals[dataset] for dataset, value in calibration_counts.items()):
                continue
            if not all(indexes[dataset].contains(calibration_counts[dataset]) for dataset in datasets):
                continue
            per_dataset_deviation = sum(
                abs(calibration_counts[dataset] - totals[dataset] * calibration_ratio) for dataset in datasets
            )
            tie_hash = _stable_hash(seed, "full_use", *quota_counts)
            feasible.append(((per_dataset_deviation, tie_hash), calibration_counts))
        if feasible:
            return min(feasible, key=lambda row: row[0])[1]
    return None


def _fallback_allocation(
    indexes: dict[str, _SubsetIndex],
    totals: dict[str, int],
    quotas: tuple[dict[str, int], ...],
    calibration_ratio: float,
    seed: int,
) -> dict[str, int]:
    datasets = tuple(sorted(totals))
    candidates: dict[str, list[int]] = {}
    for dataset in datasets:
        target = totals[dataset] * calibration_ratio
        reachable = indexes[dataset].reachable_values(exclude_edges=True)
        candidates[dataset] = sorted(
            reachable,
            key=lambda value: (abs(value - target), _stable_hash(seed, dataset, value)),
        )[:64]
    if any(not values for values in candidates.values()):
        raise ValueError("无法让 train_fit/train_calibration 同时覆盖全部数据集")

    target_total = sum(totals.values()) * calibration_ratio
    best: tuple[tuple[Any, ...], dict[str, int]] | None = None
    for values in itertools.product(*(candidates[dataset] for dataset in datasets)):
        calibration_counts = dict(zip(datasets, values))
        fit_counts = {dataset: totals[dataset] - calibration_counts[dataset] for dataset in datasets}
        calibration_papers = strict_paper_plan(calibration_counts, quotas)[0]
        fit_papers = strict_paper_plan(fit_counts, quotas)[0]
        if calibration_papers <= 0 or fit_papers <= 0:
            continue
        ratio_deviation = abs(sum(values) - target_total)
        per_dataset_deviation = sum(
            abs(calibration_counts[dataset] - totals[dataset] * calibration_ratio) for dataset in datasets
        )
        key = (
            -(calibration_papers + fit_papers),
            ratio_deviation,
            per_dataset_deviation,
            _stable_hash(seed, "fallback", *values),
        )
        if best is None or key < best[0]:
            best = (key, calibration_counts)
    if best is None:
        raise ValueError("在 component 完整约束下无法同时构造 train_fit/train_calibration strict Paper")
    return best[1]


def allocate_internal_item_splits(
    items: Iterable[dict[str, Any]],
    *,
    train_fit_ratio: float = 0.8,
    seed: int = 20260729,
    rule_version: str = "internal_item_component_v1.4",
    strict_quotas: Iterable[dict[str, int]] = DEFAULT_STRICT_QUOTAS,
    assignment_unit: str = "item_component",
    source_paper_ids_by_item: dict[str, set[str]] | None = None,
) -> InternalSplitResult:
    if assignment_unit != "item_component":
        raise ValueError("禁止直接拆分旧 Paper；内部拆分必须以 item_component 为分配单元")
    if not 0.0 < train_fit_ratio < 1.0:
        raise ValueError("train_fit_ratio 必须位于 (0,1)")
    calibration_ratio = round(1.0 - train_fit_ratio, 12)
    item_list = sorted((dict(item) for item in items), key=lambda row: str(row["item_id"]))
    components = build_internal_components(item_list)
    item_by_id = {str(item["item_id"]): item for item in item_list}
    quota_tuple = tuple({str(key): int(value) for key, value in quota.items()} for quota in strict_quotas)
    expected_datasets = tuple(sorted({dataset for quota in quota_tuple for dataset in quota}))

    by_dataset: dict[str, list[InternalComponent]] = defaultdict(list)
    for component in components:
        by_dataset[component.dataset].append(component)
    missing_datasets = sorted(set(expected_datasets) - set(by_dataset))
    unexpected_datasets = sorted(set(by_dataset) - set(expected_datasets))
    if missing_datasets or unexpected_datasets:
        raise ValueError(f"strict dataset 覆盖不匹配: missing={missing_datasets}, unexpected={unexpected_datasets}")
    if any(len(by_dataset[dataset]) < 2 for dataset in expected_datasets):
        raise ValueError("每个数据集至少需要两个独立 component 才能覆盖两个内部 split")

    indexes = {dataset: _SubsetIndex(by_dataset[dataset], seed) for dataset in expected_datasets}
    totals = {dataset: indexes[dataset].total for dataset in expected_datasets}
    calibration_counts = _find_full_use_allocation(indexes, totals, quota_tuple, calibration_ratio, seed)
    allocation_mode = "full_use_strict_exact"
    if calibration_counts is None:
        calibration_counts = _fallback_allocation(indexes, totals, quota_tuple, calibration_ratio, seed)
        allocation_mode = "max_papers_then_ratio_fallback"

    calibration_component_ids: set[str] = set()
    for dataset, count in calibration_counts.items():
        calibration_component_ids.update(indexes[dataset].select(count))

    component_by_item = {
        item_id: component
        for component in components
        for item_id in component.item_ids
    }
    source_paper_ids_by_item = source_paper_ids_by_item or {}
    manifest_rows: list[dict[str, Any]] = []
    for item_id in sorted(item_by_id):
        item = item_by_id[item_id]
        component = component_by_item[item_id]
        metadata = item.get("metadata", {})
        internal_split = "train_calibration" if component.component_id in calibration_component_ids else "train_fit"
        record = InternalItemSplitManifest(
            item_id=item_id,
            dataset=str(item["dataset"]),
            prompt_group=str(metadata.get("prompt_group") or item.get("prompt") or ""),
            leakage_component_id=str(metadata.get("leakage_component_id") or ""),
            component_id=component.component_id,
            component_size=component.size,
            source_split="train",
            internal_split=internal_split,
            seed=seed,
            rule_version=rule_version,
            assignment_unit="item_component",
            stable_hash=component.stable_hash,
            source_paper_ids=";".join(sorted(source_paper_ids_by_item.get(item_id, set()))),
        ).to_dict()
        manifest_rows.append(record)
    validate_internal_item_split_manifest(manifest_rows)

    split_dataset_counts: dict[str, Counter[str]] = {
        split: Counter(row["dataset"] for row in manifest_rows if row["internal_split"] == split)
        for split in INTERNAL_SPLITS
    }
    split_counts = {split: sum(counts.values()) for split, counts in split_dataset_counts.items()}
    paper_potential = {
        split: strict_paper_plan(dict(split_dataset_counts[split]), quota_tuple)[0]
        for split in INTERNAL_SPLITS
    }
    total_items = len(manifest_rows)
    summary = {
        "source_item_count": total_items,
        "component_count": len(components),
        "assignment_unit": "item_component",
        "legacy_paper_assignment_count": 0,
        "target_train_fit_ratio": train_fit_ratio,
        "target_train_calibration_ratio": calibration_ratio,
        "train_fit_item_count": split_counts["train_fit"],
        "train_calibration_item_count": split_counts["train_calibration"],
        "train_fit_ratio": split_counts["train_fit"] / total_items,
        "train_calibration_ratio": split_counts["train_calibration"] / total_items,
        "absolute_ratio_deviation": abs(split_counts["train_fit"] / total_items - train_fit_ratio),
        "dataset_counts": {split: dict(sorted(counts.items())) for split, counts in split_dataset_counts.items()},
        "strict_paper_potential": paper_potential,
        "allocation_mode": allocation_mode,
        "seed": seed,
        "rule_version": rule_version,
        "optimization_priority": [
            "component_integrity",
            "both_splits_cover_all_datasets_and_support_strict_papers",
            "maximize_total_strict_five_item_papers",
            "minimize_target_ratio_deviation",
            "stable_hash_tie_break",
        ],
    }
    return InternalSplitResult(manifest_rows=manifest_rows, summary=summary, components=components)


def _load_train_scope(
    items_path: str | Path,
    paper_manifest_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    paper_rows = read_csv(paper_manifest_path)
    train_rows = [row for row in paper_rows if str(row.get("split", "")) == "train"]
    if not train_rows:
        raise ValueError("paper_manifest 中没有 train 主路由 Item")
    splits_by_item: dict[str, set[str]] = defaultdict(set)
    for row in paper_rows:
        splits_by_item[str(row.get("item_id", ""))].add(str(row.get("split", "")))
    scope_ids = {str(row["item_id"]) for row in train_rows}
    leaked_scope_ids = sorted(item_id for item_id in scope_ids if splits_by_item[item_id] != {"train"})
    if leaked_scope_ids:
        raise ValueError(f"train 主路由 Item 同时出现在 dev/test manifest: {leaked_scope_ids[:10]}")
    source_papers: dict[str, set[str]] = defaultdict(set)
    for row in train_rows:
        source_papers[str(row["item_id"])].add(str(row.get("paper_id", "")))

    all_train_items = read_jsonl(items_path)
    item_ids = [str(item.get("item_id", "")) for item in all_train_items]
    duplicate_item_ids = sorted(item_id for item_id, count in Counter(item_ids).items() if count > 1)
    if duplicate_item_ids:
        raise ValueError(f"items_train.jsonl 存在重复 item_id: {duplicate_item_ids[:10]}")
    by_id = {str(item["item_id"]): item for item in all_train_items}
    missing = sorted(scope_ids - set(by_id))
    if missing:
        raise ValueError(f"paper_manifest 引用的 train Item 不存在: {missing[:10]}")
    selected = [by_id[item_id] for item_id in sorted(scope_ids)]
    return selected, source_papers


def build_internal_split(
    config_path: str | Path,
    items_path: str | Path,
    paper_manifest_path: str | Path,
    output_dir: str | Path,
    run_id: str,
    *,
    seed: int | None = None,
    overwrite: bool = False,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Any]:
    config = read_yaml(config_path)
    split_config = config.get("internal_split", {})
    assignment_unit = str(split_config.get("assignment_unit", "item_component"))
    if assignment_unit != "item_component" or split_config.get("legacy_paper_assignment") not in {None, "forbidden"}:
        raise ValueError("禁止直接拆分旧 Paper；请使用 item_component internal split")
    effective_seed = int(seed if seed is not None else split_config.get("seed", 20260729))
    train_fit_ratio = float(split_config.get("train_fit_ratio", 0.8))
    rule_version = str(split_config.get("rule_version", "internal_item_component_v1.4"))
    strict_quotas = config.get("paper", {}).get("strict_quotas", DEFAULT_STRICT_QUOTAS)

    selected_items, source_papers = _load_train_scope(items_path, paper_manifest_path)
    expected_count = split_config.get("expected_source_item_count")
    if expected_count is not None and len(selected_items) != int(expected_count):
        raise ValueError(
            f"train 主路由 Item 数与冻结范围不一致: {len(selected_items)} != {int(expected_count)}"
        )
    result = allocate_internal_item_splits(
        selected_items,
        train_fit_ratio=train_fit_ratio,
        seed=effective_seed,
        rule_version=rule_version,
        strict_quotas=strict_quotas,
        assignment_unit=assignment_unit,
        source_paper_ids_by_item=source_papers,
    )

    output_path = Path(output_dir) / "internal_item_split_manifest.csv"
    fieldnames = list(InternalItemSplitManifest.__dataclass_fields__)
    write_csv(output_path, result.manifest_rows, fieldnames, overwrite=overwrite)
    result.summary["input_artifacts"] = {
        "items_train_sha256": file_sha256(items_path),
        "external_paper_manifest_sha256": file_sha256(paper_manifest_path),
        "dataset_config_sha256": file_sha256(config_path),
    }
    result.summary["output_artifacts"] = {
        "internal_item_split_manifest_sha256": file_sha256(output_path),
    }
    report_path = Path(output_root) / run_id / "reports" / "internal_split_summary.json"
    write_json(report_path, result.summary, overwrite=overwrite)
    copy_config_snapshot(config_path, run_id, output_root=output_root)
    return {"manifest": output_path, "summary": report_path, "result": result}
