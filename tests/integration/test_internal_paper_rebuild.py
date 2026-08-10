from __future__ import annotations

from collections import Counter
import hashlib

import pytest

from a2a_dygrade_rl.datasets.audit_internal_split import audit_internal_split
from a2a_dygrade_rl.datasets.build_internal_papers import rebuild_internal_papers


def _fixture() -> tuple[list[dict], list[dict]]:
    items: list[dict] = []
    manifest: list[dict] = []
    mixes = {
        "train_fit": (("asap_sas", 3), ("sas_bench", 1), ("dress", 1)),
        "train_calibration": (("asap_sas", 2), ("sas_bench", 2), ("dress", 1)),
    }
    counter = 0
    for split, dataset_counts in mixes.items():
        for dataset, count in dataset_counts:
            for _ in range(count):
                item_id = f"item_{counter:02d}"
                prompt_group = f"{dataset}_pg_{counter:02d}"
                stable_hash = hashlib.sha256(
                    f"internal_component_v1.4\x1f{item_id}".encode("utf-8")
                ).hexdigest()
                component_id = f"ic_{stable_hash[:20]}"
                items.append(
                    {
                        "item_id": item_id,
                        "dataset": dataset,
                        "question_type": "essay" if dataset == "dress" else "short_answer",
                        "prompt": f"prompt {counter}",
                        "student_answer": f"answer {counter}",
                        "reference_answer": "reference",
                        "rubric": "rubric",
                        "gold_score": 1.0,
                        "score_min": 0.0,
                        "score_max": 5.0,
                        "metadata": {"split": "train", "prompt_group": prompt_group},
                    }
                )
                manifest.append(
                    {
                        "item_id": item_id,
                        "dataset": dataset,
                        "prompt_group": prompt_group,
                        "leakage_component_id": component_id,
                        "component_id": component_id,
                        "component_size": 1,
                        "source_split": "train",
                        "internal_split": split,
                        "seed": 13,
                        "rule_version": "test",
                        "assignment_unit": "item_component",
                        "stable_hash": stable_hash,
                        "source_paper_ids": "paper_train_00000",
                    }
                )
                counter += 1
    return items, manifest


def test_internal_papers_are_rebuilt_separately_with_new_ids_and_strict_mix():
    items, manifest = _fixture()
    result = rebuild_internal_papers(
        items,
        manifest,
        strict_quotas=[
            {"asap_sas": 2, "sas_bench": 2, "dress": 1},
            {"asap_sas": 3, "sas_bench": 1, "dress": 1},
        ],
        budget={
            "max_cost": 1.0,
            "max_elapsed_time": 10.0,
            "max_agent_calls": 5,
            "max_a2a_exchanges": 2,
        },
        seed=13,
        rule_version="internal_paper_v14",
    )

    all_papers = result.papers_by_split["train_fit"] + result.papers_by_split["train_calibration"]
    assert len(all_papers) == 2
    assert result.leftover_rows == []
    assert all(len(paper["items"]) == 5 for paper in all_papers)
    assert {paper["paper_id"].split("_00000")[0] for paper in all_papers} == {"paper_train_fit", "paper_train_calibration"}
    assert all(paper["paper_id"] != "paper_train_00000" for paper in all_papers)
    assert all(paper["metadata"]["mix_status"] == "strict" for paper in all_papers)
    assert len({item_id for paper in all_papers for item_id in paper["items"]}) == 10

    item_by_id = {item["item_id"]: item for item in items}
    split_by_item = {row["item_id"]: row["internal_split"] for row in manifest}
    for paper in all_papers:
        split = paper["metadata"]["internal_split"]
        assert all(split_by_item[item_id] == split for item_id in paper["items"])
        counts = Counter(item_by_id[item_id]["dataset"] for item_id in paper["items"])
        assert counts in (
            Counter({"asap_sas": 3, "sas_bench": 1, "dress": 1}),
            Counter({"asap_sas": 2, "sas_bench": 2, "dress": 1}),
        )

    audit = audit_internal_split(
        items=items,
        item_manifest_rows=manifest,
        papers_by_split=result.papers_by_split,
        paper_manifest_rows=result.paper_manifest_rows,
        leftover_rows=result.leftover_rows,
        strict_quotas=[
            {"asap_sas": 2, "sas_bench": 2, "dress": 1},
            {"asap_sas": 3, "sas_bench": 1, "dress": 1},
        ],
        external_paper_ids={"paper_train_00000"},
    )
    assert audit.passed
    for key in (
        "legacy_paper_assignment_count",
        "item_overlap_count",
        "prompt_group_overlap_count",
        "component_overlap_count",
        "paper_overlap_count",
        "cross_split_reference_count",
        "non_five_item_paper_count",
        "strict_mix_violation_count",
        "duplicate_item_reference_count",
    ):
        assert audit.summary[key] == 0


def test_internal_paper_builder_rejects_direct_legacy_paper_split():
    items, manifest = _fixture()
    manifest[0]["assignment_unit"] = "legacy_paper"
    with pytest.raises(ValueError, match="禁止直接拆分旧 Paper"):
        rebuild_internal_papers(
            items,
            manifest,
            strict_quotas=[{"asap_sas": 3, "sas_bench": 1, "dress": 1}],
            budget={
                "max_cost": 1.0,
                "max_elapsed_time": 10.0,
                "max_agent_calls": 5,
                "max_a2a_exchanges": 2,
            },
            seed=13,
            rule_version="test",
        )


def test_internal_audit_blocks_cross_split_reference_and_duplicate_item():
    items, manifest = _fixture()
    result = rebuild_internal_papers(
        items,
        manifest,
        strict_quotas=[
            {"asap_sas": 2, "sas_bench": 2, "dress": 1},
            {"asap_sas": 3, "sas_bench": 1, "dress": 1},
        ],
        budget={
            "max_cost": 1.0,
            "max_elapsed_time": 10.0,
            "max_agent_calls": 5,
            "max_a2a_exchanges": 2,
        },
        seed=13,
        rule_version="test",
    )
    tampered = {split: [dict(paper) for paper in papers] for split, papers in result.papers_by_split.items()}
    tampered["train_fit"][0] = dict(tampered["train_fit"][0])
    tampered["train_fit"][0]["items"] = list(tampered["train_fit"][0]["items"])
    tampered["train_fit"][0]["items"][0] = tampered["train_calibration"][0]["items"][0]
    audit = audit_internal_split(
        items=items,
        item_manifest_rows=manifest,
        papers_by_split=tampered,
        paper_manifest_rows=result.paper_manifest_rows,
        leftover_rows=result.leftover_rows,
        strict_quotas=[
            {"asap_sas": 2, "sas_bench": 2, "dress": 1},
            {"asap_sas": 3, "sas_bench": 1, "dress": 1},
        ],
        external_paper_ids={"paper_train_00000"},
    )
    assert audit.passed is False
    assert audit.summary["cross_split_reference_count"] == 1
    assert audit.summary["duplicate_item_reference_count"] == 1


def test_internal_paper_leftover_is_explicitly_traceable():
    items, manifest = _fixture()
    item_id = "extra_sas"
    stable_hash = hashlib.sha256(
        f"internal_component_v1.4\x1f{item_id}".encode("utf-8")
    ).hexdigest()
    component_id = f"ic_{stable_hash[:20]}"
    items.append({
        "item_id": item_id,
        "dataset": "sas_bench",
        "question_type": "short_answer",
        "prompt": "extra prompt",
        "student_answer": "extra answer",
        "reference_answer": "reference",
        "rubric": "rubric",
        "gold_score": 1.0,
        "score_min": 0.0,
        "score_max": 5.0,
        "metadata": {"split": "train", "prompt_group": "extra_pg"},
    })
    manifest.append({
        "item_id": item_id,
        "dataset": "sas_bench",
        "prompt_group": "extra_pg",
        "leakage_component_id": "extra_legacy",
        "component_id": component_id,
        "component_size": 1,
        "source_split": "train",
        "internal_split": "train_fit",
        "seed": 13,
        "rule_version": "test",
        "assignment_unit": "item_component",
        "stable_hash": stable_hash,
        "source_paper_ids": "paper_train_00001",
    })
    result = rebuild_internal_papers(
        items,
        manifest,
        strict_quotas=[
            {"asap_sas": 2, "sas_bench": 2, "dress": 1},
            {"asap_sas": 3, "sas_bench": 1, "dress": 1},
        ],
        budget={
            "max_cost": 1.0,
            "max_elapsed_time": 10.0,
            "max_agent_calls": 5,
            "max_a2a_exchanges": 2,
        },
        seed=13,
        rule_version="test",
    )
    assert len(result.leftover_rows) == 1
    leftover = result.leftover_rows[0]
    source = {row["item_id"]: row for row in manifest}[leftover["item_id"]]
    assert leftover["internal_split"] == "train_fit"
    assert leftover["dataset"] == "sas_bench"
    assert leftover["component_id"] == source["component_id"]
    assert leftover["prompt_group"] == source["prompt_group"]
    assert leftover["reason"] == "strict_capacity_exhausted_without_cross_split_borrowing"
