"""真实 Agent token 使用量、官方价格快照与预算门。"""

from __future__ import annotations

import math
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.io import file_sha256, read_yaml


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    input_text_tokens: int = 0
    input_vision_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_api(cls, usage: dict[str, Any] | None) -> "TokenUsage":
        payload = dict(usage or {})
        input_details = dict(payload.get("input_tokens_details") or payload.get("prompt_tokens_details") or {})
        output_details = dict(payload.get("output_tokens_details") or payload.get("completion_tokens_details") or {})
        input_tokens = _nonnegative_int(payload.get("input_tokens", payload.get("prompt_tokens", 0)), "input_tokens")
        input_text_tokens = _nonnegative_int(
            input_details.get("text_tokens", input_details.get("text_input_tokens", 0)),
            "input_text_tokens",
        )
        input_vision_tokens = _nonnegative_int(
            input_details.get("image_tokens", input_details.get("vision_tokens", input_details.get("image_input_tokens", 0))),
            "input_vision_tokens",
        )
        cached = _nonnegative_int(input_details.get("cached_tokens", 0), "cached_input_tokens")
        cache_write = _nonnegative_int(input_details.get("cache_write_tokens", 0), "cache_write_tokens")
        output_tokens = _nonnegative_int(payload.get("output_tokens", payload.get("completion_tokens", 0)), "output_tokens")
        reasoning = _nonnegative_int(output_details.get("reasoning_tokens", 0), "reasoning_tokens")
        total = _nonnegative_int(payload.get("total_tokens", input_tokens + output_tokens), "total_tokens")
        result = cls(
            input_tokens=input_tokens,
            input_text_tokens=input_text_tokens,
            input_vision_tokens=input_vision_tokens,
            cached_input_tokens=cached,
            cache_write_tokens=cache_write,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning,
            total_tokens=total,
        )
        result.validate()
        return result

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"TokenUsage {name} 必须为非负整数")
        if self.input_text_tokens + self.input_vision_tokens > self.input_tokens:
            raise ValueError("input_text_tokens + input_vision_tokens 不得大于 input_tokens")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens 不得大于 input_tokens")
        if self.cached_input_tokens + self.cache_write_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens + cache_write_tokens 不得大于 input_tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning_tokens 不得大于 output_tokens")
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens 必须等于 input_tokens + output_tokens")

    @property
    def ordinary_input_tokens(self) -> int:
        """不属于缓存读取或缓存写入分区的普通输入Token。"""

        return self.input_tokens - self.cached_input_tokens - self.cache_write_tokens

    @property
    def uncached_input_tokens(self) -> int:
        """兼容旧调用方；语义为普通输入分区，不包含另行计价的cache-write Token。"""

        return self.ordinary_input_tokens

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class PricingRule:
    model_id: str
    input_per_million_usd: float
    cached_input_per_million_usd: float
    cache_write_per_million_usd: float
    output_per_million_usd: float
    long_context_threshold_input_tokens: int | None = None
    long_context_input_multiplier: float = 1.0
    long_context_output_multiplier: float = 1.0

    def validate(self) -> None:
        for name in (
            "input_per_million_usd",
            "cached_input_per_million_usd",
            "cache_write_per_million_usd",
            "output_per_million_usd",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"PricingRule {name} must be finite and nonnegative")
        if self.long_context_threshold_input_tokens is not None:
            if (
                isinstance(self.long_context_threshold_input_tokens, bool)
                or not isinstance(self.long_context_threshold_input_tokens, int)
                or self.long_context_threshold_input_tokens < 0
            ):
                raise ValueError("long_context_threshold_input_tokens must be a nonnegative integer or None")
        for name in ("long_context_input_multiplier", "long_context_output_multiplier"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"PricingRule {name} must be finite and positive")

    def multipliers_for(self, usage: TokenUsage) -> tuple[float, float]:
        self.validate()
        usage.validate()
        threshold = self.long_context_threshold_input_tokens
        if threshold is not None and usage.input_tokens > threshold:
            return self.long_context_input_multiplier, self.long_context_output_multiplier
        return 1.0, 1.0


@dataclass(frozen=True)
class PricingManifest:
    path: Path
    effective_date: str
    currency: str
    pricing_tier: str
    source: str
    sha256: str
    rules: dict[str, PricingRule]

    def rule_for(self, model_id: str) -> PricingRule:
        candidates = [model_id]
        if model_id.count("-") >= 3:
            parts = model_id.split("-")
            if len(parts) >= 4 and parts[-1].replace("-", "").isdigit():
                candidates.append("-".join(parts[:-1]))
        for candidate in candidates:
            if candidate in self.rules:
                return self.rules[candidate]
        raise ValueError(f"价格快照中没有模型: {model_id}")


def load_pricing_manifest(path: str | Path) -> PricingManifest:
    target = Path(path)
    payload = read_yaml(target)
    model_rows = payload.get("models")
    if not isinstance(model_rows, dict) or not model_rows:
        raise ValueError("Price manifest is missing models")
    long_context = dict(payload.get("long_context") or {})
    threshold_value = long_context.get("threshold_input_tokens")
    long_context_threshold = None if threshold_value is None else int(threshold_value)
    long_context_input_multiplier = float(long_context.get("input_multiplier", 1.0))
    long_context_output_multiplier = float(long_context.get("output_multiplier", 1.0))
    rules: dict[str, PricingRule] = {}
    for model_id, row in model_rows.items():
        values = dict(row or {})
        rule = PricingRule(
            model_id=str(model_id),
            input_per_million_usd=float(values["input_per_million_usd"]),
            cached_input_per_million_usd=float(values.get("cached_input_per_million_usd", values["input_per_million_usd"])),
            cache_write_per_million_usd=float(values.get("cache_write_per_million_usd", values["input_per_million_usd"])),
            output_per_million_usd=float(values["output_per_million_usd"]),
            long_context_threshold_input_tokens=long_context_threshold,
            long_context_input_multiplier=long_context_input_multiplier,
            long_context_output_multiplier=long_context_output_multiplier,
        )
        rule.validate()
        rules[rule.model_id] = rule
    return PricingManifest(
        path=target,
        effective_date=str(payload["effective_date"]),
        currency=str(payload.get("currency", "USD")),
        pricing_tier=str(payload.get("pricing_tier", "standard")),
        source=str(payload.get("source", "")),
        sha256=file_sha256(target),
        rules=rules,
    )


def compute_api_cost(usage: TokenUsage, rule: PricingRule) -> float:
    usage.validate()
    rule.validate()
    input_multiplier, output_multiplier = rule.multipliers_for(usage)
    total = (
        input_multiplier
        * (
            usage.ordinary_input_tokens * rule.input_per_million_usd
            + usage.cached_input_tokens * rule.cached_input_per_million_usd
            + usage.cache_write_tokens * rule.cache_write_per_million_usd
        )
        + output_multiplier * usage.output_tokens * rule.output_per_million_usd
    ) / 1_000_000.0
    if not math.isfinite(total) or total < 0.0:
        raise ValueError("Computed API cost is invalid")
    return float(total)


def compute_server_allocated_cost(
    *,
    latency_seconds: float,
    server_hourly_price_usd: float | None,
) -> float | None:
    """按单次请求占用时长分摊服务器租金；未冻结小时价时返回 None。"""

    if server_hourly_price_usd is None:
        return None
    latency = float(latency_seconds)
    hourly = float(server_hourly_price_usd)
    if not math.isfinite(latency) or latency < 0.0:
        raise ValueError("latency_seconds 必须为非负有限数值")
    if not math.isfinite(hourly) or hourly < 0.0:
        raise ValueError("server_hourly_price_usd 必须为非负有限数值")
    return hourly * latency / 3600.0


class BudgetExceededError(RuntimeError):
    """真实调用预算或调用次数硬门被触发。"""


class BudgetGuard:
    def __init__(self, *, max_cost_usd: float, max_total_calls: int):
        self.max_cost_usd = float(max_cost_usd)
        self.max_total_calls = int(max_total_calls)
        if not math.isfinite(self.max_cost_usd) or self.max_cost_usd <= 0.0:
            raise ValueError("max_cost_usd 必须为正有限数值")
        if self.max_total_calls <= 0:
            raise ValueError("max_total_calls 必须为正整数")
        self._calls = 0
        self._cost_usd = 0.0
        self._lock = threading.Lock()

    def initialize(self, *, calls: int, cost_usd: float) -> None:
        with self._lock:
            if calls < 0 or cost_usd < 0.0:
                raise ValueError("BudgetGuard 初始状态不得为负")
            if calls > self.max_total_calls or cost_usd > self.max_cost_usd:
                raise BudgetExceededError("已有运行产物已超过批准预算")
            self._calls = int(calls)
            self._cost_usd = float(cost_usd)

    def reserve_call(self) -> None:
        with self._lock:
            if self._calls >= self.max_total_calls:
                raise BudgetExceededError("达到 max_total_calls，拒绝创建新请求")
            if self._cost_usd >= self.max_cost_usd:
                raise BudgetExceededError("达到 max_cost_usd，拒绝创建新请求")
            self._calls += 1

    def add_cost(self, cost_usd: float) -> None:
        value = float(cost_usd)
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("调用成本必须为非负有限数值")
        with self._lock:
            self._cost_usd += value
            if self._cost_usd > self.max_cost_usd:
                raise BudgetExceededError(
                    f"累计 API 成本 {self._cost_usd:.8f} USD 超过硬门 {self.max_cost_usd:.8f} USD"
                )

    def snapshot(self) -> dict[str, float | int]:
        with self._lock:
            return {
                "calls": self._calls,
                "cost_usd": self._cost_usd,
                "max_total_calls": self.max_total_calls,
                "max_cost_usd": self.max_cost_usd,
            }


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} 不得为布尔值")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须为整数") from exc
    if result < 0:
        raise ValueError(f"{name} 必须非负")
    return result
