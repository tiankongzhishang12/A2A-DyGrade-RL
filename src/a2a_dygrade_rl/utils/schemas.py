"""实验产物 schema。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Item:
    item_id: str
    dataset: str
    question_type: str
    subject: str
    prompt: str
    student_answer: str
    reference_answer: str
    rubric: str
    gold_score: float
    score_min: float
    score_max: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PaperBudget:
    max_cost: float
    max_latency: float
    max_agent_calls: int
    max_a2a_messages: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Paper:
    paper_id: str
    items: list[str]
    paper_budget: PaperBudget
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["paper_budget"] = self.paper_budget.to_dict()
        return data


@dataclass(frozen=True)
class AgentOutput:
    item_id: str
    agent_id: str
    run_id: str
    execution_mode: str
    is_fixture: bool
    pred_score: float | None
    confidence: float
    justification: str
    evidence: dict[str, Any]
    cost: float
    latency: float
    token_usage: int
    gold_score: float
    split: str
    model_id: str
    prompt_version: str
    prompt_hash: str
    input_hash: str
    context_hash: str
    cache_key: str
    cache_schema_version: str
    status: str
    error: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class A2AMessage:
    message_id: str
    paper_id: str
    item_id: str
    message_type: str
    sender: str
    receiver: str
    payload: dict[str, Any]
    response: dict[str, Any]
    cost: float
    latency: float


@dataclass(frozen=True)
class RoutingState:
    paper_id: str
    step: int
    item_states: dict[str, Any]
    difficulty_state: dict[str, Any]
    agent_capability_state: dict[str, Any]
    a2a_history_state: dict[str, Any]
    remaining_budget: dict[str, float]
    valid_action_mask: dict[str, bool]


@dataclass(frozen=True)
class Trajectory:
    trajectory_id: str
    paper_id: str
    steps: list[dict[str, Any]]
    total_cost: float
    makespan: float
    messages: list[dict[str, Any]]
    final_scores: dict[str, float]
    quality_metrics: dict[str, float]
    budget_violation: bool
    source_policy: str


@dataclass(frozen=True)
class ExperimentReport:
    method: str
    split: str
    seed: int
    qwk: float
    mae: float
    rmse: float
    within_1_accuracy: float
    cost_per_paper: float
    paper_latency: float
    token_usage: float
    agent_calls: float
    a2a_messages: float
    useful_communication_rate: float
    disagreement_reduction: float
    arbitration_rate: float
    budget_violation_rate: float
