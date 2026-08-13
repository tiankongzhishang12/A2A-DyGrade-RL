"""OpenAI-compatible Chat Completions client for audited self-hosted models."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from a2a_dygrade_rl.agents.pricing import (
    BudgetExceededError,
    BudgetGuard,
    PricingManifest,
    TokenUsage,
    compute_api_cost,
    compute_server_allocated_cost,
    load_pricing_manifest,
)
from a2a_dygrade_rl.utils.io import ensure_dir
from a2a_dygrade_rl.utils.llm_client import (
    SELFHOSTED_AGENT_RESPONSE_SCHEMA,
    ClientResponse,
    LLMClient,
)
from a2a_dygrade_rl.utils.model_input import find_banned_keys, strip_banned_fields
from a2a_dygrade_rl.utils.multimodal import PreparedAsset, prepare_source_assets


class ChatTransport(Protocol):
    kind: str

    def post_json(
        self,
        *,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]: ...


@dataclass
class UrllibChatTransport:
    kind: str = "urllib"

    def post_json(
        self,
        *,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Chat Completions 响应顶层必须是对象")
        return payload


@dataclass
class FakeChatTransport:
    """Deterministic local transport. It never calls a network or a model."""

    scripted_failures: list[int | Exception] = field(default_factory=list)
    capture_path: Path | None = None
    kind: str = "fake"
    calls: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def post_json(
        self,
        *,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        del headers, timeout_seconds
        with self._lock:
            call_number = len(self.calls) + 1
            self.calls.append(json.loads(json.dumps(body, ensure_ascii=False)))
            if self.capture_path is not None:
                _append_jsonl(self.capture_path, {"call_number": call_number, "url": url, "body": body})
            if self.scripted_failures:
                failure = self.scripted_failures.pop(0)
                if isinstance(failure, Exception):
                    raise failure
                raise ChatHTTPError(int(failure), f"fake scripted HTTP {failure}")
        request_payload = _extract_fake_request(body)
        score_range = dict(request_payload["score_range"])
        lower = float(score_range["min"])
        upper = float(score_range["max"])
        digest = hashlib.sha256(
            json.dumps(
                {"model": body["model"], "request": request_payload},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        unit = int(digest[:12], 16) / float(0xFFFFFFFFFFFF)
        model = str(body["model"])
        strength = 0.25 if "3B" in model else 0.55 if "8B" in model else 0.82
        confidence = round(min(0.98, 0.45 + strength * 0.45), 6)
        scoring_mode = str(request_payload.get("scoring_mode", ""))
        if scoring_mode == "analytic_three_dimension":
            base = max(0.0, min(5.0, 1.0 + 3.2 * strength + (unit - 0.5) * 0.8))
            traits = {
                "content": round(base, 2),
                "organization": round(max(0.0, min(5.0, base - 0.25)), 2),
                "language": round(max(0.0, min(5.0, base + 0.15)), 2),
            }
            pred_score = round(sum(traits.values()), 2)
        else:
            pred_score = round(lower + (upper - lower) * max(0.0, min(1.0, 0.18 + 0.7 * strength + (unit - 0.5) * 0.1)), 2)
            traits = {}
        assistant = {
            "pred_score": pred_score,
            "confidence": confidence,
            "justification": "Fake transport deterministic score for local contract validation only.",
            "evidence": {
                "matched_points": ["visible-rubric-point"],
                "missing_points": [],
                "concerns": [],
                "participating_agents": [],
                "recommend_escalation": strength < 0.4,
            },
            "trait_scores": traits,
        }
        serialized_body = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        image_count = sum(
            1
            for message in body.get("messages", [])
            for block in (message.get("content", []) if isinstance(message.get("content"), list) else [])
            if block.get("type") == "image_url"
        )
        text_tokens = max(1, (len(serialized_body) + 3) // 4)
        image_tokens = image_count * 256
        output_text = json.dumps(assistant, ensure_ascii=False, separators=(",", ":"))
        completion_tokens = max(1, (len(output_text) + 3) // 4)
        prompt_tokens = text_tokens + image_tokens
        return {
            "id": f"fake-chatcmpl-{call_number:05d}",
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": output_text},
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "prompt_tokens_details": {
                    "text_tokens": text_tokens,
                    "image_tokens": image_tokens,
                    "cached_tokens": 0,
                },
            },
        }


class ChatHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = int(status_code)


class SelfHostedChatCompletionsClient(LLMClient):
    is_fixture = False

    def __init__(
        self,
        *,
        provider: dict[str, Any],
        agents: dict[str, dict[str, Any]],
        transport: ChatTransport | None = None,
    ):
        self.provider = dict(provider)
        configured_agents = [dict(row) for row in agents.values() if not row.get("disabled")]
        agent_ids = [str(row.get("agent_id", "")).strip() for row in configured_agents]
        if not agent_ids or any(not value for value in agent_ids) or len(agent_ids) != len(set(agent_ids)):
            raise ValueError("自托管Agent配置必须包含非空且唯一的agent_id")
        self.agent_configs = {str(row["agent_id"]): row for row in configured_agents}
        self.base_url = str(provider["base_url"]).rstrip("/")
        if not self.base_url.endswith("/v1"):
            self.base_url += "/v1"
        self.api_key_env = str(provider.get("api_key_env", "SELFHOSTED_API_KEY"))
        self.require_api_key = bool(provider.get("require_api_key", False))
        self.timeout_seconds = float(provider.get("timeout_seconds", 180.0))
        self.max_attempts = int(provider.get("max_attempts", 2))
        self.retry_backoff_seconds = float(provider.get("retry_backoff_seconds", 1.0))
        self.require_reported_model_match = bool(provider.get("require_reported_model_match", True))
        self.require_usage = bool(provider.get("require_usage", True))
        self.require_multimodal_token_breakdown = bool(provider.get("require_multimodal_token_breakdown", True))
        self.prepared_root = Path(str(provider["prepared_root"]))
        self.pricing: PricingManifest = load_pricing_manifest(provider["pricing_manifest_path"])
        self.server_hourly_price_usd = provider.get("server_hourly_price_usd")
        self.budget = BudgetGuard(
            max_cost_usd=float(provider["max_cost_usd"]),
            max_total_calls=int(provider["max_total_calls"]),
        )
        self.attempt_log_path = _optional_path(provider.get("attempt_log_path"))
        self.transport = transport or _transport_from_provider(provider)
        self._attempt_lock = threading.Lock()
        self._attempt_numbers = _load_attempt_numbers(self.attempt_log_path)
        historical_calls, historical_cost = _load_attempt_budget(self.attempt_log_path)
        self.budget.initialize(calls=historical_calls, cost_usd=historical_cost)
        if self.max_attempts <= 0:
            raise ValueError("max_attempts 必须为正整数")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds 必须为正有限数值")
        if not math.isfinite(self.retry_backoff_seconds) or self.retry_backoff_seconds < 0.0:
            raise ValueError("retry_backoff_seconds 必须为非负有限数值")

    def initialize_budget(self, *, calls: int, cost_usd: float) -> None:
        current = self.budget.snapshot()
        self.budget.initialize(
            calls=max(int(calls), int(current["calls"])),
            cost_usd=max(float(cost_usd), float(current["cost_usd"])),
        )

    def budget_snapshot(self) -> dict[str, Any]:
        return {**self.budget.snapshot(), "transport_kind": self.transport.kind}

    def complete(
        self,
        request: dict[str, Any],
        agent_id: str,
        logical_call_id: str | None = None,
    ) -> ClientResponse:
        findings = find_banned_keys(request)
        if findings:
            raise ValueError(f"自托管请求包含禁用Gold字段: {findings[:10]}")
        if agent_id not in self.agent_configs:
            raise ValueError(f"未知 Agent 配置: {agent_id}")
        agent_config = self.agent_configs[agent_id]
        model_id = str(agent_config["model_id"])
        generation = dict(agent_config.get("generation_parameters") or {})
        body, assets = self._build_body(request, agent_id, model_id, generation)
        body_findings = _body_banned_key_findings(body)
        if body_findings:
            raise ValueError(f"序列化 Chat body 包含禁用Gold字段: {body_findings[:10]}")
        logical_id = logical_call_id or _stable_hash(
            {"agent_id": agent_id, "model_id": model_id, "request": request, "generation": generation}
        )
        api_key = os.environ.get(self.api_key_env, "").strip()
        if self.require_api_key and not api_key:
            raise RuntimeError(f"缺少自托管服务凭据环境变量: {self.api_key_env}")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        last_error: Exception | None = None
        for local_attempt_index in range(1, self.max_attempts + 1):
            attempt_number = self._next_attempt_number(logical_id)
            self.budget.reserve_call()
            started = time.perf_counter()
            attempt_id = _stable_hash({"logical_call_id": logical_id, "attempt_number": attempt_number})
            attempt_usage: TokenUsage | None = None
            attempt_cost = 0.0
            attempt_latency: float | None = None
            attempt_server_cost: float | None = None
            cost_booked = False
            reported_for_audit: str | None = None
            response_id_for_audit: str | None = None
            pricing_model_for_audit = model_id
            try:
                payload = self.transport.post_json(
                    url=f"{self.base_url}/chat/completions",
                    body=body,
                    headers=headers,
                    timeout_seconds=self.timeout_seconds,
                )
                attempt_latency = time.perf_counter() - started
                attempt_server_cost = compute_server_allocated_cost(
                    latency_seconds=attempt_latency,
                    server_hourly_price_usd=None if self.server_hourly_price_usd is None else float(self.server_hourly_price_usd),
                )
                reported_for_audit = str(payload.get("model", "")).strip() or None
                response_id_for_audit = str(payload.get("id", "")).strip() or None
                try:
                    attempt_usage = TokenUsage.from_api(payload.get("usage"))
                except Exception:
                    attempt_usage = None
                if attempt_usage is not None:
                    pricing_model_for_audit = reported_for_audit or model_id
                    try:
                        pricing_rule = self.pricing.rule_for(pricing_model_for_audit)
                    except (KeyError, ValueError):
                        # 模型替换仍然产生了资源消耗；无替换模型价格时按请求模型价格审计，不能记成0。
                        pricing_model_for_audit = model_id
                        pricing_rule = self.pricing.rule_for(model_id)
                    attempt_cost = compute_api_cost(attempt_usage, pricing_rule)
                response = self._parse_response(
                    payload,
                    requested_model_id=model_id,
                    latency=attempt_latency,
                    attempt_number=attempt_number,
                    attempt_id=attempt_id,
                    logical_call_id=logical_id,
                    body=body,
                    request=request,
                    assets=assets,
                )
                # BudgetGuard.add_cost 会先记入已实际发生的成本，再在越过硬门时抛错。
                # 因此必须在调用前标记，避免异常分支把同一 attempt 的成本重复记账。
                cost_booked = True
                self.budget.add_cost(float(response.cost or 0.0))
                self._write_attempt(
                    agent_id=agent_id,
                    requested_model_id=model_id,
                    logical_call_id=logical_id,
                    attempt_id=attempt_id,
                    attempt_number=attempt_number,
                    status="success",
                    latency=attempt_latency,
                    request_body_sha256=str(response.metadata["request_body_sha256"]),
                    reported_model_id=str(response.metadata["reported_model_id"]),
                    response_id=str(response.metadata["response_id"]),
                    pricing_model_id=str(response.metadata["reported_model_id"]),
                    usage=response.usage.to_dict(),
                    cost_usd=float(response.cost or 0.0),
                    actual_server_allocated_cost_usd=attempt_server_cost,
                    error=None,
                )
                return response
            except Exception as exc:
                if attempt_latency is None:
                    attempt_latency = time.perf_counter() - started
                if attempt_server_cost is None:
                    attempt_server_cost = compute_server_allocated_cost(
                        latency_seconds=attempt_latency,
                        server_hourly_price_usd=None if self.server_hourly_price_usd is None else float(self.server_hourly_price_usd),
                    )
                last_error = _normalize_transport_error(exc)
                retryable = _is_retryable(last_error)
                if attempt_cost > 0.0 and not cost_booked:
                    # 失败响应已经实际消耗Token；预算越界也必须先落attempt审计，不能被异常打断。
                    cost_booked = True
                    try:
                        self.budget.add_cost(attempt_cost)
                    except BudgetExceededError as budget_exc:
                        last_error = budget_exc
                        retryable = False
                self._write_attempt(
                    agent_id=agent_id,
                    requested_model_id=model_id,
                    logical_call_id=logical_id,
                    attempt_id=attempt_id,
                    attempt_number=attempt_number,
                    status="retryable_failure" if retryable and local_attempt_index < self.max_attempts else "terminal_failure",
                    latency=attempt_latency,
                    request_body_sha256=_stable_hash(body),
                    reported_model_id=reported_for_audit,
                    response_id=response_id_for_audit,
                    pricing_model_id=pricing_model_for_audit,
                    usage=None if attempt_usage is None else attempt_usage.to_dict(),
                    cost_usd=attempt_cost,
                    actual_server_allocated_cost_usd=attempt_server_cost,
                    error=f"{type(last_error).__name__}: {last_error}",
                )
                if not retryable or local_attempt_index >= self.max_attempts:
                    break
                time.sleep(self.retry_backoff_seconds * local_attempt_index)
        raise RuntimeError(f"自托管 Chat Completions 调用失败: {last_error}")

    def _build_body(
        self,
        request: dict[str, Any],
        agent_id: str,
        model_id: str,
        generation: dict[str, Any],
    ) -> tuple[dict[str, Any], list[PreparedAsset]]:
        visible = strip_banned_fields({key: value for key, value in request.items() if key != "prompt_template"})
        # Agent能力档位只能由model_id体现；移除角色名，保证三档模型可见语义除model外完全一致。
        visible.pop("role", None)
        source_assets = list(visible.pop("source_assets", []) or [])
        assets = prepare_source_assets(source_assets, prepared_root=self.prepared_root)
        visible["source_assets"] = [asset.audit_dict() for asset in assets]
        prompt_template = str(request.get("prompt_template", ""))
        if not prompt_template.strip():
            raise ValueError("自托管请求缺少非空统一评分Prompt")
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": json.dumps(
                    {"request": visible},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        ]
        content.extend(asset.chat_content_block() for asset in assets)
        body = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": prompt_template},
                {"role": "user", "content": content},
            ],
            "temperature": float(generation.get("temperature", 0.0)),
            "max_tokens": int(generation.get("max_tokens", generation.get("max_output_tokens", 768))),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "a2a_dygrade_agent_output_v2",
                    "strict": True,
                    "schema": SELFHOSTED_AGENT_RESPONSE_SCHEMA,
                },
            },
        }
        if body["temperature"] != 0.0:
            raise ValueError("自托管 checkpoint 必须使用 temperature=0")
        if bool(generation.get("enable_thinking", False)):
            raise ValueError("自托管 checkpoint 禁止 enable_thinking")
        return body, assets

    def _parse_response(
        self,
        payload: dict[str, Any],
        *,
        requested_model_id: str,
        latency: float,
        attempt_number: int,
        attempt_id: str,
        logical_call_id: str,
        body: dict[str, Any],
        request: dict[str, Any],
        assets: list[PreparedAsset],
    ) -> ClientResponse:
        response_id = str(payload.get("id", "")).strip()
        if not response_id:
            raise ValueError("Chat Completions 缺少响应ID")
        reported_model_id = str(payload.get("model", "")).strip()
        if not reported_model_id:
            raise ValueError("Chat Completions 缺少实际 model ID")
        if self.require_reported_model_match and not _model_matches(requested_model_id, reported_model_id):
            raise ValueError(f"模型静默替换: requested={requested_model_id}, reported={reported_model_id}")
        usage = TokenUsage.from_api(payload.get("usage"))
        if self.require_usage and usage.total_tokens <= 0:
            raise ValueError("Chat Completions 缺少有效 token usage")
        if assets and self.require_multimodal_token_breakdown and usage.input_vision_tokens <= 0:
            raise ValueError("多模态响应缺少服务器/Processor视觉Token分解")
        output_text, finish_reason = _extract_chat_output(payload)
        parsed = json.loads(output_text)
        if not isinstance(parsed, dict):
            raise ValueError("Agent结构化输出顶层必须是对象")
        _validate_structured_payload(parsed)
        _validate_scoring_semantics(parsed, request=request)
        rule = self.pricing.rule_for(reported_model_id)
        official_cost = compute_api_cost(usage, rule)
        actual_server_cost = compute_server_allocated_cost(
            latency_seconds=latency,
            server_hourly_price_usd=None if self.server_hourly_price_usd is None else float(self.server_hourly_price_usd),
        )
        request_body_sha = _stable_hash(body)
        metadata = {
            "client": "SelfHostedChatCompletionsClient",
            "provider_id": str(self.provider.get("provider_id", "self_hosted")),
            "gateway_id": str(self.provider.get("gateway_id", "openai_chat_completions")),
            "transport_kind": self.transport.kind,
            "requested_model_id": requested_model_id,
            "reported_model_id": reported_model_id,
            "response_id": response_id,
            "finish_reason": finish_reason,
            "attempt_count": attempt_number,
            "canonical_attempt_id": attempt_id,
            "logical_call_id": logical_call_id,
            "request_body_sha256": request_body_sha,
            "request_semantics_sha256": _stable_hash({key: value for key, value in body.items() if key != "model"}),
            "schema_sha256": _stable_hash(SELFHOSTED_AGENT_RESPONSE_SCHEMA),
            "gold_key_findings": [],
            "asset_audit": [asset.audit_dict() for asset in assets],
            "usage": usage.to_dict(),
            "pricing": {
                "manifest_sha256": self.pricing.sha256,
                "effective_date": self.pricing.effective_date,
                "currency": self.pricing.currency,
                "pricing_type": "official_api_equivalent",
                "official_api_equivalent_cost_usd": official_cost,
                "actual_server_allocated_cost_usd": actual_server_cost,
            },
        }
        return ClientResponse(
            payload=parsed,
            token_usage=usage.total_tokens,
            latency=float(latency),
            metadata=metadata,
            usage=usage,
            cost=official_cost,
        )

    def _next_attempt_number(self, logical_call_id: str) -> int:
        with self._attempt_lock:
            number = self._attempt_numbers.get(logical_call_id, 0) + 1
            self._attempt_numbers[logical_call_id] = number
            return number

    def _write_attempt(
        self,
        *,
        agent_id: str,
        requested_model_id: str,
        logical_call_id: str,
        attempt_id: str,
        attempt_number: int,
        status: str,
        latency: float,
        request_body_sha256: str,
        reported_model_id: str | None,
        response_id: str | None,
        pricing_model_id: str,
        usage: dict[str, Any] | None,
        cost_usd: float,
        actual_server_allocated_cost_usd: float | None,
        error: str | None,
    ) -> None:
        if self.attempt_log_path is None:
            return
        record = {
            "agent_id": agent_id,
            "requested_model_id": requested_model_id,
            "logical_call_id": logical_call_id,
            "attempt_id": attempt_id,
            "attempt_number": attempt_number,
            "status": status,
            "latency_seconds": float(latency),
            "request_body_sha256": request_body_sha256,
            "reported_model_id": reported_model_id,
            "response_id": response_id,
            "pricing_model_id": pricing_model_id,
            "usage": usage,
            "official_api_equivalent_cost_usd": float(cost_usd),
            "actual_server_allocated_cost_usd": actual_server_allocated_cost_usd,
            "error": error,
            "transport_kind": self.transport.kind,
        }
        with self._attempt_lock:
            _append_jsonl(self.attempt_log_path, record)


def _validate_structured_payload(payload: dict[str, Any]) -> None:
    expected = {"pred_score", "confidence", "justification", "evidence", "trait_scores"}
    if set(payload) != expected:
        raise ValueError(f"Agent结构化输出字段不匹配: expected={sorted(expected)} actual={sorted(payload)}")
    for field in ("pred_score", "confidence"):
        value = payload[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError(f"Agent结构化输出 {field} 必须为有限数值")
    confidence = float(payload["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("Agent结构化输出 confidence 越界")
    if not isinstance(payload["justification"], str) or not payload["justification"].strip():
        raise ValueError("Agent结构化输出 justification 不能为空")
    evidence = payload["evidence"]
    evidence_fields = {"matched_points", "missing_points", "concerns", "participating_agents", "recommend_escalation"}
    if not isinstance(evidence, dict) or set(evidence) != evidence_fields:
        raise ValueError("Agent结构化输出 evidence 字段不完整")
    for field in ("matched_points", "missing_points", "concerns", "participating_agents"):
        values = evidence[field]
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"Agent结构化输出 evidence.{field} 必须为字符串数组")
    if not isinstance(evidence["recommend_escalation"], bool):
        raise ValueError("Agent结构化输出 evidence.recommend_escalation 必须为布尔值")
    traits = payload["trait_scores"]
    if not isinstance(traits, dict) or not set(traits).issubset({"content", "organization", "language"}):
        raise ValueError("Agent结构化输出 trait_scores 字段非法")
    for name, value in traits.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 5.0:
            raise ValueError(f"Agent结构化输出 trait_scores.{name} 非法")


def _validate_scoring_semantics(payload: dict[str, Any], *, request: dict[str, Any]) -> None:
    score_range = dict(request.get("score_range") or {})
    lower = float(score_range["min"])
    upper = float(score_range["max"])
    pred_score = float(payload["pred_score"])
    if not lower <= pred_score <= upper:
        raise ValueError(f"Agent结构化输出 pred_score 越界: {pred_score} not in [{lower}, {upper}]")

    traits = dict(payload.get("trait_scores") or {})
    if str(request.get("scoring_mode", "")) == "analytic_three_dimension":
        expected = {"content", "organization", "language"}
        if set(traits) != expected:
            raise ValueError("DREsS必须返回Content、Organization、Language三个trait_scores")
        if abs(sum(float(traits[name]) for name in expected) - pred_score) > 1e-6:
            raise ValueError("DREsS pred_score必须等于三个trait_scores之和")
    elif traits:
        raise ValueError("非DREsS响应的trait_scores必须为空")


def _transport_from_provider(provider: dict[str, Any]) -> ChatTransport:
    kind = str(provider.get("transport", "urllib")).lower()
    if kind == "urllib":
        return UrllibChatTransport()
    if kind == "fake":
        return FakeChatTransport(capture_path=_optional_path(provider.get("captured_request_log_path")))
    raise ValueError(f"不支持的自托管 transport: {kind}")


def _extract_chat_output(payload: dict[str, Any]) -> tuple[str, str]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Chat Completions 必须恰好包含一个 choice")
    choice = dict(choices[0])
    finish_reason = str(choice.get("finish_reason", ""))
    if finish_reason not in {"stop", "completed"}:
        raise ValueError(f"Chat Completions 未正常结束: {finish_reason}")
    message = dict(choice.get("message") or {})
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "".join(str(block.get("text", "")) for block in content if isinstance(block, dict)).strip()
    else:
        text = ""
    if not text:
        raise ValueError("Chat Completions 缺少 assistant content")
    return text, finish_reason


def _extract_fake_request(body: dict[str, Any]) -> dict[str, Any]:
    messages = list(body.get("messages") or [])
    if len(messages) < 2:
        raise ValueError("Fake transport 请求缺少user message")
    content = messages[-1].get("content")
    if not isinstance(content, list) or not content or content[0].get("type") != "text":
        raise ValueError("Fake transport 请求缺少text block")
    payload = json.loads(str(content[0]["text"]))
    return dict(payload["request"])


def _body_banned_key_findings(body: dict[str, Any]) -> list[str]:
    findings = find_banned_keys(body)
    for message_index, message in enumerate(body.get("messages") or []):
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block_index, block in enumerate(content):
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            try:
                payload = json.loads(str(block.get("text", "")))
            except json.JSONDecodeError:
                continue
            findings.extend(find_banned_keys(payload, path=f"$.messages[{message_index}].content[{block_index}].text_json"))
    return findings


def _model_matches(requested: str, reported: str) -> bool:
    # 自托管服务使用冻结的 served-model-name；任何后缀或别名都视为身份不一致。
    return requested == reported


def _normalize_transport_error(exc: Exception) -> Exception:
    if isinstance(exc, ChatHTTPError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            detail = ""
        return ChatHTTPError(exc.code, f"HTTP {exc.code}: {detail}")
    return exc


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ChatHTTPError):
        return exc.status_code in {408, 409, 429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, urllib.error.URLError, ConnectionError))


def _optional_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    return Path(text) if text else None


def _load_attempt_numbers(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return {}
    result: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        logical_call_id = str(row.get("logical_call_id", ""))
        attempt_number = int(row.get("attempt_number", 0))
        if logical_call_id:
            result[logical_call_id] = max(result.get(logical_call_id, 0), attempt_number)
    return result


def _load_attempt_budget(path: Path | None) -> tuple[int, float]:
    if path is None or not path.exists():
        return 0, 0.0
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cost = sum(float(row.get("official_api_equivalent_cost_usd", 0.0)) for row in rows)
    if not math.isfinite(cost) or cost < 0.0:
        raise ValueError("attempt日志中的累计成本非法")
    return len(rows), cost


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
