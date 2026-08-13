from __future__ import annotations

import json

import pytest

from a2a_dygrade_rl.agents.pricing import (
    BudgetExceededError,
    BudgetGuard,
    PricingRule,
    TokenUsage,
    compute_api_cost,
    load_pricing_manifest,
)
from a2a_dygrade_rl.utils.llm_client import OpenAIResponsesClient


def test_token_usage_and_official_cost_do_not_double_count_reasoning():
    usage = TokenUsage.from_api(
        {
            "input_tokens": 3200,
            "input_tokens_details": {"cached_tokens": 1000, "cache_write_tokens": 200},
            "output_tokens": 700,
            "output_tokens_details": {"reasoning_tokens": 450},
            "total_tokens": 3900,
        }
    )
    rule = PricingRule(
        model_id="gpt-test",
        input_per_million_usd=2.5,
        cached_input_per_million_usd=0.25,
        cache_write_per_million_usd=3.125,
        output_per_million_usd=15.0,
    )
    expected = (2000 * 2.5 + 1000 * 0.25 + 200 * 3.125 + 700 * 15.0) / 1_000_000
    assert compute_api_cost(usage, rule) == pytest.approx(expected)
    assert usage.reasoning_tokens == 450
    assert usage.output_tokens == 700


def test_token_usage_rejects_inconsistent_details():
    with pytest.raises(ValueError, match="cached_input_tokens"):
        TokenUsage.from_api(
            {
                "input_tokens": 3,
                "input_tokens_details": {"cached_tokens": 4},
                "output_tokens": 1,
                "total_tokens": 4,
            }
        )
    with pytest.raises(ValueError, match="total_tokens"):
        TokenUsage.from_api({"input_tokens": 3, "output_tokens": 2, "total_tokens": 9})


def test_long_context_multiplier_applies_only_above_272k_input_tokens():
    rule = PricingRule(
        model_id="gpt-test",
        input_per_million_usd=2.0,
        cached_input_per_million_usd=0.2,
        cache_write_per_million_usd=2.5,
        output_per_million_usd=12.0,
        long_context_threshold_input_tokens=272_000,
        long_context_input_multiplier=2.0,
        long_context_output_multiplier=1.5,
    )
    boundary = TokenUsage(input_tokens=272_000, output_tokens=1000, total_tokens=273_000)
    above = TokenUsage(input_tokens=272_001, output_tokens=1000, total_tokens=273_001)
    assert compute_api_cost(boundary, rule) == pytest.approx((272_000 * 2.0 + 1000 * 12.0) / 1_000_000)
    assert compute_api_cost(above, rule) == pytest.approx(
        (272_001 * 2.0 * 2.0 + 1000 * 12.0 * 1.5) / 1_000_000
    )


def test_20260731_manifest_matches_current_gpt56_standard_rates():
    manifest = load_pricing_manifest("configs/pricing/openai_standard_20260731.yaml")
    luna = manifest.rule_for("gpt-5.6-luna")
    terra = manifest.rule_for("gpt-5.6-terra")
    sol = manifest.rule_for("gpt-5.6-sol")
    assert (luna.input_per_million_usd, luna.cached_input_per_million_usd, luna.output_per_million_usd) == (
        0.2,
        0.02,
        1.2,
    )
    assert (terra.input_per_million_usd, terra.cached_input_per_million_usd, terra.output_per_million_usd) == (
        2.0,
        0.2,
        12.0,
    )
    assert (sol.input_per_million_usd, sol.cached_input_per_million_usd, sol.output_per_million_usd) == (
        5.0,
        0.5,
        30.0,
    )
    assert sol.long_context_threshold_input_tokens == 272_000


def test_budget_guard_is_hard_and_resume_aware():
    guard = BudgetGuard(max_cost_usd=1.0, max_total_calls=2)
    guard.initialize(calls=1, cost_usd=0.25)
    guard.reserve_call()
    guard.add_cost(0.5)
    with pytest.raises(BudgetExceededError):
        guard.reserve_call()
    assert guard.snapshot()["calls"] == 2
    assert guard.snapshot()["cost_usd"] == pytest.approx(0.75)


def _provider_config() -> dict:
    return {
        "base_url": "http://127.0.0.1:8317/v1",
        "api_key_env": "TEST_CLIPROXY_KEY",
        "pricing_manifest_path": "configs/pricing/openai_standard_20260731.yaml",
        "max_cost_usd": 1.0,
        "max_total_calls": 10,
        "max_attempts": 1,
        "require_reported_model_match": True,
        "gateway_id": "test_gateway",
    }


def _agents() -> dict:
    return {
        "cheap": {
            "agent_id": "CheapAgent",
            "model_id": "gpt-5.6-luna",
            "generation_parameters": {"reasoning_effort": "none", "max_output_tokens": 128},
        }
    }


def _response(model: str = "gpt-5.6-luna") -> dict:
    output = {
        "pred_score": 1.0,
        "confidence": 0.8,
        "justification": "依据充分。",
        "evidence": {
            "matched_points": ["point"],
            "missing_points": [],
            "concerns": [],
            "participating_agents": [],
            "recommend_escalation": False,
        },
    }
    return {
        "id": "resp_test",
        "model": model,
        "status": "completed",
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {"cached_tokens": 10, "cache_write_tokens": 0},
            "output_tokens": 20,
            "output_tokens_details": {"reasoning_tokens": 5},
            "total_tokens": 120,
        },
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": json.dumps(output, ensure_ascii=False)}]}
        ],
    }


def test_responses_client_parses_model_usage_and_cost(monkeypatch):
    monkeypatch.setenv("TEST_CLIPROXY_KEY", "local-test-key")
    client = OpenAIResponsesClient(provider=_provider_config(), agents=_agents())
    monkeypatch.setattr(client, "_post_json", lambda body, key: _response())
    response = client.complete(
        {
            "prompt_template": "score",
            "score_range": {"min": 0, "max": 3},
            "student_answer": "answer",
            "context": {},
        },
        "CheapAgent",
    )
    assert response.metadata["reported_model_id"] == "gpt-5.6-luna"
    assert response.usage.cached_input_tokens == 10
    assert response.usage.reasoning_tokens == 5
    assert response.cost == pytest.approx((90 * 0.2 + 10 * 0.02 + 20 * 1.2) / 1_000_000)
    assert response.metadata["pricing_rule"]["applied_input_multiplier"] == 1.0
    assert response.metadata["pricing_rule"]["applied_output_multiplier"] == 1.0


def test_responses_client_rejects_silent_model_replacement(monkeypatch):
    monkeypatch.setenv("TEST_CLIPROXY_KEY", "local-test-key")
    client = OpenAIResponsesClient(provider=_provider_config(), agents=_agents())
    monkeypatch.setattr(client, "_post_json", lambda body, key: _response("gpt-5.6-sol"))
    with pytest.raises(ValueError, match="模型静默替换"):
        client.complete(
            {
                "prompt_template": "score",
                "score_range": {"min": 0, "max": 3},
                "student_answer": "answer",
                "context": {},
            },
            "CheapAgent",
        )
