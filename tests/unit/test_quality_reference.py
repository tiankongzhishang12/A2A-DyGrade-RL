from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from a2a_dygrade_rl.evaluation.quality_protocol import protocol_fingerprint
from a2a_dygrade_rl.rl.quality_reference import select_quality_references
from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol


BUDGETS = ("Tight", "Medium", "Loose")
DATASETS = ("asap_sas", "sas_bench", "dress")


def _row(policy_id: str, budget_id: str, *, severe: float, nmae: float, qwk: float, cost: float, ready: bool = True) -> dict:
    return {
        "policy_id": policy_id,
        "budget_id": budget_id,
        "split": "train_calibration",
        "dataset_severe": {dataset: severe for dataset in DATASETS},
        "dataset_unsafe_stop": {dataset: severe for dataset in DATASETS},
        "macro_nmae": nmae,
        "macro_qwk": qwk,
        "cost_per_paper": cost,
        "elapsed_time_per_paper": cost * 10,
        "agent_calls_per_paper": 5,
        "a2a_exchanges_per_paper": 0,
        "quality_metrics_defined": ready,
        "stop_readiness": ready,
        "qwk_ready": ready,
        "budget_feasible": True,
    }


def test_reference_selection_is_quality_first_deterministic_and_checkpoint_blind(tmp_path: Path):
    rows = []
    for budget in BUDGETS:
        rows.extend(
            [
                _row("Always-Cheap", budget, severe=0.02, nmae=0.10, qwk=0.80, cost=0.01),
                _row("Always-Mid", budget, severe=0.01, nmae=0.08, qwk=0.85, cost=0.05),
                _row("Always-Strong", budget, severe=0.01, nmae=0.07, qwk=0.90, cost=0.10),
                _row("Fixed-Full-Multi-Agent", budget, severe=0.01, nmae=0.07, qwk=0.90, cost=0.20),
            ]
        )
    before = deepcopy(rows)
    first = select_quality_references(
        rows,
        protocol=QualityMetricProtocol.formal_v13(),
        internal_manifest_hash="a" * 64,
        cache_hash="b" * 64,
        seed=20260729,
        output_path=tmp_path / "quality_reference_manifest.json",
    )
    second = select_quality_references(
        rows,
        protocol=QualityMetricProtocol.formal_v13(),
        internal_manifest_hash="a" * 64,
        cache_hash="b" * 64,
        seed=20260729,
    )
    assert rows == before
    assert first == second
    assert first["budget_to_reference_policy"] == {budget: "Always-Strong" for budget in BUDGETS}
    assert first["budget_failures"] == {}
    assert first["quality_protocol_hash"] == protocol_fingerprint(QualityMetricProtocol.formal_v13())
    assert (tmp_path / "quality_reference_manifest.json").exists()

    bad = deepcopy(rows)
    bad[0]["checkpoint_id"] = "ckpt_forbidden"
    with pytest.raises(ValueError, match="checkpoint"):
        select_quality_references(
            bad,
            protocol=QualityMetricProtocol.formal_v13(),
            internal_manifest_hash="a" * 64,
            cache_hash="b" * 64,
            seed=20260729,
        )


def test_reference_selection_keeps_readiness_failure_without_manual_replacement():
    rows = [_row("Always-Cheap", budget, severe=0.0, nmae=0.0, qwk=1.0, cost=0.01, ready=False) for budget in BUDGETS]
    result = select_quality_references(
        rows,
        protocol=QualityMetricProtocol.formal_v13(),
        internal_manifest_hash="a" * 64,
        cache_hash="b" * 64,
        seed=20260729,
    )
    assert result["budget_to_reference_policy"] == {}
    assert set(result["budget_failures"]) == set(BUDGETS)

def test_reference_selection_requires_explicit_budget_feasibility():
    row = _row("Always-Cheap", "Tight", severe=0.0, nmae=0.0, qwk=1.0, cost=0.01)
    row.pop("budget_feasible")
    with pytest.raises(ValueError, match="budget_feasible"):
        select_quality_references(
            [row],
            protocol=QualityMetricProtocol.formal_v13(),
            internal_manifest_hash="a" * 64,
            cache_hash="b" * 64,
            seed=20260729,
        )




def test_reference_selection_rejects_duplicate_policy_budget_rows():
    rows = [
        _row("Always-Cheap", "Tight", severe=0.01, nmae=0.01, qwk=0.9, cost=0.01),
        _row("Always-Cheap", "Tight", severe=0.00, nmae=0.00, qwk=1.0, cost=0.01),
    ]
    with pytest.raises(ValueError, match="重复"):
        select_quality_references(
            rows,
            protocol=QualityMetricProtocol.formal_v13(),
            internal_manifest_hash="a" * 64,
            cache_hash="b" * 64,
            seed=20260729,
        )


@pytest.mark.parametrize("field", ["quality_metrics_defined", "stop_readiness", "qwk_ready"])
def test_reference_selection_requires_explicit_boolean_readiness(field):
    row = _row("Always-Cheap", "Tight", severe=0.0, nmae=0.0, qwk=1.0, cost=0.01)
    row[field] = "false"
    with pytest.raises(ValueError, match="显式布尔"):
        select_quality_references(
            [row],
            protocol=QualityMetricProtocol.formal_v13(),
            internal_manifest_hash="a" * 64,
            cache_hash="b" * 64,
            seed=20260729,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("macro_nmae", -0.01),
        ("macro_qwk", 1.01),
        ("cost_per_paper", -0.01),
    ],
)
def test_reference_selection_rejects_out_of_range_quality_or_resource_values(field, value):
    row = _row("Always-Cheap", "Tight", severe=0.0, nmae=0.0, qwk=1.0, cost=0.01)
    row[field] = value
    with pytest.raises(ValueError):
        select_quality_references(
            [row],
            protocol=QualityMetricProtocol.formal_v13(),
            internal_manifest_hash="a" * 64,
            cache_hash="b" * 64,
            seed=20260729,
        )
