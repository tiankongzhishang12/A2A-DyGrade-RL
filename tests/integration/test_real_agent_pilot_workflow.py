from __future__ import annotations

import csv
from pathlib import Path

from a2a_dygrade_rl.agents.cache import run_agent_cache
from a2a_dygrade_rl.agents.pilot import build_real_pilot_sample
from a2a_dygrade_rl.utils.io import read_jsonl, write_jsonl, write_yaml


def _item(index: int) -> dict:
    return {
        "item_id": f"item_{index}",
        "dataset": ["asap_sas", "dress", "sas_bench"][index % 3],
        "question_type": "short_answer",
        "subject": "science",
        "prompt": f"prompt {index % 4}",
        "student_answer": f"answer {index}",
        "reference_answer": "reference",
        "rubric": "rubric",
        "gold_score": float(index % 4),
        "score_min": 0.0,
        "score_max": 3.0,
        "metadata": {"split": "train", "prompt_group": f"p{index % 4}", "answer_length": 10 + index},
    }


def _fixture_config() -> dict:
    agents = {}
    for key, agent_id in (
        ("cheap", "CheapAgent"),
        ("mid", "MidAgent"),
        ("strong", "StrongAgent"),
        ("evidence", "EvidenceAgent"),
        ("arbitrator", "ArbitratorAgent"),
    ):
        agents[key] = {
            "agent_id": agent_id,
            "mode": "fixture",
            "model_id": f"fixture-{key}",
            "model_revision": "r1",
            "prompt": key,
            "prompt_version": "v1",
            "cost": 0.001,
            "latency": 0.01,
        }
    return {
        "cache_schema_version": "1.0",
        "arbitrator_contexts": [["CheapAgent", "MidAgent"]],
        "agents": agents,
    }


def test_pilot_sample_is_20_strict_papers_without_gold_selection(tmp_path: Path):
    items = [_item(index) for index in range(125)]
    papers = []
    manifest_rows = []
    for paper_index in range(25):
        ids = [f"item_{paper_index * 5 + offset}" for offset in range(5)]
        papers.append(
            {
                "paper_id": f"paper_train_fit_{paper_index:05d}",
                "items": ids,
                "paper_budget": {"max_cost": 1, "max_elapsed_time": 1, "max_agent_calls": 12, "max_a2a_exchanges": 8},
                "metadata": {"internal_split": "train_fit", "mix_status": "strict"},
            }
        )
        for item_id in ids:
            manifest_rows.append(
                {
                    "item_id": item_id,
                    "dataset": "fixture",
                    "prompt_group": "p",
                    "leakage_component_id": item_id,
                    "component_id": item_id,
                    "component_size": "1",
                    "source_split": "train",
                    "internal_split": "train_fit",
                    "seed": "42",
                    "rule_version": "v1",
                    "assignment_unit": "item_component",
                    "stable_hash": "a" * 64,
                    "source_paper_ids": "",
                }
            )
    items_path = tmp_path / "items.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    internal_path = tmp_path / "internal.csv"
    write_jsonl(items_path, items)
    write_jsonl(papers_path, papers)
    with internal_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]))
        writer.writeheader()
        writer.writerows(manifest_rows)
    result = build_real_pilot_sample(
        papers_path=papers_path,
        items_path=items_path,
        internal_manifest_path=internal_path,
        run_id="real_pilot_sample_test",
        paper_count=20,
        seed=42,
        output_root=tmp_path / "outputs" / "runs",
    )
    assert result["paper_count"] == 20
    assert result["item_count"] == 100
    selected = read_jsonl(result["outputs"]["items_path"])
    assert len(selected) == 100
    assert all(row["metadata"]["split"] == "train_fit" for row in selected)
    assert all(row["metadata"]["formal_eligible"] is False for row in selected)


def test_checkpoint_resume_expands_with_same_fixed_sample(tmp_path: Path):
    items = [_item(index) for index in range(3)]
    items_path = tmp_path / "items.jsonl"
    config_path = tmp_path / "agents.yaml"
    write_jsonl(items_path, items)
    write_yaml(config_path, _fixture_config())
    common = {
        "config_path": config_path,
        "items_path": items_path,
        "split": "train",
        "run_id": "fixture_smoke_checkpoint_resume",
        "execution_mode": "fixture_smoke",
        "seed": 42,
        "sample_size": 3,
        "output_root": tmp_path / "outputs" / "runs",
    }
    first = run_agent_cache(checkpoint_item_limit=1, **common)
    assert first["completed_item_count"] == 1
    assert len(first["records"]) == 5
    second = run_agent_cache(checkpoint_item_limit=2, resume=True, **common)
    assert second["completed_item_count"] == 2
    assert len(second["records"]) == 10
    assert second["reused"] == 5


def test_recovery_journal_restores_records_missing_from_consolidated_cache(tmp_path: Path):
    items = [_item(index) for index in range(2)]
    items_path = tmp_path / "items.jsonl"
    config_path = tmp_path / "agents.yaml"
    output_root = tmp_path / "outputs" / "runs"
    run_id = "fixture_smoke_journal_recovery"
    write_jsonl(items_path, items)
    write_yaml(config_path, _fixture_config())
    common = {
        "config_path": config_path,
        "items_path": items_path,
        "split": "train",
        "run_id": run_id,
        "execution_mode": "fixture_smoke",
        "seed": 42,
        "sample_size": 2,
        "output_root": output_root,
    }
    first = run_agent_cache(checkpoint_item_limit=1, **common)
    assert len(first["records"]) == 5
    journal = output_root / run_id / "logs" / "cache_journal.train.jsonl"
    assert len(read_jsonl(journal)) == 5

    split_dir = output_root / run_id / "predictions" / "agent_cache" / "train"
    for path in split_dir.glob("*.jsonl"):
        path.unlink()

    resumed = run_agent_cache(checkpoint_item_limit=2, resume=True, **common)
    assert resumed["journal_recovered_records"] == 5
    assert resumed["reused"] == 5
    assert resumed["generated"] == 5
    assert len(resumed["records"]) == 10
