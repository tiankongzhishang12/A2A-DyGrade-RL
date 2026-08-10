from __future__ import annotations

import pytest

from a2a_dygrade_rl.evaluation.qwk_readiness import evaluate_qwk_readiness, score_to_fixed_bin


def test_half_up_score_mapping_uses_all_eleven_fixed_labels():
    assert score_to_fixed_bin(0.049, 0, 1) == 0
    assert score_to_fixed_bin(0.05, 0, 1) == 1
    assert score_to_fixed_bin(0.95, 0, 1) == 10
    assert score_to_fixed_bin(1.0, 0, 1) == 10

    gold_bins = [0, 10] * 50
    pred_bins = [0, 9] * 50
    record = evaluate_qwk_readiness("dress", gold_bins, pred_bins, min_valid_completed=100)
    assert record.fixed_labels == tuple(range(11))
    assert record.valid_completed_n == 100
    assert record.gold_nonempty_bin_count == 2
    assert record.expected_weighted_disagreement > 0
    assert record.qwk_defined is True
    assert record.qwk is not None


def test_qwk_readiness_fails_on_sample_count_gold_bins_or_expected_disagreement():
    too_small = evaluate_qwk_readiness("dress", [0, 10] * 49, [0, 10] * 49, min_valid_completed=100)
    assert too_small.qwk_defined is False
    assert "valid_completed_n" in too_small.readiness_failure_reason

    one_gold_bin = evaluate_qwk_readiness("dress", [5] * 100, [4, 5] * 50, min_valid_completed=100)
    assert one_gold_bin.qwk_defined is False
    assert "gold_nonempty_bin_count" in one_gold_bin.readiness_failure_reason

    zero_expected = evaluate_qwk_readiness("dress", [5] * 100, [5] * 100, min_valid_completed=100)
    assert zero_expected.qwk_defined is False
    assert "expected_weighted_disagreement" in zero_expected.readiness_failure_reason


def test_qwk_mapping_rejects_non_finite_scores():
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="有限数值"):
            score_to_fixed_bin(value, 0, 1)
