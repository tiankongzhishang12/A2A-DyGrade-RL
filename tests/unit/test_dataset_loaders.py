from a2a_dygrade_rl.datasets.load_common import load_dataset
from a2a_dygrade_rl.datasets.load_dress import load_dress


def test_load_dataset_from_jsonl_fixture():
    rows = load_dataset(
        {
            "name": "smoke",
            "raw_path": "tests/fixtures/raw_smoke",
            "pattern": "*.jsonl",
            "question_type": "short_answer",
            "score_min": 0,
            "score_max": 5,
        }
    )
    assert len(rows) == 10
    assert {"item_id", "prompt", "student_answer", "gold_score"} <= set(rows[0])


def test_load_dress_filters_invalid_rows_when_raw_available():
    rows = load_dress(
        {
            "name": "dress",
            "raw_path": "data/raw/dress",
            "question_type": "essay",
            "score_min": 0,
            "score_max": 15,
        }
    )
    if not rows:
        return
    assert rows
    assert all(row["dataset"] == "dress" for row in rows)
    assert all(row["metadata"]["source_file"] in {"DREsS_Std.tsv", "DREsS_New.tsv"} for row in rows)
    assert all(0 <= row["gold_score"] <= 15 for row in rows)
