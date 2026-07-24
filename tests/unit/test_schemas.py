from a2a_dygrade_rl.datasets.normalize import normalize_record
from a2a_dygrade_rl.utils.validation import validate_item


def test_normalize_record_accepts_alias_fields():
    item = normalize_record(
        {
            "id": "1",
            "question": "解释水循环。",
            "answer": "水蒸发后形成云。",
            "reference": "水通过蒸发、凝结、降水和径流循环。",
            "score": 4,
            "prompt_id": "p1",
        },
        {"name": "smoke", "question_type": "short_answer", "score_min": 0, "score_max": 5},
    )
    validate_item(item)
    assert item["item_id"] == "smoke_1"
    assert item["metadata"]["prompt_group"] == "p1"
