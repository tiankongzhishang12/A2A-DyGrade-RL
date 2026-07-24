"""Provider-neutral LLM client contracts and deterministic fixture client."""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClientResponse:
    payload: dict[str, Any]
    token_usage: int
    latency: float
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMClient(ABC):
    is_fixture = False

    @abstractmethod
    def complete(self, request: dict[str, Any], agent_id: str) -> ClientResponse:
        raise NotImplementedError


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
        return ClientResponse(
            payload=payload,
            token_usage=token_usage,
            latency=round(0.01 + 0.02 * conf_unit, 6),
            metadata={"client": "FixtureClient", "seed": self.seed},
        )
