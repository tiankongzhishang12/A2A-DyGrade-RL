import json
from pathlib import Path

import pytest

from a2a_dygrade_rl.agents.base_agent import BaseAgent
from a2a_dygrade_rl.agents.cache import build_cache_key, validate_run_identity
from a2a_dygrade_rl.agents.cheap_agent import CheapAgent
from a2a_dygrade_rl.utils.llm_client import FixtureClient
from a2a_dygrade_rl.utils.validation import validate_agent_output


def sample_item() -> dict:
    return {
        "item_id": "fixture_item_1",
        "dataset": "asap_sas",
        "question_type": "short_answer",
        "subject": "science",
        "prompt": "Explain the result.",
        "student_answer": "The result follows from the evidence.",
        "reference_answer": "Use evidence to explain the result.",
        "rubric": "Award points for a supported explanation.",
        "gold_score": 2.0,
        "score_min": 0.0,
        "score_max": 3.0,
        "metadata": {"split": "train", "prompt_group": "p1"},
    }


def valid_record() -> dict:
    return {
        "item_id": "fixture_item_1",
        "agent_id": "CheapAgent",
        "run_id": "fixture_smoke_001",
        "execution_mode": "fixture_smoke",
        "is_fixture": True,
        "pred_score": 2.0,
        "confidence": 0.75,
        "justification": "The answer covers the main point.",
        "evidence": {},
        "cost": 0.001,
        "latency": 0.1,
        "token_usage": 32,
        "gold_score": 2.0,
        "split": "train",
        "model_id": "fixture-cheap-v1",
        "prompt_version": "v1",
        "prompt_hash": "a" * 64,
        "input_hash": "b" * 64,
        "context_hash": "c" * 64,
        "cache_key": "d" * 64,
        "cache_schema_version": "1.0",
        "status": "success",
        "error": None,
        "metadata": {"score_min": 0.0, "score_max": 3.0},
    }


def test_agent_cache_fixture_and_schema_are_valid():
    rows = [json.loads(line) for line in Path("tests/fixtures/agent_cache/sample_agent_cache.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows
    for row in rows:
        validate_agent_output(row, allowed_agents={"CheapAgent"})


@pytest.mark.parametrize(
    ("field", "value"),
    [("pred_score", 9.0), ("confidence", 1.1), ("cost", -1.0), ("token_usage", -2)],
)
def test_agent_output_rejects_invalid_values(field, value):
    record = valid_record()
    record[field] = value
    with pytest.raises(ValueError):
        validate_agent_output(record, item=sample_item(), allowed_agents={"CheapAgent"})


def test_cache_key_is_stable_and_sensitive_to_versions():
    parts = {
        "item_id": "i1",
        "agent_id": "CheapAgent",
        "split": "train",
        "model_id": "fixture-cheap-v1",
        "model_revision": "r1",
        "prompt_hash": "p1",
        "generation_parameters": {"temperature": 0},
        "context_hash": "c1",
        "cache_schema_version": "1.0",
    }
    first = build_cache_key(**parts)
    assert first == build_cache_key(**parts)
    assert first != build_cache_key(**{**parts, "prompt_hash": "p2"})
    assert first != build_cache_key(**{**parts, "context_hash": "c2"})


@pytest.mark.parametrize(
    ("run_id", "execution_mode", "is_fixture"),
    [
        ("fixture_smoke_001", "fixture_smoke", True),
        ("real_pilot_001", "real_pilot", False),
        ("formal_agent_cache_001", "formal_experiment", False),
    ],
)
def test_run_identity_accepts_valid_mode_combinations(run_id, execution_mode, is_fixture):
    validate_run_identity(run_id, execution_mode, is_fixture)


@pytest.mark.parametrize(
    ("run_id", "execution_mode", "is_fixture"),
    [
        ("fixture_smoke_001", "fixture_smoke", False),
        ("real_pilot_001", "real_pilot", True),
        ("formal_agent_cache_001", "formal_experiment", True),
        ("real_pilot_001", "fixture_smoke", True),
        ("fixture_smoke_001", "real_pilot", False),
        ("formal_experiment_001", "formal_experiment", False),
        ("unknown_001", "unknown_mode", False),
    ],
)
def test_run_identity_rejects_invalid_mode_combinations(run_id, execution_mode, is_fixture):
    with pytest.raises(ValueError):
        validate_run_identity(run_id, execution_mode, is_fixture)


def test_agent_request_never_contains_gold_score():
    agent = CheapAgent(
        {
            "agent_id": "CheapAgent",
            "model_id": "fixture-cheap-v1",
            "prompt_path": "prompts/cheap_scorer.txt",
            "prompt_version": "v1",
            "cost": 0.001,
            "latency": 0.1,
        },
        FixtureClient(seed=7),
    )
    request = agent.build_request(sample_item(), {"nested": {"gold_score": 99}})
    assert "gold_score" not in json.dumps(request)
    prediction = agent.predict(sample_item(), {})
    assert 0.0 <= prediction["pred_score"] <= 3.0


