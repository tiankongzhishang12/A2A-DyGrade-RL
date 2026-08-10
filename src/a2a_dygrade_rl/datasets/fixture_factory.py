"""完整 Fixture Smoke 的确定性数据工厂；产物永远不得用于论文结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.agents.agent_registry import build_agent_registry
from a2a_dygrade_rl.utils.io import read_yaml
from a2a_dygrade_rl.utils.schemas import Paper, PaperBudget


DATASET_LAYOUT = ("asap_sas", "asap_sas", "sas_bench", "sas_bench", "dress")
SCORE_RANGES = {
    "asap_sas": (0.0, 3.0),
    "sas_bench": (0.0, 5.0),
    "dress": (0.0, 15.0),
}
QUESTION_TYPES = {
    "asap_sas": "short_answer",
    "sas_bench": "short_answer",
    "dress": "essay",
}


class PairwiseFixtureConstraintNotMet(ValueError):
    """仅表示当前 nonce 未满足 Fixture Agent 差异约束。"""


def load_fixture_blueprint(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("blueprint_version") != "quality_constrained_fixture_v1":
        raise ValueError("未知 Fixture blueprint version")
    if int(data.get("items_per_paper", 0)) != 5:
        raise ValueError("完整 Fixture Smoke 必须固定5题 Paper")
    return data


def _base_item(
    *,
    item_id: str,
    dataset: str,
    split: str,
    prompt_group: str,
    paper_id: str,
    paper_index: int,
    position: int,
    nonce: int,
) -> dict[str, Any]:
    score_min, score_max = SCORE_RANGES[dataset]
    answer_length = 5 + ((paper_index * 7 + position * 11 + nonce * 3) % 42)
    answer_words = [f"word{(paper_index + position + offset) % 19}" for offset in range(answer_length)]
    return {
        "item_id": item_id,
        "dataset": dataset,
        "question_type": QUESTION_TYPES[dataset],
        "subject": "english",
        "prompt": f"Fixture prompt {split} {dataset} paper={paper_index} position={position} nonce={nonce}",
        "student_answer": " ".join(answer_words),
        "reference_answer": f"Fixture reference for {dataset}",
        "rubric": "clarity evidence correctness organization",
        "gold_score": score_min,
        "score_min": score_min,
        "score_max": score_max,
        "metadata": {
            "split": split,
            "prompt_group": prompt_group,
            "leakage_component_id": prompt_group,
            "fixture": True,
            "formal_eligible": False,
            "source_paper_id": paper_id,
            "paper_position": position,
        },
    }


def _assign_gold(
    item: dict[str, Any],
    *,
    registry: dict[str, Any],
    gold_agent: str,
    max_pairwise_error: float,
) -> dict[str, Any]:
    predictions = {agent_id: registry[agent_id].predict(item, {}) for agent_id in ("CheapAgent", "MidAgent", "StrongAgent")}
    span = float(item["score_max"]) - float(item["score_min"])
    pairwise = max(
        abs(float(predictions[left]["pred_score"]) - float(predictions[right]["pred_score"])) / span
        for left, right in (("CheapAgent", "MidAgent"), ("CheapAgent", "StrongAgent"), ("MidAgent", "StrongAgent"))
    )
    if pairwise > float(max_pairwise_error):
        raise PairwiseFixtureConstraintNotMet(f"pairwise_error={pairwise}")
    resolved = dict(item)
    resolved["gold_score"] = float(predictions[gold_agent]["pred_score"])
    resolved["metadata"] = {
        **resolved["metadata"],
        "fixture_gold_agent": gold_agent,
        "max_pairwise_agent_error": pairwise,
    }
    return resolved


def generate_quality_constrained_fixture(
    *,
    blueprint: dict[str, Any],
    agent_config_path: str | Path,
) -> dict[str, Any]:
    seed = int(blueprint["seed"])
    agent_config = read_yaml(agent_config_path)
    registry = build_agent_registry(agent_config, execution_mode="fixture_smoke", seed=seed)
    component_size = int(blueprint["component_size"])
    max_pairwise = float(blueprint["max_pairwise_agent_error"])
    gold_agent_by_dataset = {str(key): str(value) for key, value in blueprint["gold_agent_by_dataset"].items()}
    placeholder_budget = PaperBudget(
        max_cost=1.0,
        max_elapsed_time=120.0,
        max_agent_calls=20,
        max_a2a_exchanges=4,
    )

    items_by_split: dict[str, list[dict[str, Any]]] = {"train": [], "dev": [], "test": []}
    papers_by_split: dict[str, list[dict[str, Any]]] = {"dev": [], "test": []}
    external_manifests: dict[str, list[dict[str, Any]]] = {"dev": [], "test": []}
    source_paper_ids_by_item: dict[str, set[str]] = {}
    dataset_offsets = {split: {dataset: 0 for dataset in SCORE_RANGES} for split in items_by_split}
    split_paper_counts = {
        "train": int(blueprint["train_paper_count"]),
        "dev": int(blueprint["dev_paper_count"]),
        "test": int(blueprint["test_like_paper_count"]),
    }

    for split, paper_count in split_paper_counts.items():
        for paper_index in range(paper_count):
            paper_id = f"fixture_{split}_paper_{paper_index:04d}"
            paper_item_ids: list[str] = []
            for position, dataset in enumerate(DATASET_LAYOUT):
                dataset_index = dataset_offsets[split][dataset]
                dataset_offsets[split][dataset] += 1
                item_id = f"fixture_{split}_{dataset}_{dataset_index:05d}"
                if split == "train":
                    prompt_group = f"fixture_train_{dataset}_component_{dataset_index // component_size:04d}"
                else:
                    prompt_group = f"fixture_{split}_{dataset}_paper_{paper_index:04d}_position_{position}"
                selected: dict[str, Any] | None = None
                last_error = ""
                for nonce in range(256):
                    candidate = _base_item(
                        item_id=item_id,
                        dataset=dataset,
                        split=split,
                        prompt_group=prompt_group,
                        paper_id=paper_id,
                        paper_index=paper_index,
                        position=position,
                        nonce=nonce,
                    )
                    try:
                        selected = _assign_gold(
                            candidate,
                            registry=registry,
                            gold_agent=gold_agent_by_dataset[dataset],
                            max_pairwise_error=max_pairwise,
                        )
                        break
                    except PairwiseFixtureConstraintNotMet as exc:
                        last_error = str(exc)
                if selected is None:
                    raise RuntimeError(f"无法为 {item_id} 构造受控 Fixture Agent 差异: {last_error}")
                items_by_split[split].append(selected)
                paper_item_ids.append(item_id)
                source_paper_ids_by_item[item_id] = {paper_id}
                if split in external_manifests:
                    external_manifests[split].append(
                        {
                            "item_id": item_id,
                            "split": split,
                            "dataset": dataset,
                            "prompt_group": prompt_group,
                            "paper_id": paper_id,
                            "formal_eligible": False,
                        }
                    )
            if split in papers_by_split:
                papers_by_split[split].append(
                    Paper(
                        paper_id=paper_id,
                        items=paper_item_ids,
                        paper_budget=placeholder_budget,
                        metadata={"split": split, "fixture": True, "formal_eligible": False, "strict_quota_id": "fixture_2_2_1"},
                    ).to_dict()
                )

    return {
        "items_by_split": items_by_split,
        "papers_by_split": papers_by_split,
        "external_manifests": external_manifests,
        "source_paper_ids_by_item": source_paper_ids_by_item,
        "summary": {
            "blueprint_version": blueprint["blueprint_version"],
            "seed": seed,
            "item_counts": {split: len(rows) for split, rows in items_by_split.items()},
            "paper_counts": split_paper_counts,
            "formal_eligible": False,
            "online_agent_calls": 0,
        },
    }
