"""paper-level 样本构造。"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from a2a_dygrade_rl.utils.io import copy_config_snapshot, read_jsonl, read_yaml, write_csv, write_jsonl
from a2a_dygrade_rl.utils.schemas import Paper, PaperBudget
from a2a_dygrade_rl.utils.seed import set_seed
from a2a_dygrade_rl.utils.validation import validate_paper


def _mix_label(counts: Counter[str]) -> str:
    return ";".join(f"{dataset}:{counts[dataset]}" for dataset in sorted(counts))


def _build_relaxed_chunks(items: list[dict], target_items: int, min_items: int, max_items: int) -> list[list[dict]]:
    chunks = []
    for index in range(0, len(items), target_items):
        chunk = items[index : index + target_items]
        if len(chunk) < min_items or len(chunk) > max_items:
            continue
        chunks.append(chunk)
    return chunks


def _build_strict_chunks(items: list[dict], quotas: list[dict[str, int]]) -> list[tuple[list[dict], dict[str, int]]]:
    items_by_dataset: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        items_by_dataset[str(item["dataset"])].append(item)
    chunks: list[tuple[list[dict], dict[str, int]]] = []
    while True:
        feasible = [
            quota
            for quota in quotas
            if all(len(items_by_dataset[dataset]) >= count for dataset, count in quota.items())
        ]
        if not feasible:
            break
        # 选择构造后剩余数据集最均衡的 quota，减少某一短答数据集过早耗尽。
        quota = min(
            feasible,
            key=lambda candidate: max(len(items_by_dataset[d]) - c for d, c in candidate.items())
            - min(len(items_by_dataset[d]) - c for d, c in candidate.items()),
        )
        chunk: list[dict] = []
        for dataset in sorted(quota):
            count = int(quota[dataset])
            for _ in range(count):
                chunk.append(items_by_dataset[dataset].pop())
        chunks.append((chunk, dict(quota)))
    return chunks


def build_papers(config_path: str | Path, input_dir: str | Path, output_dir: str | Path, run_id: str, seed: int | None = None, overwrite: bool = False) -> dict[str, Path]:
    config = read_yaml(config_path)
    effective_seed = int(seed if seed is not None else config.get("run", {}).get("seed", 42))
    rng = set_seed(effective_seed)
    paper_config = config.get("paper", {})
    target_items = int(paper_config.get("target_items", 5))
    min_items = int(paper_config.get("min_items", 5))
    max_items = int(paper_config.get("max_items", 8))
    mix_mode = str(paper_config.get("mix_mode", "relaxed"))
    strict_quotas = [{str(k): int(v) for k, v in quota.items()} for quota in paper_config.get("strict_quotas", [])]
    budgets = paper_config.get("budgets", {})
    budget = PaperBudget(
        max_cost=float(budgets.get("max_cost", 0.2)),
        max_latency=float(budgets.get("max_latency", 30.0)),
        max_agent_calls=int(budgets.get("max_agent_calls", 12)),
        max_a2a_messages=int(budgets.get("max_a2a_messages", 6)),
    )
    paths: dict[str, Path] = {}
    manifest_rows: list[dict] = []
    for split in ("train", "dev", "test"):
        item_path = Path(input_dir) / f"items_{split}.jsonl"
        if not item_path.exists():
            continue
        items = read_jsonl(item_path)
        items_by_id = {item["item_id"]: item for item in items}
        rng.shuffle(items)
        papers = []
        if mix_mode == "strict" and strict_quotas:
            chunks = _build_strict_chunks(items, strict_quotas)
        else:
            chunks = [(chunk, {}) for chunk in _build_relaxed_chunks(items, target_items, min_items, max_items)]
        for chunk, quota in chunks:
            paper_id = f"paper_{split}_{len(papers):05d}"
            dataset_counts = Counter(str(item["dataset"]) for item in chunk)
            mix_status = "strict" if quota and all(dataset_counts.get(dataset, 0) == count for dataset, count in quota.items()) else "relaxed"
            deviation_reason = "" if mix_status == "strict" else "未配置 strict quota 或数据不足，使用 relaxed chunk 构造"
            paper = Paper(
                paper_id=paper_id,
                items=[item["item_id"] for item in chunk],
                paper_budget=budget,
                metadata={
                    "split": split,
                    "seed": effective_seed,
                    "construction_rule_version": str(config.get("run", {}).get("rule_version", "v1")),
                    "dataset_mix": dict(sorted(dataset_counts.items())),
                    "mix_status": mix_status,
                    "deviation_reason": deviation_reason,
                },
            ).to_dict()
            validate_paper(paper, items_by_id)
            papers.append(paper)
            for item_id in paper["items"]:
                item = items_by_id[item_id]
                manifest_rows.append(
                    {
                        "item_id": item_id,
                        "dataset": item["dataset"],
                        "question_type": item.get("question_type", ""),
                        "prompt_group": item.get("metadata", {}).get("prompt_group", ""),
                        "paper_id": paper_id,
                        "split": split,
                        "seed": effective_seed,
                        "rule_version": paper["metadata"]["construction_rule_version"],
                        "split_scope": item.get("metadata", {}).get("split_scope", ""),
                        "paper_dataset_mix": _mix_label(dataset_counts),
                        "mix_status": mix_status,
                        "deviation_reason": deviation_reason,
                    }
                )
        paths[split] = write_jsonl(Path(output_dir) / f"papers_{split}.jsonl", papers, overwrite=overwrite)
    write_csv(
        Path(output_dir) / "paper_manifest.csv",
        manifest_rows,
        [
            "item_id",
            "dataset",
            "question_type",
            "prompt_group",
            "paper_id",
            "split",
            "seed",
            "rule_version",
            "split_scope",
            "paper_dataset_mix",
            "mix_status",
            "deviation_reason",
        ],
        overwrite=overwrite,
    )
    copy_config_snapshot(config_path, run_id)
    return paths
