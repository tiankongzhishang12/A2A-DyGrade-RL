from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from a2a_dygrade_rl.agents.selfhosted_checkpoint import build_selfhosted_checkpoint_sample
from a2a_dygrade_rl.utils.io import read_jsonl, write_json, write_jsonl


def _item(item_id: str, dataset: str, *, image: bool = False) -> dict:
    return {
        "item_id": item_id,
        "dataset": dataset,
        "question_type": "short_answer",
        "subject": "fixture",
        "prompt": "prompt",
        "student_answer": "answer",
        "reference_answer": "reference",
        "rubric": "rubric",
        "gold_score": 1.0,
        "score_min": 0.0,
        "score_max": 3.0 if dataset != "dress" else 15.0,
        "schema_version": "item_semantic_v2",
        "scoring_unit": "whole_response",
        "scoring_mode": "analytic_three_dimension" if dataset == "dress" else "holistic",
        "source_assets": [{"asset_id": "image"}] if image else [],
        "metadata": {"split": "train", "prompt_group": f"{dataset}-p", "formal_eligible": True},
    }


def _write_fixture(tmp_path: Path):
    items = [
        _item("a1", "asap_sas", image=True),
        _item("a2", "asap_sas"),
        _item("a3", "asap_sas"),
        _item("d1", "dress"),
        _item("s1", "sas_bench"),
        _item("a4", "asap_sas"),
        _item("a5", "asap_sas"),
        _item("a6", "asap_sas"),
        _item("d2", "dress"),
        _item("s2", "sas_bench"),
    ]
    papers = [
        {"paper_id": "paper_z", "items": ["a1", "d1", "a2", "s1", "a3"], "metadata": {"internal_split": "train_fit", "mix_status": "strict"}},
        {"paper_id": "paper_a", "items": ["a4", "d2", "a5", "s2", "a6"], "metadata": {"internal_split": "train_fit", "mix_status": "strict"}},
    ]
    items_path = tmp_path / "items.jsonl"
    papers_path = tmp_path / "papers.jsonl"
    internal_path = tmp_path / "internal.csv"
    readiness_path = tmp_path / "readiness.json"
    write_jsonl(items_path, items)
    write_jsonl(papers_path, papers)
    rows = [
        {"item_id": row["item_id"], "source_split": "train", "internal_split": "train_fit"}
        for row in items
    ]
    with internal_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(readiness_path, {"status": "PASS", "errors": [], "run_id": "semantic"})
    return items_path, papers_path, internal_path, readiness_path


def test_checkpoint_selection_is_deterministic_and_gold_independent(tmp_path: Path):
    items_path, papers_path, internal_path, readiness_path = _write_fixture(tmp_path)
    kwargs = {
        "papers_path": papers_path,
        "items_path": items_path,
        "internal_manifest_path": internal_path,
        "semantic_readiness_manifest_path": readiness_path,
        "seed": 7,
        "output_root": tmp_path / "outputs" / "runs",
    }
    first = build_selfhosted_checkpoint_sample(run_id="real_pilot_selfhosted_checkpoint_prepare_a", **kwargs)
    rows = read_jsonl(items_path)
    for index, row in enumerate(rows):
        row["gold_score"] = float(index % 3)
    write_jsonl(items_path, rows, overwrite=True)
    second = build_selfhosted_checkpoint_sample(run_id="real_pilot_selfhosted_checkpoint_prepare_b", **kwargs)
    assert first["selected_paper_ids"] == second["selected_paper_ids"]
    assert first["selected_item_ids"] == second["selected_item_ids"]
    assert first["gold_fields_read_for_selection"] == 0
    assert first["dataset_counts"].keys() == {"asap_sas", "dress", "sas_bench"}
    assert first["image_item_count"] >= 1
    assert first["expected_canonical_calls"] == 15


def test_checkpoint_requires_readiness_pass(tmp_path: Path):
    items_path, papers_path, internal_path, readiness_path = _write_fixture(tmp_path)
    write_json(readiness_path, {"status": "FAIL", "errors": ["x"]}, overwrite=True)
    with pytest.raises(ValueError, match="Readiness"):
        build_selfhosted_checkpoint_sample(
            papers_path=papers_path,
            items_path=items_path,
            internal_manifest_path=internal_path,
            semantic_readiness_manifest_path=readiness_path,
            run_id="real_pilot_selfhosted_checkpoint_prepare_fail",
            output_root=tmp_path / "outputs" / "runs",
        )


def test_checkpoint_requires_asap_sas_image_not_any_dataset_image(tmp_path: Path):
    items_path, papers_path, internal_path, readiness_path = _write_fixture(tmp_path)
    rows = read_jsonl(items_path)
    for row in rows:
        row["source_assets"] = [{"asset_id": "wrong-dataset-image"}] if row["dataset"] == "dress" else []
    write_jsonl(items_path, rows, overwrite=True)
    with pytest.raises(ValueError, match="ASAP-SAS图片"):
        build_selfhosted_checkpoint_sample(
            papers_path=papers_path,
            items_path=items_path,
            internal_manifest_path=internal_path,
            semantic_readiness_manifest_path=readiness_path,
            run_id="real_pilot_selfhosted_checkpoint_prepare_wrong_image",
            output_root=tmp_path / "outputs" / "runs",
        )


def test_checkpoint_prepare_run_id_cannot_overwrite_existing_artifacts(tmp_path: Path):
    items_path, papers_path, internal_path, readiness_path = _write_fixture(tmp_path)
    kwargs = {
        "papers_path": papers_path,
        "items_path": items_path,
        "internal_manifest_path": internal_path,
        "semantic_readiness_manifest_path": readiness_path,
        "run_id": "real_pilot_selfhosted_checkpoint_prepare_unique",
        "output_root": tmp_path / "outputs" / "runs",
    }
    build_selfhosted_checkpoint_sample(**kwargs)
    with pytest.raises(FileExistsError, match="禁止覆盖"):
        build_selfhosted_checkpoint_sample(**kwargs)


def test_checkpoint_rejects_duplicate_internal_manifest_item_ids(tmp_path: Path):
    items_path, papers_path, internal_path, readiness_path = _write_fixture(tmp_path)
    rows = list(csv.DictReader(internal_path.open(encoding="utf-8")))
    rows.append(dict(rows[0]))
    with internal_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="重复或空item_id"):
        build_selfhosted_checkpoint_sample(
            papers_path=papers_path,
            items_path=items_path,
            internal_manifest_path=internal_path,
            semantic_readiness_manifest_path=readiness_path,
            run_id="real_pilot_selfhosted_checkpoint_prepare_duplicate_manifest",
            output_root=tmp_path / "outputs" / "runs",
        )
