from __future__ import annotations

import json
from pathlib import Path

import pytest

from a2a_dygrade_rl.agents.pricing import BudgetExceededError
from a2a_dygrade_rl.utils.selfhosted_client import (
    ChatHTTPError,
    FakeChatTransport,
    SelfHostedChatCompletionsClient,
)


def _provider(tmp_path: Path) -> dict:
    pricing = tmp_path / "pricing.yaml"
    pricing.write_text(
        """effective_date: '2026-08-12'\ncurrency: USD\npricing_tier: test\nsource: fixture\nmodels:\n  test-model:\n    input_per_million_usd: 1.0\n    output_per_million_usd: 2.0\n""",
        encoding="utf-8",
    )
    prepared = tmp_path / "prepared"
    prepared.mkdir(exist_ok=True)
    return {
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key_env": "UNUSED_SELFHOSTED_KEY",
        "require_api_key": False,
        "timeout_seconds": 1,
        "max_attempts": 2,
        "retry_backoff_seconds": 0,
        "require_reported_model_match": True,
        "require_usage": True,
        "require_multimodal_token_breakdown": True,
        "prepared_root": str(prepared),
        "pricing_manifest_path": str(pricing),
        "max_cost_usd": 1.0,
        "max_total_calls": 5,
        "provider_id": "fixture",
        "gateway_id": "fake",
        "attempt_log_path": str(tmp_path / "attempts.jsonl"),
    }


def _agents() -> dict:
    return {
        "cheap": {
            "agent_id": "CheapAgent",
            "model_id": "test-model",
            "generation_parameters": {"temperature": 0.0, "max_tokens": 128, "enable_thinking": False},
        }
    }


def _request() -> dict:
    return {
        "item_id": "item-1",
        "dataset": "asap_sas",
        "prompt": "Question",
        "student_answer": "Answer",
        "rubric": "Rubric",
        "reference_answer": "",
        "scoring_mode": "holistic",
        "source_assets": [],
        "score_range": {"min": 0.0, "max": 3.0},
        "prompt_template": "Return JSON.",
    }


def test_fake_chat_client_builds_schema_body_and_cost(tmp_path: Path):
    transport = FakeChatTransport(capture_path=tmp_path / "captured.jsonl")
    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=transport)
    response = client.complete(_request(), "CheapAgent", logical_call_id="a" * 64)
    assert response.token_usage == response.usage.input_tokens + response.usage.output_tokens
    assert response.cost is not None and response.cost > 0
    assert response.metadata["logical_call_id"] == "a" * 64
    assert response.metadata["canonical_attempt_id"]
    body = transport.calls[0]
    assert body["temperature"] == 0.0
    assert body["response_format"]["type"] == "json_schema"
    assert body["messages"][1]["content"][0]["type"] == "text"
    serialized = json.dumps(body, ensure_ascii=False).lower()
    assert "gold_score" not in serialized
    assert "manual_label" not in serialized


def test_chat_client_retries_retryable_http_and_audits_attempts(tmp_path: Path):
    transport = FakeChatTransport(scripted_failures=[503])
    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=transport)
    response = client.complete(_request(), "CheapAgent", logical_call_id="b" * 64)
    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(transport.calls) == 2
    assert [row["status"] for row in attempts] == ["retryable_failure", "success"]
    assert response.metadata["attempt_count"] == 2


def test_chat_client_does_not_retry_terminal_http(tmp_path: Path):
    transport = FakeChatTransport(scripted_failures=[400])
    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=transport)
    with pytest.raises(RuntimeError, match="HTTP 400"):
        client.complete(_request(), "CheapAgent", logical_call_id="c" * 64)
    assert len(transport.calls) == 1


def test_chat_client_rejects_reported_model_replacement(tmp_path: Path):
    class ReplacingTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            payload["model"] = "other-model"
            return payload

    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=ReplacingTransport())
    with pytest.raises(RuntimeError, match="模型静默替换"):
        client.complete(_request(), "CheapAgent", logical_call_id="d" * 64)


def test_chat_client_rejects_missing_or_inconsistent_usage(tmp_path: Path):
    class BadUsageTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            payload["usage"]["total_tokens"] += 1
            return payload

    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=BadUsageTransport())
    with pytest.raises(RuntimeError, match="total_tokens"):
        client.complete(_request(), "CheapAgent", logical_call_id="e" * 64)


def test_chat_client_rejects_gold_before_transport(tmp_path: Path):
    transport = FakeChatTransport()
    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=transport)
    request = _request()
    request["nested"] = {"gold_score": 2}
    with pytest.raises(ValueError, match="禁用Gold"):
        client.complete(request, "CheapAgent", logical_call_id="f" * 64)
    assert transport.calls == []


def test_budget_guard_is_hard_for_selfhosted_client(tmp_path: Path):
    provider = _provider(tmp_path)
    provider["max_total_calls"] = 1
    client = SelfHostedChatCompletionsClient(provider=provider, agents=_agents(), transport=FakeChatTransport())
    client.complete(_request(), "CheapAgent", logical_call_id="1" * 64)
    with pytest.raises(BudgetExceededError):
        client.complete(_request(), "CheapAgent", logical_call_id="2" * 64)


def test_chat_client_rejects_non_json_and_incomplete_schema(tmp_path: Path):
    class NonJsonTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            payload["choices"][0]["message"]["content"] = "not-json"
            return payload

    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=NonJsonTransport())
    with pytest.raises(RuntimeError, match="Expecting value"):
        client.complete(_request(), "CheapAgent", logical_call_id="3" * 64)

    class MissingEvidenceTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            parsed = json.loads(payload["choices"][0]["message"]["content"])
            parsed["evidence"].pop("concerns")
            payload["choices"][0]["message"]["content"] = json.dumps(parsed)
            return payload

    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=MissingEvidenceTransport())
    with pytest.raises(RuntimeError, match="evidence 字段不完整"):
        client.complete(_request(), "CheapAgent", logical_call_id="4" * 64)



def test_chat_body_handles_official_jpeg_and_tiff_assets(tmp_path: Path):
    provider = _provider(tmp_path)
    provider["prepared_root"] = "data/processed/semantic_v2"
    resources = json.loads(Path("data/processed/semantic_v2/resource_manifest.json").read_text(encoding="utf-8"))["resources"]
    jpeg = next(row for row in resources if row["mime_type"] == "image/jpeg")
    tiff = next(row for row in resources if row["mime_type"] == "image/tiff")
    for asset, expected_prefix in ((jpeg, "data:image/jpeg;base64,"), (tiff, "data:image/png;base64,")):
        transport = FakeChatTransport()
        client = SelfHostedChatCompletionsClient(provider=provider, agents=_agents(), transport=transport)
        request = _request()
        request["source_assets"] = [asset]
        response = client.complete(request, "CheapAgent", logical_call_id=("5" if asset is jpeg else "6") * 64)
        image_block = transport.calls[0]["messages"][1]["content"][1]
        assert image_block["type"] == "image_url"
        assert image_block["image_url"]["url"].startswith(expected_prefix)
        assert response.usage.input_vision_tokens > 0
        assert response.metadata["asset_audit"][0]["source_sha256"] == asset["sha256"]


def test_attempt_numbers_continue_across_client_restart(tmp_path: Path):
    provider = _provider(tmp_path)
    first = SelfHostedChatCompletionsClient(provider=provider, agents=_agents(), transport=FakeChatTransport(scripted_failures=[400]))
    with pytest.raises(RuntimeError):
        first.complete(_request(), "CheapAgent", logical_call_id="7" * 64)
    second = SelfHostedChatCompletionsClient(provider=provider, agents=_agents(), transport=FakeChatTransport())
    response = second.complete(_request(), "CheapAgent", logical_call_id="7" * 64)
    assert response.metadata["attempt_count"] == 2
    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["attempt_number"] for row in attempts] == [1, 2]
    assert len({row["attempt_id"] for row in attempts}) == 2


def test_failed_structured_response_records_operational_token_cost(tmp_path: Path):
    class InvalidSchemaTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            parsed = json.loads(payload["choices"][0]["message"]["content"])
            parsed.pop("evidence")
            payload["choices"][0]["message"]["content"] = json.dumps(parsed)
            return payload

    client = SelfHostedChatCompletionsClient(provider=_provider(tmp_path), agents=_agents(), transport=InvalidSchemaTransport())
    with pytest.raises(RuntimeError, match="字段不匹配"):
        client.complete(_request(), "CheapAgent", logical_call_id="8" * 64)
    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert attempts[0]["status"] == "terminal_failure"
    assert attempts[0]["official_api_equivalent_cost_usd"] > 0
    assert attempts[0]["usage"]["total_tokens"] > 0


def test_retry_budget_is_per_invocation_after_prior_attempt_history(tmp_path: Path):
    provider = _provider(tmp_path)
    first = SelfHostedChatCompletionsClient(provider=provider, agents=_agents(), transport=FakeChatTransport(scripted_failures=[400]))
    with pytest.raises(RuntimeError):
        first.complete(_request(), "CheapAgent", logical_call_id="9" * 64)
    second_transport = FakeChatTransport(scripted_failures=[503])
    second = SelfHostedChatCompletionsClient(provider=provider, agents=_agents(), transport=second_transport)
    response = second.complete(_request(), "CheapAgent", logical_call_id="9" * 64)
    assert len(second_transport.calls) == 2
    assert response.metadata["attempt_count"] == 3

def test_budget_overrun_books_attempt_cost_exactly_once(tmp_path: Path):
    provider = _provider(tmp_path)
    provider["max_cost_usd"] = 0.000001
    client = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=FakeChatTransport(),
    )

    with pytest.raises(RuntimeError, match="超过硬门"):
        client.complete(_request(), "CheapAgent", logical_call_id="a1" * 32)

    attempts = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(attempts) == 1
    assert attempts[0]["status"] == "terminal_failure"
    incurred_cost = attempts[0]["official_api_equivalent_cost_usd"]
    assert incurred_cost > provider["max_cost_usd"]
    assert client.budget_snapshot()["cost_usd"] == pytest.approx(incurred_cost)

def test_reported_model_suffix_is_rejected_for_exact_identity(tmp_path: Path):
    class SuffixedModelTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            payload["model"] = "test-model-revision"
            return payload

    client = SelfHostedChatCompletionsClient(
        provider=_provider(tmp_path),
        agents=_agents(),
        transport=SuffixedModelTransport(),
    )
    with pytest.raises(RuntimeError, match="模型静默替换"):
        client.complete(_request(), "CheapAgent", logical_call_id="b1" * 32)


def test_model_replacement_attempt_keeps_usage_and_cost_audit(tmp_path: Path):
    class ReplacingTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            payload["model"] = "unpriced-replacement-model"
            return payload

    client = SelfHostedChatCompletionsClient(
        provider=_provider(tmp_path),
        agents=_agents(),
        transport=ReplacingTransport(),
    )
    with pytest.raises(RuntimeError, match="模型静默替换"):
        client.complete(_request(), "CheapAgent", logical_call_id="b2" * 32)

    attempt = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8").strip())
    assert attempt["reported_model_id"] == "unpriced-replacement-model"
    assert attempt["pricing_model_id"] == "test-model"
    assert attempt["usage"]["total_tokens"] > 0
    assert attempt["official_api_equivalent_cost_usd"] > 0


def test_attempt_budget_is_restored_after_process_restart(tmp_path: Path):
    provider = _provider(tmp_path)
    first = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=FakeChatTransport(scripted_failures=[503]),
    )
    response = first.complete(_request(), "CheapAgent", logical_call_id="b3" * 32)
    before = first.budget_snapshot()
    attempts_before = [json.loads(line) for line in (tmp_path / "attempts.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(attempts_before) == 2
    assert before["cost_usd"] == pytest.approx(sum(row["official_api_equivalent_cost_usd"] for row in attempts_before))

    restarted = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=FakeChatTransport(),
    )
    restored = restarted.budget_snapshot()
    assert restored["calls"] == 2
    assert restored["cost_usd"] == pytest.approx(before["cost_usd"])
    assert response.metadata["schema_sha256"]


def test_budget_overrun_on_failed_response_is_audited_before_stopping(tmp_path: Path):
    class InvalidSchemaTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            parsed = json.loads(payload["choices"][0]["message"]["content"])
            parsed.pop("evidence")
            payload["choices"][0]["message"]["content"] = json.dumps(parsed)
            return payload

    provider = _provider(tmp_path)
    provider["max_cost_usd"] = 0.000001
    client = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=InvalidSchemaTransport(),
    )
    with pytest.raises(RuntimeError, match="超过硬门"):
        client.complete(_request(), "CheapAgent", logical_call_id="b4" * 32)

    attempt = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8").strip())
    assert attempt["status"] == "terminal_failure"
    assert attempt["official_api_equivalent_cost_usd"] > 0
    assert client.budget_snapshot()["cost_usd"] == pytest.approx(attempt["official_api_equivalent_cost_usd"])

def test_client_rejects_out_of_range_score_before_success_audit(tmp_path: Path):
    class OutOfRangeTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            parsed = json.loads(payload["choices"][0]["message"]["content"])
            parsed["pred_score"] = 999
            payload["choices"][0]["message"]["content"] = json.dumps(parsed)
            return payload

    client = SelfHostedChatCompletionsClient(
        provider=_provider(tmp_path),
        agents=_agents(),
        transport=OutOfRangeTransport(),
    )
    with pytest.raises(RuntimeError, match="pred_score 越界"):
        client.complete(_request(), "CheapAgent", logical_call_id="b5" * 32)
    attempt = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8").strip())
    assert attempt["status"] == "terminal_failure"


def test_client_rejects_dress_trait_sum_and_non_dress_traits(tmp_path: Path):
    class BadDressTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            parsed = json.loads(payload["choices"][0]["message"]["content"])
            parsed["pred_score"] += 1
            payload["choices"][0]["message"]["content"] = json.dumps(parsed)
            return payload

    dress = _request()
    dress["scoring_mode"] = "analytic_three_dimension"
    dress["score_range"] = {"min": 0.0, "max": 15.0}
    client = SelfHostedChatCompletionsClient(
        provider=_provider(tmp_path),
        agents=_agents(),
        transport=BadDressTransport(),
    )
    with pytest.raises(RuntimeError, match="三个trait_scores之和"):
        client.complete(dress, "CheapAgent", logical_call_id="b6" * 32)

    class NonDressTraitsTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            parsed = json.loads(payload["choices"][0]["message"]["content"])
            parsed["trait_scores"] = {"content": 1, "organization": 1, "language": 1}
            payload["choices"][0]["message"]["content"] = json.dumps(parsed)
            return payload

    non_dress_path = tmp_path / "non_dress"
    non_dress_path.mkdir()
    provider = _provider(non_dress_path)
    client = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=NonDressTraitsTransport(),
    )
    with pytest.raises(RuntimeError, match="trait_scores必须为空"):
        client.complete(_request(), "CheapAgent", logical_call_id="b7" * 32)


def test_attempt_records_optional_allocated_server_cost(tmp_path: Path):
    provider = _provider(tmp_path)
    provider["server_hourly_price_usd"] = 3.6
    client = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=FakeChatTransport(),
    )
    response = client.complete(_request(), "CheapAgent", logical_call_id="b8" * 32)
    attempt = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8").strip())
    assert attempt["actual_server_allocated_cost_usd"] is not None
    assert attempt["actual_server_allocated_cost_usd"] >= 0
    assert response.metadata["pricing"]["actual_server_allocated_cost_usd"] >= 0

def test_transport_failure_records_allocated_server_overhead(tmp_path: Path):
    provider = _provider(tmp_path)
    provider["server_hourly_price_usd"] = 3.6
    client = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=FakeChatTransport(scripted_failures=[400]),
    )
    with pytest.raises(RuntimeError, match="HTTP 400"):
        client.complete(_request(), "CheapAgent", logical_call_id="b9" * 32)
    attempt = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8").strip())
    assert attempt["status"] == "terminal_failure"
    assert attempt["actual_server_allocated_cost_usd"] is not None
    assert attempt["actual_server_allocated_cost_usd"] >= 0


def test_model_visible_request_semantics_are_identical_except_model(tmp_path: Path):
    agents = {
        "cheap": {"agent_id": "CheapAgent", "model_id": "test-model", "generation_parameters": {"temperature": 0.0, "max_tokens": 128, "enable_thinking": False}},
        "mid": {"agent_id": "MidAgent", "model_id": "test-model-mid", "generation_parameters": {"temperature": 0.0, "max_tokens": 128, "enable_thinking": False}},
    }
    provider = _provider(tmp_path)
    pricing_path = Path(provider["pricing_manifest_path"])
    pricing_path.write_text(
        pricing_path.read_text(encoding="utf-8")
        + "  test-model-mid:\n    input_per_million_usd: 1.0\n    output_per_million_usd: 2.0\n",
        encoding="utf-8",
    )
    transport = FakeChatTransport()
    client = SelfHostedChatCompletionsClient(provider=provider, agents=agents, transport=transport)
    request = _request()
    request["role"] = "cheap_scorer"
    cheap = client.complete(request, "CheapAgent", logical_call_id="c1" * 32)
    request["role"] = "mid_scorer"
    mid = client.complete(request, "MidAgent", logical_call_id="c2" * 32)

    cheap_body, mid_body = transport.calls
    assert cheap_body["model"] != mid_body["model"]
    assert {key: value for key, value in cheap_body.items() if key != "model"} == {
        key: value for key, value in mid_body.items() if key != "model"
    }
    serialized_user = json.loads(cheap_body["messages"][1]["content"][0]["text"])
    assert "agent_id" not in serialized_user
    assert "role" not in serialized_user["request"]
    assert cheap.metadata["request_semantics_sha256"] == mid.metadata["request_semantics_sha256"]



def test_failed_response_server_cost_matches_recorded_latency(tmp_path: Path):
    class InvalidJsonTransport(FakeChatTransport):
        def post_json(self, **kwargs):
            payload = super().post_json(**kwargs)
            payload["choices"][0]["message"]["content"] = "not-json"
            return payload

    provider = _provider(tmp_path)
    provider["server_hourly_price_usd"] = 3.6
    provider["max_attempts"] = 1
    client = SelfHostedChatCompletionsClient(
        provider=provider,
        agents=_agents(),
        transport=InvalidJsonTransport(),
    )
    with pytest.raises(RuntimeError, match="调用失败"):
        client.complete(_request(), "CheapAgent", logical_call_id="ca" * 32)
    attempt = json.loads((tmp_path / "attempts.jsonl").read_text(encoding="utf-8").strip())
    assert attempt["status"] == "terminal_failure"
    expected = 3.6 * float(attempt["latency_seconds"]) / 3600.0
    assert attempt["actual_server_allocated_cost_usd"] == pytest.approx(expected)
