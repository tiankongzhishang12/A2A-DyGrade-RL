from __future__ import annotations

from copy import deepcopy
import hashlib

import pytest

from a2a_dygrade_rl.agents.capability import (
    build_formal_capability_profiles,
    calibrate_capability_support,
)


def _item(item_id: str, split: str, gold: float) -> dict:
    return {
        "item_id": item_id,
        "dataset": "asap_sas",
        "question_type": "short_answer",
        "subject": "english",
        "prompt": "p",
        "student_answer": "a",
        "reference_answer": "r",
        "rubric": "rubric",
        "gold_score": gold,
        "score_min": 0.0,
        "score_max": 1.0,
        "metadata": {"split": split, "prompt_group": item_id},
    }


def _record(item_id: str, split: str, score: float) -> dict:
    return {
        "item_id": item_id,
        "agent_id": "CheapAgent",
        "run_id": "fixture_smoke_capability",
        "execution_mode": "fixture_smoke",
        "is_fixture": True,
        "pred_score": score,
        "confidence": 0.8,
        "justification": "fixture",
        "evidence": {},
        "cost": 0.001,
        "latency": 0.5,
        "token_usage": 10,
        "gold_score": score,
        "split": split,
        "model_id": "fixture",
        "prompt_version": "v1",
        "prompt_hash": "a" * 64,
        "input_hash": "b" * 64,
        "context_hash": "c" * 64,
        "cache_key": hashlib.sha256(item_id.encode("utf-8")).hexdigest(),
        "cache_schema_version": "1.1",
        "status": "success",
        "error": None,
        "metadata": {"score_min": 0.0, "score_max": 1.0},
    }


def test_formal_capability_fit_and_calibration_have_disjoint_roles():
    fit_items = [_item("fit_a", "train_fit", 0.0), _item("fit_b", "train_fit", 1.0)]
    fit_records = [_record("fit_a", "train_fit", 0.0), _record("fit_b", "train_fit", 1.0)]
    fit_difficulty = [
        {"item_id": "fit_a", "difficulty_label": "Easy", "source_split": "train_fit"},
        {"item_id": "fit_b", "difficulty_label": "Easy", "source_split": "train_fit"},
    ]
    profiles = build_formal_capability_profiles(fit_items, fit_records, fit_difficulty, allow_fixture=True)
    assert profiles
    assert {row["source_split"] for row in profiles} == {"train_fit"}
    assert all("best_agent" not in row and "oracle_agent" not in row for row in profiles)

    cal_items = [_item("cal_a", "train_calibration", 0.0), _item("cal_b", "train_calibration", 1.0)]
    cal_records = [_record("cal_a", "train_calibration", 0.0), _record("cal_b", "train_calibration", 1.0)]
    cal_difficulty = [
        {"item_id": "cal_a", "difficulty_label": "Easy", "source_split": "train_calibration"},
        {"item_id": "cal_b", "difficulty_label": "Easy", "source_split": "train_calibration"},
    ]
    before = deepcopy(profiles)
    first = calibrate_capability_support(
        profiles,
        cal_items,
        cal_records,
        cal_difficulty,
        support_quantile=0.25,
        internal_manifest_hash="a" * 64,
        cache_hash="b" * 64,
        seed=20260729,
        allow_fixture=True,
    )
    second = calibrate_capability_support(
        profiles,
        cal_items,
        cal_records,
        cal_difficulty,
        support_quantile=0.25,
        internal_manifest_hash="a" * 64,
        cache_hash="b" * 64,
        seed=20260729,
        allow_fixture=True,
    )
    assert profiles == before
    assert first == second
    assert first["fit_split"] == "train_fit"
    assert first["calibration_split"] == "train_calibration"
    assert first["calibration_no_gradient"] is True
    assert first["no_item_oracle_labels"] is True


def test_formal_capability_rejects_dev_or_test_inputs():
    items = [_item("dev_a", "dev", 0.0)]
    records = [_record("dev_a", "dev", 0.0)]
    difficulty = [{"item_id": "dev_a", "difficulty_label": "Easy", "source_split": "dev"}]
    with pytest.raises(ValueError, match="train_fit"):
        build_formal_capability_profiles(items, records, difficulty)


def test_formal_capability_defaults_to_fail_closed_for_fixture_cache():
    items = [_item("fit_fixture", "train_fit", 0.0)]
    records = [_record("fit_fixture", "train_fit", 0.0)]
    difficulty = [{"item_id": "fit_fixture", "difficulty_label": "Easy", "source_split": "train_fit"}]
    with pytest.raises(ValueError, match="Fixture"):
        build_formal_capability_profiles(items, records, difficulty)


def test_formal_capability_rejects_fixture_items_even_if_cache_flags_are_forged():
    items = [_item("fit_fixture_item", "train_fit", 0.0)]
    items[0]["metadata"].update({"fixture": True, "formal_eligible": False})
    records = [_record("fit_fixture_item", "train_fit", 0.0)]
    records[0].update({"run_id": "formal_agent_cache_forged", "execution_mode": "formal_experiment", "is_fixture": False})
    difficulty = [{"item_id": "fit_fixture_item", "difficulty_label": "Easy", "source_split": "train_fit"}]
    with pytest.raises(ValueError, match="Fixture"):
        build_formal_capability_profiles(items, records, difficulty)



def test_formal_capability_rejects_nonboolean_fixture_identity():
    items = [_item("fit_formal", "train_fit", 0.0)]
    records = [_record("fit_formal", "train_fit", 0.0)]
    records[0].update({
        "run_id": "formal_agent_cache_capability",
        "execution_mode": "formal_experiment",
        "is_fixture": "false",
    })
    difficulty = [{"item_id": "fit_formal", "difficulty_label": "Easy", "source_split": "train_fit"}]
    with pytest.raises(ValueError):
        build_formal_capability_profiles(items, records, difficulty)


def test_capability_support_rejects_invalid_manifest_hashes():
    fit_items = [_item("fit_a", "train_fit", 0.0)]
    fit_records = [_record("fit_a", "train_fit", 0.0)]
    fit_difficulty = [{"item_id": "fit_a", "difficulty_label": "Easy", "source_split": "train_fit"}]
    profiles = build_formal_capability_profiles(fit_items, fit_records, fit_difficulty, allow_fixture=True)
    cal_items = [_item("cal_a", "train_calibration", 0.0)]
    cal_records = [_record("cal_a", "train_calibration", 0.0)]
    cal_difficulty = [{"item_id": "cal_a", "difficulty_label": "Easy", "source_split": "train_calibration"}]

    with pytest.raises(ValueError):
        calibrate_capability_support(
            profiles,
            cal_items,
            cal_records,
            cal_difficulty,
            support_quantile=0.25,
            internal_manifest_hash="not-a-hash",
            cache_hash="b" * 64,
            seed=20260729,
            allow_fixture=True,
        )
