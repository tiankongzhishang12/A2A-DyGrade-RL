"""Shared Agent wrapper contract."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.llm_client import LLMClient
from a2a_dygrade_rl.utils.model_input import project_model_visible_item, strip_banned_fields


def strip_gold(value: Any) -> Any:
    """历史兼容名称：递归移除所有模型不可见 Gold/标签字段。"""

    return strip_banned_fields(value)

class BaseAgent(ABC):
    role = "base"

    def __init__(self, config: dict[str, Any], client: LLMClient):
        if self.__class__ is BaseAgent:
            raise TypeError("BaseAgent 不能直接实例化")
        self.config = dict(config)
        self.client = client
        self.agent_id = str(config["agent_id"])
        self.model_id = str(config.get("model_id", "unconfigured"))
        self.model_revision = str(config.get("model_revision", "unknown"))
        self.prompt_version = str(config.get("prompt_version", "v1"))
        prompt_path = Path(str(config.get("prompt_path", "")))
        self.prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else str(config.get("prompt", ""))
        self.prompt_hash = hashlib.sha256(self.prompt_text.encode("utf-8")).hexdigest()

    def build_request(self, item: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        request = project_model_visible_item(item)
        request.update(
            {
                "score_range": {"min": float(item["score_min"]), "max": float(item["score_max"])},
                "prompt_template": self.prompt_text,
                "prompt_version": self.prompt_version,
                "role": self.role,
                "context": strip_gold(context or {}),
            }
        )
        return strip_gold(request)

    def predict(self, item: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        request = self.build_request(item, context)
        response = self.client.complete(request, self.agent_id)
        parsed = self.parse_response(response.payload)
        parsed["token_usage"] = int(response.token_usage)
        parsed["usage"] = response.usage.to_dict()
        parsed["latency"] = max(float(self.config.get("latency", response.latency)), float(response.latency))
        parsed["cost"] = float(response.cost) if response.cost is not None else self.estimate_cost(response.token_usage)
        parsed["client_metadata"] = response.metadata
        parsed["request"] = request
        self.validate_prediction(parsed, item)
        return parsed

    def parse_response(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        return {
            "pred_score": float(raw_response["pred_score"]),
            "confidence": float(raw_response["confidence"]),
            "justification": str(raw_response["justification"]),
            "evidence": dict(raw_response.get("evidence", {})),
        }

    def validate_prediction(self, prediction: dict[str, Any], item: dict[str, Any]) -> None:
        if not float(item["score_min"]) <= prediction["pred_score"] <= float(item["score_max"]):
            raise ValueError(f"{self.agent_id} pred_score 越界")
        if not 0.0 <= prediction["confidence"] <= 1.0:
            raise ValueError(f"{self.agent_id} confidence 越界")

    def estimate_cost(self, token_usage: int) -> float:
        if "cost_per_token" in self.config:
            return float(self.config["cost_per_token"]) * token_usage
        return float(self.config.get("cost", 0.0))

    @property
    @abstractmethod
    def role_name(self) -> str:
        raise NotImplementedError

