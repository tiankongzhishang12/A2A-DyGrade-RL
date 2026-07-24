from pathlib import Path

from a2a_dygrade_rl.datasets.build_items import build_items
from a2a_dygrade_rl.datasets.build_papers import build_papers
from a2a_dygrade_rl.datasets.split import assign_prompt_splits
from a2a_dygrade_rl.utils.io import read_jsonl, write_yaml
from a2a_dygrade_rl.utils.io import write_jsonl
from a2a_dygrade_rl.utils.validation import validate_no_split_leakage


def test_data_pipeline_builds_items_and_papers(tmp_path):
    config = {
        "run": {"seed": 7, "rule_version": "test"},
        "datasets": [
            {
                "name": "dress",
                "enabled": True,
                "raw_path": "tests/fixtures/raw_smoke",
                "pattern": "*.jsonl",
                "question_type": "short_answer",
                "score_min": 0,
                "score_max": 5,
            }
        ],
        "splits": {"train": 0.5, "dev": 0.25, "test": 0.25},
        "paper": {
            "min_items": 1,
            "max_items": 5,
            "target_items": 2,
            "budgets": {"max_cost": 1, "max_latency": 1, "max_agent_calls": 2, "max_a2a_messages": 1},
        },
    }
    config_path = tmp_path / "dataset.yaml"
    write_yaml(config_path, config)
    build_items(config_path, tmp_path / "processed", "pytest_smoke", overwrite=True)
    all_items = []
    for split in ("train", "dev", "test"):
        all_items.extend(read_jsonl(tmp_path / "processed" / f"items_{split}.jsonl"))
    validate_no_split_leakage(all_items)
    paths = build_papers(config_path, tmp_path / "processed", tmp_path / "processed", "pytest_smoke", overwrite=True)
    assert Path(paths["train"]).exists()


def test_dataset_aware_prompt_split_keeps_each_dataset_in_test_when_possible():
    items = []
    for dataset in ("a", "b"):
        for group_index in range(10):
            for response_index in range(2):
                items.append(
                    {
                        "item_id": f"{dataset}_{group_index}_{response_index}",
                        "dataset": dataset,
                        "prompt": f"prompt {group_index}",
                        "metadata": {"prompt_group": f"{dataset}_prompt_{group_index}"},
                    }
                )
    split_items = assign_prompt_splits(items, {"train": 0.7, "dev": 0.1, "test": 0.2}, seed=7, rule_version="test")
    validate_no_split_leakage(split_items)
    by_dataset = {dataset: {"train": 0, "dev": 0, "test": 0} for dataset in ("a", "b")}
    for item in split_items:
        by_dataset[item["dataset"]][item["metadata"]["split"]] += 1
    assert all(counts["train"] > 0 and counts["dev"] > 0 and counts["test"] > 0 for counts in by_dataset.values())


def test_exact_prompt_answer_duplicates_stay_in_same_split():
    items = []
    for group_index in range(8):
        items.append(
            {
                "item_id": f"sas_{group_index}",
                "dataset": "sas_bench",
                "prompt": "same prompt" if group_index in {2, 5} else f"prompt {group_index}",
                "student_answer": "same answer" if group_index in {2, 5} else f"answer {group_index}",
                "metadata": {"prompt_group": f"prompt_group_{group_index}"},
            }
        )
    split_items = assign_prompt_splits(items, {"train": 0.5, "dev": 0.25, "test": 0.25}, seed=3, rule_version="test")
    duplicate_splits = {
        item["metadata"]["split"]
        for item in split_items
        if item["prompt"] == "same prompt" and item["student_answer"] == "same answer"
    }
    assert len(duplicate_splits) == 1


def test_build_papers_uses_strict_dataset_mix(tmp_path):
    config = {
        "run": {"seed": 11, "rule_version": "test"},
        "paper": {
            "min_items": 5,
            "max_items": 5,
            "target_items": 5,
            "mix_mode": "strict",
            "strict_quotas": [{"asap_sas": 2, "sas_bench": 2, "dress": 1}, {"asap_sas": 3, "sas_bench": 1, "dress": 1}],
            "budgets": {"max_cost": 1, "max_latency": 1, "max_agent_calls": 5, "max_a2a_messages": 2},
        },
    }
    config_path = tmp_path / "dataset.yaml"
    write_yaml(config_path, config)
    items = []
    for dataset, count in (("asap_sas", 6), ("sas_bench", 4), ("dress", 2)):
        for index in range(count):
            items.append(
                {
                    "item_id": f"{dataset}_{index}",
                    "dataset": dataset,
                    "question_type": "essay" if dataset == "dress" else "short_answer",
                    "prompt": f"{dataset} prompt {index}",
                    "metadata": {"split": "train", "prompt_group": f"{dataset}_pg_{index}", "split_scope": "test"},
                }
            )
    processed = tmp_path / "processed"
    write_jsonl(processed / "items_train.jsonl", items, overwrite=True)
    paths = build_papers(config_path, processed, processed, "pytest_strict", overwrite=True)
    papers = read_jsonl(paths["train"])
    assert len(papers) == 2
    for paper in papers:
        assert paper["metadata"]["mix_status"] == "strict"
        assert paper["metadata"]["dataset_mix"]["dress"] == 1
        assert paper["metadata"]["dataset_mix"]["asap_sas"] in {2, 3}
        assert paper["metadata"]["dataset_mix"]["sas_bench"] in {1, 2}
    manifest = (processed / "paper_manifest.csv").read_text(encoding="utf-8")
    assert "prompt_group" in manifest
    assert "paper_dataset_mix" in manifest
