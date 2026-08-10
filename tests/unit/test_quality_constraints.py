from __future__ import annotations

import pytest

from a2a_dygrade_rl.evaluation.statistical_gate import evaluate_bootstrap_gate
from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol


def _base(protocol: QualityMetricProtocol, point_deltas: dict, replicate_deltas: dict):
    return evaluate_bootstrap_gate(
        point_deltas=point_deltas,
        replicate_deltas=replicate_deltas,
        protocol=protocol,
        candidate_id="p1",
        comparator_id="ref",
        budget_id="Tight",
        comparison_kind="fixed_reference",
        resample_index_digest="8" * 64,
    )


def test_all_four_zero_margin_quality_constraints_must_pass_together():
    protocol = QualityMetricProtocol.formal_v13(bootstrap_replicates=4, qwk_min_valid_completed=1)
    points = {
        "max_dataset_delta_severe": 0.0,
        "max_dataset_delta_unsafe_stop": 0.0,
        "delta_macro_nmae": 0.0,
        "delta_macro_qwk": 0.0,
    }
    samples = {key: [0.0] * 4 for key in points}
    result = _base(protocol, points, samples)
    assert result.quality_feasible is True
    assert result.status == "quality_noninferiority_pass"
    assert all(
        (
            result.pass_max_dataset_delta_severe,
            result.pass_max_dataset_delta_unsafe_stop,
            result.pass_delta_macro_nmae,
            result.pass_delta_macro_qwk,
        )
    )


def test_one_undefined_metric_fails_gate_but_preserves_other_confidence_bounds():
    protocol = QualityMetricProtocol.formal_v13(bootstrap_replicates=4, qwk_min_valid_completed=1)
    points = {
        "max_dataset_delta_severe": 0.0,
        "max_dataset_delta_unsafe_stop": None,
        "delta_macro_nmae": 0.0,
        "delta_macro_qwk": 0.0,
    }
    samples = {
        "max_dataset_delta_severe": [0.0] * 4,
        "max_dataset_delta_unsafe_stop": [],
        "delta_macro_nmae": [0.0] * 4,
        "delta_macro_qwk": [0.0] * 4,
    }
    result = _base(protocol, points, samples)
    assert result.quality_feasible is False
    assert result.status == "quality_noninferiority_inconclusive"
    assert result.ucb95_max_dataset_delta_unsafe_stop is None
    assert result.ucb95_max_dataset_delta_severe == 0.0
    assert result.ucb95_delta_macro_nmae == 0.0
    assert result.lcb95_delta_macro_qwk == 0.0


def test_bootstrap_gate_rejects_wrong_replicate_count_and_inferior_metric():
    protocol = QualityMetricProtocol.formal_v13(bootstrap_replicates=4, qwk_min_valid_completed=1)
    points = {
        "max_dataset_delta_severe": 0.1,
        "max_dataset_delta_unsafe_stop": 0.0,
        "delta_macro_nmae": 0.0,
        "delta_macro_qwk": 0.0,
    }
    bad_length = {key: [0.0] * 4 for key in points}
    bad_length["delta_macro_nmae"] = [0.0] * 3
    with pytest.raises(ValueError, match="replicate"):
        _base(protocol, points, bad_length)

    samples = {key: [0.0] * 4 for key in points}
    samples["max_dataset_delta_severe"] = [0.1] * 4
    result = _base(protocol, points, samples)
    assert result.quality_feasible is False
    assert result.status == "quality_inferior"
    assert result.pass_max_dataset_delta_severe is False
