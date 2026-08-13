from __future__ import annotations

import pytest

from a2a_dygrade_rl.agents.pricing import PricingRule, TokenUsage, compute_api_cost, compute_server_allocated_cost


def test_chat_usage_aliases_and_visual_breakdown():
    usage = TokenUsage.from_api(
        {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "prompt_tokens_details": {"text_tokens": 80, "image_tokens": 40, "cached_tokens": 10},
        }
    )
    assert usage.input_tokens == 120
    assert usage.input_text_tokens == 80
    assert usage.input_vision_tokens == 40
    assert usage.output_tokens == 30
    assert usage.total_tokens == 150


def test_token_breakdown_cannot_exceed_input():
    with pytest.raises(ValueError, match="不得大于"):
        TokenUsage.from_api(
            {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "total_tokens": 11,
                "prompt_tokens_details": {"text_tokens": 8, "image_tokens": 5},
            }
        )


def test_cached_and_cache_write_tokens_share_input_partition():
    with pytest.raises(ValueError, match=r"cached_input_tokens \+ cache_write_tokens"):
        TokenUsage.from_api(
            {
                "prompt_tokens": 10,
                "completion_tokens": 1,
                "total_tokens": 11,
                "prompt_tokens_details": {"cached_tokens": 7, "cache_write_tokens": 4},
            }
        )

def test_official_api_equivalent_cost_is_recomputable():
    usage = TokenUsage(input_tokens=1_000, input_text_tokens=800, input_vision_tokens=200, output_tokens=100, total_tokens=1_100)
    rule = PricingRule(
        model_id="m",
        input_per_million_usd=0.10,
        cached_input_per_million_usd=0.10,
        cache_write_per_million_usd=0.10,
        output_per_million_usd=0.20,
    )
    assert compute_api_cost(usage, rule) == pytest.approx(0.00012)


def test_server_allocated_cost_is_separate_and_optional():
    assert compute_server_allocated_cost(latency_seconds=1800, server_hourly_price_usd=2.0) == pytest.approx(1.0)
    assert compute_server_allocated_cost(latency_seconds=10, server_hourly_price_usd=None) is None
    with pytest.raises(ValueError):
        compute_server_allocated_cost(latency_seconds=-1, server_hourly_price_usd=1.0)
