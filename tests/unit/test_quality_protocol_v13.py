from __future__ import annotations

from a2a_dygrade_rl.evaluation.quality_protocol import (
    evaluate_quality,
    gate_error,
    load_quality_protocol,
    protocol_fingerprint,
)
from a2a_dygrade_rl.evaluation.metrics_quality import quadratic_weighted_kappa_details
from a2a_dygrade_rl.evaluation.metrics_budget import budget_exhausted, budget_exhaustion_rate
from a2a_dygrade_rl.evaluation.failure_registry import FailureRecord, FailureRegistry


def _record(
    item_id: str,
    dataset: str,
    gold: float,
    pred: float | None,
    *,
    status: str = "completed",
    terminal_action: str = "STOP",
) -> dict:
    return {
        "paper_id": f"paper_{item_id}",
        "item_id": item_id,
        "dataset": dataset,
        "gold_score": gold,
        "pred_score": pred,
        "score_min": 0.0,
        "score_max": 4.0,
        "status": status,
        "terminal_action": terminal_action,
        "active_cache_valid": True,
    }


def test_gate_error_and_severe_extreme_boundaries_are_frozen():
    assert gate_error(gold_score=2, pred_score=3, score_min=0, score_max=4) == 0.25
    assert gate_error(gold_score=2, pred_score=None, score_min=0, score_max=4) == 1.0
    assert gate_error(gold_score=2, pred_score=5, score_min=0, score_max=4) == 1.0
    assert gate_error(gold_score=2, pred_score=2, score_min=0, score_max=4, status="deferred") == 1.0

    result = evaluate_quality(
        [
            _record("boundary", "dress", 2, 3),
            _record("severe", "dress", 2, 3.0001),
            _record("extreme", "dress", 2, 4),
        ],
        datasets=("dress",),
        qwk_min_valid_completed=1,
    )
    assert result["datasets"]["dress"]["severe_count"] == 2
    assert result["datasets"]["dress"]["extreme_count"] == 1


def test_deferral_enters_nmae_and_unsafe_stop_uses_all_stops_denominator():
    records = [
        _record("a", "asap_sas", 0, 0),
        _record("b", "asap_sas", 0, None, status="deferred"),
        _record("c", "sas_bench", 0, 0),
        _record("d", "sas_bench", 0, 2),
        _record("e", "dress", 0, 0),
        _record("f", "dress", 0, 1),  # Gate Error=0.25，不属于 Severe。
    ]
    result = evaluate_quality(records, qwk_min_valid_completed=1)
    assert result["datasets"]["asap_sas"]["nmae"] == 0.5
    assert result["datasets"]["sas_bench"]["nmae"] == 0.25
    assert result["datasets"]["dress"]["nmae"] == 0.125
    assert result["macro_nmae"] == (0.5 + 0.25 + 0.125) / 3
    assert result["unsafe_stop_count"] == 2
    assert result["stop_count"] == 6
    assert result["unsafe_stop_rate"] == 2 / 6
    assert result["deferral_rate"] == 1 / 6


def test_zero_stop_is_na_and_quality_infeasible():
    record = _record("a", "dress", 0, 0, terminal_action="ARBITRATE")
    result = evaluate_quality([record], datasets=("dress",), qwk_min_valid_completed=1)
    assert result["stop_count"] == 0
    assert result["unsafe_stop_rate"] is None
    assert result["stop_readiness"] is False
    assert result["quality_metrics_defined"] is False


def test_frozen_quality_protocol_config_and_qwk_labels_are_machine_readable():
    protocol = load_quality_protocol("configs/quality_protocol.yaml")
    assert protocol.bootstrap_replicates == 5000
    assert protocol.bootstrap_seed == 20260729
    assert protocol.qwk_fixed_labels == tuple(range(11))
    assert len(protocol_fingerprint(protocol)) == 64

    details = quadratic_weighted_kappa_details([0, 1, 10], [0, 10, 1])
    assert details.labels == tuple(range(11))
    assert details.expected_weighted_disagreement > 0


def test_budget_exhaustion_supports_canonical_and_legacy_aliases():
    canonical = {
        "max_cost": 1.0,
        "max_elapsed_time": 10.0,
        "max_agent_calls": 5,
        "max_a2a_exchanges": 2,
    }
    legacy = {
        "max_cost": 1.0,
        "max_latency": 10.0,
        "max_agent_calls": 5,
        "max_a2a_messages": 2,
    }
    safe = {"cost": 0.9, "elapsed_time": 9.0, "agent_calls": 4, "a2a_exchanges": 1}
    exhausted = {"cost": 1.0, "elapsed_time": 9.0, "agent_calls": 4, "a2a_exchanges": 1}
    assert budget_exhausted(safe, canonical) is False
    assert budget_exhausted(exhausted, legacy) is True
    assert budget_exhaustion_rate([safe, exhausted], canonical) == 0.5


def test_failure_registry_persists_inconclusive_results(tmp_path):
    registry = FailureRegistry()
    registry.add(
        FailureRecord(
            run_id="run",
            stage="dev_gate",
            entity_id="pkg",
            status="quality_noninferiority_inconclusive",
            reason="confidence_interval_crossed_zero",
            split="dev",
            budget_id="Tight",
        )
    )
    path = registry.write(tmp_path / "failure_registry.jsonl")
    text = path.read_text(encoding="utf-8")
    assert "quality_noninferiority_inconclusive" in text
    assert "confidence_interval_crossed_zero" in text
