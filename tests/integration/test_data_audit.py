from __future__ import annotations

from a2a_dygrade_rl.datasets.audit import audit_prepared_data
from a2a_dygrade_rl.datasets.normalize import normalized_score_error, score_range
from a2a_dygrade_rl.utils.io import read_jsonl, write_jsonl


def _item(item_id: str, split: str, prompt_group: str, dataset: str = "asap_sas") -> dict:
    return {
        "item_id": item_id,
        "dataset": dataset,
        "question_type": "short_answer",
        "subject": "science",
        "prompt": f"prompt {prompt_group}",
        "student_answer": f"answer {item_id}",
        "reference_answer": "",
        "rubric": "rubric",
        "gold_score": 1.0,
        "score_min": 0.0,
        "score_max": 2.0,
        "metadata": {"split": split, "prompt_group": prompt_group},
    }


def _paper(paper_id: str, split: str, item_ids: list[str]) -> dict:
    return {
        "paper_id": paper_id,
        "items": item_ids,
        "paper_budget": {"max_cost": 1.0, "max_latency": 10.0, "max_agent_calls": 4, "max_a2a_messages": 2},
        "metadata": {"split": split, "dataset_mix": ["asap_sas"], "seed": 7, "construction_rule_version": "test"},
    }


def _write_minimal_processed(processed_dir) -> None:
    train_items = [_item("train_1", "train", "p1"), _item("train_2", "train", "p2")]
    dev_items = [_item("dev_1", "dev", "p3"), _item("dev_2", "dev", "p4")]
    test_items = [_item("test_1", "test", "p5"), _item("test_2", "test", "p6")]
    for split, items in (("train", train_items), ("dev", dev_items), ("test", test_items)):
        write_jsonl(processed_dir / f"items_{split}.jsonl", items, overwrite=True)
        write_jsonl(processed_dir / f"papers_{split}.jsonl", [_paper(f"paper_{split}", split, [item["item_id"] for item in items])], overwrite=True)
    (processed_dir / "split_manifest.csv").write_text(
        "item_id,dataset,prompt_group,paper_id,split,seed,rule_version,split_scope\n"
        "train_1,asap_sas,p1,,train,7,test,dataset_aware_prompt\n",
        encoding="utf-8",
    )
    (processed_dir / "paper_manifest.csv").write_text(
        "item_id,dataset,prompt_group,paper_id,split,seed,rule_version\n"
        "train_1,asap_sas,p1,paper_train,train,7,test\n",
        encoding="utf-8",
    )


def test_normalized_score_error_formula():
    assert score_range(0, 4) == 4
    assert normalized_score_error(pred_score=3, gold_score=1, score_min=0, score_max=4) == 0.5


def test_audit_prepared_data_writes_reports(tmp_path):
    processed_dir = tmp_path / "processed"
    output_root = tmp_path / "outputs" / "runs"
    _write_minimal_processed(processed_dir)

    result = audit_prepared_data(processed_dir, "pytest_audit", output_root=output_root, min_paper_items=2, overwrite=True)

    assert result.passed
    assert result.report_path is not None and result.report_path.exists()
    assert result.distribution_path is not None and result.distribution_path.exists()
    assert "R_i = score_max_i - score_min_i" in result.report_path.read_text(encoding="utf-8")


def test_audit_detects_score_range_prompt_leak_and_bad_paper_ref(tmp_path):
    processed_dir = tmp_path / "processed"
    _write_minimal_processed(processed_dir)
    train_items = read_jsonl(processed_dir / "items_train.jsonl")
    train_items[0]["score_max"] = 0.0
    write_jsonl(processed_dir / "items_train.jsonl", train_items, overwrite=True)
    test_items = read_jsonl(processed_dir / "items_test.jsonl")
    test_items[0]["metadata"]["prompt_group"] = "p2"
    write_jsonl(processed_dir / "items_test.jsonl", test_items, overwrite=True)
    bad_test_paper = [_paper("paper_test_bad", "test", ["missing_item", "test_2"])]
    write_jsonl(processed_dir / "papers_test.jsonl", bad_test_paper, overwrite=True)

    result = audit_prepared_data(processed_dir, "pytest_bad", output_root=tmp_path / "outputs" / "runs", min_paper_items=2, overwrite=True)

    assert not result.passed
    joined_errors = "\n".join(result.errors)
    assert "score_max 必须大于 score_min" in joined_errors
    assert "test prompt group" in joined_errors
    assert "Paper 引用不存在 item" in joined_errors
