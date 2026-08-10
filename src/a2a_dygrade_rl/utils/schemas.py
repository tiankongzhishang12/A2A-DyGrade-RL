"""实验数据、质量协议与选择产物的标准 schema。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar


class _Serializable:
    """为文件型实验产物提供稳定的字典序列化。"""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Item(_Serializable):
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


@dataclass(frozen=True, init=False)
class PaperBudget(_Serializable):
    """Paper 四维预算。

    正式字段统一为 ``max_elapsed_time`` 与 ``max_a2a_exchanges``。构造器仍接受
    legacy ``max_latency``/``max_a2a_messages``，便于读取已有 fixture 和外部
    prepared data；序列化始终输出正式字段。
    """

    max_cost: float
    max_elapsed_time: float
    max_agent_calls: int
    max_a2a_exchanges: int

    def __init__(
        self,
        max_cost: float,
        max_elapsed_time: float | None = None,
        max_agent_calls: int = 0,
        max_a2a_exchanges: int | None = None,
        *,
        max_latency: float | None = None,
        max_a2a_messages: int | None = None,
    ) -> None:
        elapsed = max_elapsed_time if max_elapsed_time is not None else max_latency
        exchanges = max_a2a_exchanges if max_a2a_exchanges is not None else max_a2a_messages
        if elapsed is None:
            raise ValueError("PaperBudget 缺少 max_elapsed_time")
        if exchanges is None:
            raise ValueError("PaperBudget 缺少 max_a2a_exchanges")
        object.__setattr__(self, "max_cost", float(max_cost))
        object.__setattr__(self, "max_elapsed_time", float(elapsed))
        object.__setattr__(self, "max_agent_calls", int(max_agent_calls))
        object.__setattr__(self, "max_a2a_exchanges", int(exchanges))

    @property
    def max_latency(self) -> float:
        return self.max_elapsed_time

    @property
    def max_a2a_messages(self) -> int:
        return self.max_a2a_exchanges


@dataclass(frozen=True)
class Paper(_Serializable):
    paper_id: str
    items: list[str]
    paper_budget: PaperBudget
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["paper_budget"] = self.paper_budget.to_dict()
        return data


@dataclass(frozen=True)
class AgentOutput(_Serializable):
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


@dataclass(frozen=True)
class A2AMessage(_Serializable):
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
class RoutingState(_Serializable):
    paper_id: str
    step: int
    item_states: dict[str, Any]
    difficulty_state: dict[str, Any]
    agent_capability_state: dict[str, Any]
    a2a_history_state: dict[str, Any]
    remaining_budget: dict[str, float]
    valid_action_mask: dict[str, bool]


@dataclass(frozen=True)
class Trajectory(_Serializable):
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
class ExperimentReport(_Serializable):
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


@dataclass(frozen=True)
class InternalItemSplitManifest(_Serializable):
    item_id: str
    dataset: str
    prompt_group: str
    leakage_component_id: str
    component_id: str
    component_size: int
    source_split: str
    internal_split: str
    seed: int
    rule_version: str
    assignment_unit: str
    stable_hash: str
    source_paper_ids: str = ""


@dataclass(frozen=True)
class InternalPaperManifest(_Serializable):
    paper_id: str
    internal_split: str
    item_id: str
    paper_position: int
    dataset: str
    prompt_group: str
    component_id: str
    strict_quota_id: str
    paper_dataset_mix: str
    seed: int
    rule_version: str
    source_paper_ids: str = ""


@dataclass(frozen=True)
class LeftoverRecord(_Serializable):
    item_id: str
    dataset: str
    internal_split: str
    prompt_group: str
    component_id: str
    reason: str
    seed: int
    rule_version: str
    source_paper_ids: str = ""


@dataclass(frozen=True)
class QualityMetricProtocol(_Serializable):
    """V1.3 正式质量协议及 V1.4 Dev 选择顺序。"""

    FORMAL_DATASETS: ClassVar[tuple[str, ...]] = ("asap_sas", "sas_bench", "dress")
    FORMAL_BUDGETS: ClassVar[tuple[str, ...]] = ("Tight", "Medium", "Loose")

    protocol_version: str = "quality_protocol_v1.3"
    datasets: tuple[str, ...] = FORMAL_DATASETS
    gate_error_invalid_value: float = 1.0
    severe_threshold: float = 0.25
    severe_operator: str = ">"
    extreme_threshold: float = 0.50
    extreme_operator: str = ">="
    unsafe_stop_denominator: str = "all_stops"
    zero_stop_policy: str = "na_quality_infeasible"
    qwk_bin_count: int = 11
    qwk_fixed_labels: tuple[int, ...] = tuple(range(11))
    qwk_mapping: str = "floor(10*z+0.5)_clip_0_10"
    qwk_min_valid_completed: int = 100
    qwk_min_gold_nonempty_bins: int = 2
    qwk_require_positive_expected_disagreement: bool = True
    bootstrap_unit: str = "paper"
    bootstrap_paired: bool = True
    bootstrap_replicates: int = 5000
    bootstrap_confidence_level: float = 0.95
    bootstrap_sidedness: str = "one_sided"
    noninferiority_margin: float = 0.0
    bootstrap_seed: int = 20260729
    bootstrap_quantile_method: str = "conservative_nearest_rank"
    budget_ids: tuple[str, ...] = FORMAL_BUDGETS
    reference_gate_order: tuple[str, ...] = (
        "max_dataset_delta_severe",
        "max_dataset_delta_unsafe_stop",
        "delta_macro_nmae",
        "delta_macro_qwk",
    )
    quality_champion_order: tuple[str, ...] = (
        "worst_budget_dataset_severe",
        "worst_budget_dataset_unsafe_stop",
        "mean_budget_macro_nmae",
        "mean_budget_macro_qwk_desc",
        "package_id",
    )
    resource_order: tuple[str, ...] = (
        "mean_budget_cost_per_paper",
        "mean_budget_elapsed_time_per_paper",
        "mean_budget_agent_calls_per_paper",
        "mean_budget_a2a_exchanges_per_paper",
        "package_id",
    )

    @classmethod
    def formal_v13(cls, **overrides: Any) -> "QualityMetricProtocol":
        return cls(**overrides)


@dataclass(frozen=True)
class QWKReadinessRecord(_Serializable):
    dataset: str
    valid_completed_n: int
    gold_nonempty_bin_count: int
    expected_weighted_disagreement: float
    fixed_labels: tuple[int, ...]
    qwk_defined: bool
    qwk: float | None
    readiness_failure_reason: str = ""


@dataclass(frozen=True)
class PairedBootstrapGateResult(_Serializable):
    candidate_id: str
    comparator_id: str
    budget_id: str
    comparison_kind: str
    unit: str
    paired: bool
    replicates: int
    confidence_level: float
    noninferiority_margin: float
    seed: int
    point_max_dataset_delta_severe: float | None
    ucb95_max_dataset_delta_severe: float | None
    point_max_dataset_delta_unsafe_stop: float | None
    ucb95_max_dataset_delta_unsafe_stop: float | None
    point_delta_macro_nmae: float | None
    ucb95_delta_macro_nmae: float | None
    point_delta_macro_qwk: float | None
    lcb95_delta_macro_qwk: float | None
    pass_max_dataset_delta_severe: bool
    pass_max_dataset_delta_unsafe_stop: bool
    pass_delta_macro_nmae: bool
    pass_delta_macro_qwk: bool
    quality_feasible: bool
    status: str
    failure_reason: str
    quality_protocol_hash: str
    resample_index_digest: str
    reconstruction: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationPackage(_Serializable):
    package_id: str
    checkpoint_id: str
    checkpoint_hash: str
    calibration_status: str
    stop_boundary: float | None
    calibration_failure_reason: str
    boundary_frozen: bool
    calibration_split: str
    calibration_no_gradient: bool
    calibration_no_replay: bool
    calibration_no_checkpoint_ranking: bool
    main_method_upgrade_thresholds: dict[str, float]
    quality_protocol_hash: str
    internal_manifest_hash: str
    quality_reference_manifest_hash: str
    budget_manifest_hash: str
    support_manifest_hash: str
    coverage: float | None = None


@dataclass(frozen=True)
class PolicyPackage(_Serializable):
    package_id: str
    checkpoint_id: str
    checkpoint_hash: str
    calibration_package_hash: str
    package_role: str
    calibration_status: str
    stop_boundary: float | None
    boundary_frozen: bool
    dev_boundary_updates: int
    quality_protocol_hash: str
    internal_manifest_hash: str
    quality_reference_manifest_hash: str
    budget_manifest_hash: str
    support_manifest_hash: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityReferenceManifest(_Serializable):
    manifest_version: str
    split: str
    budget_to_reference_policy: dict[str, str]
    candidates: list[dict[str, Any]]
    quality_protocol_hash: str
    internal_manifest_hash: str
    cache_hash: str
    seed: int
    budget_failures: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BudgetCalibrationManifest(_Serializable):
    manifest_version: str
    split: str
    budgets: dict[str, dict[str, float | int]]
    quantiles: dict[str, float]
    policy_ids: tuple[str, ...]
    internal_manifest_hash: str
    cache_hash: str
    config_hash: str
    seed: int


@dataclass(frozen=True)
class CapabilitySupportManifest(_Serializable):
    manifest_version: str
    fit_split: str
    calibration_split: str
    support_quantile: float
    low_support_count_boundary: int
    uncertainty_boundary: float
    fit_profile_hash: str
    calibration_support_hash: str
    internal_manifest_hash: str
    cache_hash: str
    seed: int
    calibration_no_gradient: bool
    no_item_oracle_labels: bool


@dataclass(frozen=True)
class StopBoundaryCalibrationRecord(_Serializable):
    checkpoint_id: str
    checkpoint_hash: str
    calibration_split: str
    calibration_status: str
    stop_boundary: float | None
    coverage: float
    failure_reason: str
    risk_limit: float
    confidence_level: float
    min_stops_per_dataset: int
    per_dataset_support: dict[str, Any]
    calibration_no_gradient: bool
    calibration_no_replay: bool
    calibration_no_checkpoint_ranking: bool


@dataclass(frozen=True)
class FixtureSmokeRunManifest(_Serializable):
    manifest_version: str
    run_id: str
    execution_mode: str
    is_fixture: bool
    formal_eligible: bool
    online_agent_calls: int
    seed: int
    fixture_blueprint_hash: str
    fixture_config_hash: str
    quality_protocol_hash: str
    core_pipeline_modules: tuple[str, ...]
    core_module_hashes: dict[str, str]
    audit_counters: dict[str, int]


@dataclass(frozen=True)
class QualityChampionManifest(_Serializable):
    manifest_version: str
    split: str
    package_id: str
    checkpoint_id: str
    quality_key: tuple[Any, ...]
    quality_champion_no_resource: bool
    manual_override_count: int
    quality_protocol_hash: str


@dataclass(frozen=True)
class QualityProtectionManifest(_Serializable):
    manifest_version: str
    split: str
    champion_package_id: str
    feasible_package_ids: tuple[str, ...]
    candidate_to_champion_gate: bool
    gate_results: list[dict[str, Any]]
    quality_protocol_hash: str


@dataclass(frozen=True)
class PolicyFreezeManifest(_Serializable):
    manifest_version: str
    selected_package_id: str
    selected_checkpoint_id: str
    quality_champion_package_id: str
    budget_ids: tuple[str, ...]
    stop_boundary: float
    package_hash: str
    quality_protocol_hash: str
    internal_manifest_hash: str
    quality_reference_manifest_hash: str
    budget_manifest_hash: str
    support_manifest_hash: str
    dev_boundary_update_count: int
    quality_champion_manual_override_count: int
    selection_rule_version: str
