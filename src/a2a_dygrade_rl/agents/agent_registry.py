"""Agent registry with explicit fixture/real mode gates."""

from __future__ import annotations

from typing import Any

from a2a_dygrade_rl.agents.arbitrator_agent import ArbitratorAgent
from a2a_dygrade_rl.agents.cheap_agent import CheapAgent
from a2a_dygrade_rl.agents.evidence_agent import EvidenceAgent
from a2a_dygrade_rl.agents.mid_agent import MidAgent
from a2a_dygrade_rl.agents.strong_agent import StrongAgent
from a2a_dygrade_rl.utils.llm_client import LLMClient, build_llm_client


AGENT_CLASSES = {
    "CheapAgent": CheapAgent,
    "MidAgent": MidAgent,
    "StrongAgent": StrongAgent,
    "EvidenceAgent": EvidenceAgent,
    "ArbitratorAgent": ArbitratorAgent,
}


def build_agent_registry(
    config: dict[str, Any],
    execution_mode: str,
    seed: int,
    client: LLMClient | None = None,
) -> dict[str, Any]:
    is_fixture_mode = execution_mode == "fixture_smoke"
    if client is None:
        client = build_llm_client(config, execution_mode=execution_mode, seed=seed)
    if is_fixture_mode != bool(client.is_fixture):
        raise ValueError("LLM client 与 execution_mode 不匹配")

    registry: dict[str, Any] = {}
    disabled_ids = {
        str(agent_config["agent_id"])
        for agent_config in config.get("agents", {}).values()
        if bool(agent_config.get("disabled", False))
    }
    for agent_config in config.get("agents", {}).values():
        agent_id = str(agent_config["agent_id"])
        if agent_id not in AGENT_CLASSES:
            raise ValueError(f"未知 Agent 类型: {agent_id}")
        if bool(agent_config.get("disabled", False)):
            continue
        configured_fixture = str(agent_config.get("mode", "fixture")) == "fixture"
        provider_type = str(config.get("provider", {}).get("type", ""))
        fake_selfhosted = is_fixture_mode and provider_type == "openai_chat_completions_compatible" and getattr(client, "transport", None) is not None and client.transport.kind == "fake"
        if configured_fixture != is_fixture_mode and not fake_selfhosted:
            raise ValueError(f"Agent 配置模式与 execution_mode 不一致: {agent_id}")
        registry[agent_id] = AGENT_CLASSES[agent_id](agent_config, client)
    missing = set(AGENT_CLASSES) - set(registry) - disabled_ids
    if missing:
        raise ValueError(f"Agent registry 缺少角色: {sorted(missing)}")
    return registry
