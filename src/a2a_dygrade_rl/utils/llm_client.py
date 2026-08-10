"""Provider-neutral LLM client contracts, fixture client and Responses-compatible real client."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from a2a_dygrade_rl.agents.pricing import (
    BudgetGuard,
    PricingManifest,
    TokenUsage,
    compute_api_cost,
    load_pricing_manifest,
)


AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pred_score": {"type": "number"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "justification": {"type": "string"},
        "evidence": {
            "type": "object",
            "properties": {
                "matched_points": {"type": "array", "items": {"type": "string"}},
                "missing_points": {"type": "array", "items": {"type": "string"}},
                "concerns": {"type": "array", "items": {"type": "string"}},
                "participating_agents": {"type": "array", "items": {"type": "string"}},
                "recommend_escalation": {"type": "boolean"},
            },
            "required": [
                "matched_points",
                "missing_points",
                "concerns",
                "participating_agents",
                "recommend_escalation",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["pred_score", "confidence", "justification", "evidence"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ClientResponse:
    payload: dict[str, Any]
    token_usage: int
    latency: float
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: TokenUsage = field(default_factory=TokenUsage)
    cost: float | None = None


class LLMClient(ABC):
    is_fixture = False

    @abstractmethod
    def complete(self, request: dict[str, Any], agent_id: str) -> ClientResponse:
        raise NotImplementedError

    def initialize_budget(self, *, calls: int, cost_usd: float) -> None:
        del calls, cost_usd

    def budget_snapshot(self) -> dict[str, Any]:
        return {}


class OpenAIResponsesClient(LLMClient):
    """调用 CLIProxy 或官方 OpenAI-compatible Responses endpoint。"""

    is_fixture = False

    def __init__(self, *, provider: dict[str, Any], agents: dict[str, dict[str, Any]]):
        self.provider = dict(provider)
        self.agent_configs = {str(row["agent_id"]): dict(row) for row in agents.values()}
        self.base_url = str(provider["base_url"]).rstrip("/")
        self.api_key_env = str(provider.get("api_key_env", "CLIPROXY_API_KEY"))
        self.timeout_seconds = float(provider.get("timeout_seconds", 180.0))
        self.max_attempts = int(provider.get("max_attempts", 2))
        self.retry_backoff_seconds = float(provider.get("retry_backoff_seconds", 1.0))
        self.require_reported_model_match = bool(provider.get("require_reported_model_match", True))
        self.usage_source = str(provider.get("usage_source", "upstream_reported"))
        self.gateway_id = str(provider.get("gateway_id", "openai_responses"))
        self.pricing: PricingManifest = load_pricing_manifest(provider["pricing_manifest_path"])
        self.budget = BudgetGuard(
            max_cost_usd=float(provider["max_cost_usd"]),
            max_total_calls=int(provider["max_total_calls"]),
        )
        if self.max_attempts <= 0:
            raise ValueError("max_attempts 必须为正整数")

    def initialize_budget(self, *, calls: int, cost_usd: float) -> None:
        self.budget.initialize(calls=calls, cost_usd=cost_usd)

    def budget_snapshot(self) -> dict[str, Any]:
        return self.budget.snapshot()

    def complete(self, request: dict[str, Any], agent_id: str) -> ClientResponse:
        if _contains_key(request, "gold_score"):
            raise ValueError("真实 Agent 请求中禁止包含 gold_score")
        if agent_id not in self.agent_configs:
            raise ValueError(f"未知 Agent 配置: {agent_id}")
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"缺少本地代理凭据环境变量: {self.api_key_env}")
        agent_config = self.agent_configs[agent_id]
        model_id = str(agent_config["model_id"])
        generation = dict(agent_config.get("generation_parameters") or {})
        body = self._build_body(request, agent_id, model_id, generation)

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.budget.reserve_call()
            started = time.perf_counter()
            try:
                response_payload = self._post_json(body, api_key)
                latency = time.perf_counter() - started
                return self._parse_response(
                    response_payload,
                    requested_model_id=model_id,
                    latency=latency,
                    attempt_count=attempt,
                )
            except urllib.error.HTTPError as exc:
                last_error = _http_error(exc)
                retryable = exc.code in {408, 409, 429, 500, 502, 503, 504}
            except (TimeoutError, urllib.error.URLError, ConnectionError) as exc:
                last_error = exc
                retryable = True
            except Exception:
                raise
            if not retryable or attempt >= self.max_attempts:
                break
            time.sleep(self.retry_backoff_seconds * attempt)
        raise RuntimeError(f"CLIProxy Responses 调用失败: {last_error}")

    def discover_models(self) -> list[str]:
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(f"缺少本地代理凭据环境变量: {self.api_key_env}")
        request = urllib.request.Request(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return sorted(str(row["id"]) for row in payload.get("data", []))

    def _build_body(
        self,
        request: dict[str, Any],
        agent_id: str,
        model_id: str,
        generation: dict[str, Any],
    ) -> dict[str, Any]:
        visible = {key: value for key, value in request.items() if key not in {"prompt_template"}}
        instructions = (
            f"{request.get('prompt_template', '')}\n\n"
            "必须只依据提供的可见信息评分，不得推测或请求 gold_score。"
            "严格返回 JSON Schema。pred_score 必须位于 score_range；confidence 位于0到1。"
            "evidence 的五个字段必须全部存在，无内容时使用空数组或 false。"
        )
        body: dict[str, Any] = {
            "model": model_id,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {"agent_id": agent_id, "request": visible},
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "a2a_dygrade_agent_output",
                    "strict": True,
                    "schema": AGENT_RESPONSE_SCHEMA,
                }
            },
            "store": bool(generation.get("store", False)),
            "max_output_tokens": int(generation.get("max_output_tokens", generation.get("max_tokens", 512))),
        }
        reasoning_effort = generation.get("reasoning_effort")
        if reasoning_effort is not None:
            body["reasoning"] = {"effort": str(reasoning_effort)}
        return body

    def _post_json(self, body: dict[str, Any], api_key: str) -> dict[str, Any]:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=encoded,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def _parse_response(
        self,
        payload: dict[str, Any],
        *,
        requested_model_id: str,
        latency: float,
        attempt_count: int,
    ) -> ClientResponse:
        if str(payload.get("status", "")) != "completed":
            raise ValueError(f"Responses 未完成: {payload.get('status')} {payload.get('error')}")
        reported_model_id = str(payload.get("model", "")).strip()
        if not reported_model_id:
            raise ValueError("Responses 缺少实际 model ID")
        if self.require_reported_model_match and not _model_matches(requested_model_id, reported_model_id):
            raise ValueError(f"模型静默替换: requested={requested_model_id}, reported={reported_model_id}")
        usage = TokenUsage.from_api(payload.get("usage"))
        if usage.total_tokens <= 0:
            raise ValueError("真实 Responses 缺少有效 token usage")
        rule = self.pricing.rule_for(reported_model_id)
        cost = compute_api_cost(usage, rule)
        input_price_multiplier, output_price_multiplier = rule.multipliers_for(usage)
        self.budget.add_cost(cost)
        output_text = _extract_output_text(payload)
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ValueError("Structured Output 不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Structured Output 顶层必须是对象")
        metadata = {
            "client": self.__class__.__name__,
            "gateway_id": self.gateway_id,
            "request_id": str(payload.get("id", "")),
            "requested_model_id": requested_model_id,
            "reported_model_id": reported_model_id,
            "usage_source": self.usage_source,
            "attempt_count": attempt_count,
            "usage": usage.to_dict(),
            "cost_basis": "official_standard_api_list_price",
            "pricing_effective_date": self.pricing.effective_date,
            "pricing_tier": self.pricing.pricing_tier,
            "pricing_manifest_sha256": self.pricing.sha256,
            "pricing_rule": {
                "input_per_million_usd": rule.input_per_million_usd,
                "cached_input_per_million_usd": rule.cached_input_per_million_usd,
                "cache_write_per_million_usd": rule.cache_write_per_million_usd,
                "output_per_million_usd": rule.output_per_million_usd,
                "long_context_threshold_input_tokens": rule.long_context_threshold_input_tokens,
                "long_context_input_multiplier": rule.long_context_input_multiplier,
                "long_context_output_multiplier": rule.long_context_output_multiplier,
                "applied_input_multiplier": input_price_multiplier,
                "applied_output_multiplier": output_price_multiplier,
            },
        }
        return ClientResponse(
            payload=parsed,
            token_usage=usage.total_tokens,
            latency=float(latency),
            metadata=metadata,
            usage=usage,
            cost=cost,
        )


class FixtureClient(LLMClient):
    """Deterministic engineering fixture. It must never be used for paper results."""

    is_fixture = True

    def __init__(self, seed: int = 42):
        self.seed = int(seed)

    def complete(self, request: dict[str, Any], agent_id: str) -> ClientResponse:
        if _contains_key(request, "gold_score"):
            raise ValueError("Agent 请求中禁止包含 gold_score")
        score_min = float(request["score_range"]["min"])
        score_max = float(request["score_range"]["max"])
        span = score_max - score_min
        if span <= 0:
            raise ValueError("FixtureClient 收到非法分数范围")
        unit = _stable_unit(request, f"{agent_id}:{self.seed}:score")
        conf_unit = _stable_unit(request, f"{agent_id}:{self.seed}:confidence")
        answer_words = len(str(request.get("student_answer", "")).split())
        rubric_words = len(str(request.get("rubric", "")).split())
        visible_quality = answer_words / max(1.0, answer_words + 8.0 + rubric_words * 0.25)

        if agent_id == "EvidenceAgent":
            coverage = _clamp(visible_quality + (unit - 0.5) * 0.2, 0.0, 1.0)
            pred_score = score_min + span * coverage
            payload = {
                "pred_score": round(pred_score, 6),
                "confidence": round(0.55 + 0.4 * conf_unit, 6),
                "justification": "Fixture evidence coverage uses visible answer and rubric features.",
                "evidence": {
                    "coverage": round(coverage, 6),
                    "matched_points": ["fixture-visible-point"] if coverage >= 0.5 else [],
                    "missing_points": [] if coverage >= 0.5 else ["fixture-missing-point"],
                    "recommend_escalation": coverage < 0.45,
                },
            }
        elif agent_id == "ArbitratorAgent":
            opinions = request.get("context", {}).get("opinions", [])
            if not opinions:
                raise ValueError("ArbitratorAgent fixture 需要已有 Agent 意见")
            weights = [max(0.05, float(opinion.get("confidence", 0.5))) for opinion in opinions]
            pred_score = sum(float(opinion["pred_score"]) * weight for opinion, weight in zip(opinions, weights)) / sum(weights)
            payload = {
                "pred_score": round(_clamp(pred_score, score_min, score_max), 6),
                "confidence": round(_clamp(sum(weights) / len(weights), 0.0, 1.0), 6),
                "justification": "Fixture arbitration combines only opinions present in this context.",
                "evidence": {"participating_agents": [opinion["agent_id"] for opinion in opinions]},
            }
        else:
            noise_scale = {"CheapAgent": 0.55, "MidAgent": 0.32, "StrongAgent": 0.16}.get(agent_id, 0.4)
            pred_score = score_min + span * _clamp(visible_quality + (unit - 0.5) * noise_scale, 0.0, 1.0)
            confidence_base = {"CheapAgent": 0.48, "MidAgent": 0.62, "StrongAgent": 0.76}.get(agent_id, 0.5)
            payload = {
                "pred_score": round(pred_score, 6),
                "confidence": round(_clamp(confidence_base + (conf_unit - 0.5) * 0.25, 0.05, 0.99), 6),
                "justification": f"Deterministic {agent_id} fixture score uses visible input features.",
                "evidence": {},
            }

        serialized_length = len(json.dumps(request, ensure_ascii=False, sort_keys=True))
        token_usage = max(1, math.ceil(serialized_length / 4))
        usage = TokenUsage(input_tokens=token_usage, total_tokens=token_usage)
        return ClientResponse(
            payload=payload,
            token_usage=token_usage,
            latency=round(0.01 + 0.02 * conf_unit, 6),
            metadata={"client": "FixtureClient", "seed": self.seed, "usage": usage.to_dict()},
            usage=usage,
        )


def build_llm_client(config: dict[str, Any], execution_mode: str, seed: int) -> LLMClient:
    if execution_mode == "fixture_smoke":
        return FixtureClient(seed=seed)
    provider = config.get("provider")
    if not isinstance(provider, dict):
        raise ValueError("真实运行配置缺少 provider")
    provider_type = str(provider.get("type", ""))
    if provider_type != "openai_responses_compatible":
        raise ValueError(f"不支持的真实 provider type: {provider_type}")
    return OpenAIResponsesClient(provider=provider, agents=dict(config.get("agents") or {}))


def _extract_output_text(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for output in payload.get("output") or []:
        if output.get("type") != "message":
            continue
        for content in output.get("content") or []:
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                pieces.append(content["text"])
    text = "".join(pieces).strip()
    if not text:
        raise ValueError("Responses 缺少 output_text")
    return text


def _model_matches(requested: str, reported: str) -> bool:
    if requested == reported:
        return True
    return reported.startswith(requested + "-")


def _http_error(exc: urllib.error.HTTPError) -> RuntimeError:
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
    except Exception:
        detail = ""
    return RuntimeError(f"HTTP {exc.code}: {detail}")


def _contains_key(value: Any, forbidden_key: str) -> bool:
    if isinstance(value, dict):
        return forbidden_key in value or any(_contains_key(child, forbidden_key) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, forbidden_key) for child in value)
    return False


def _stable_unit(value: Any, salt: str) -> float:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + salt
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
