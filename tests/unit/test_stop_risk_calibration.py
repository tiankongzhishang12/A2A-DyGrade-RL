from __future__ import annotations

import pytest

from a2a_dygrade_rl.rl.calibration import calibrate_stop_boundary
from a2a_dygrade_rl.router.stop_risk_head import fit_stop_risk_head, predict_stop_risk
from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol


DATASETS = ("asap_sas", "sas_bench", "dress")


def _fit_rows(split: str = "train_fit") -> list[dict]:
    rows = []
    for index in range(60):
        rows.append(
            {
                "split": split,
                "features": {"disagreement": index / 60, "confidence_gap": (60 - index) / 60},
                "gate_error": 0.5 if index >= 50 else 0.0,
            }
        )
    return rows


def _calibration_rows(*, unsafe: bool = False, split: str = "train_calibration") -> list[dict]:
    rows = []
    for dataset in DATASETS:
        for index in range(100):
            rows.append(
                {
                    "split": split,
                    "dataset": dataset,
                    "paper_id": f"{dataset}_p{index}",
                    "item_id": f"{dataset}_i{index}",
                    "predicted_stop_risk": 0.01 + index / 10000,
                    "gate_error": 0.5 if unsafe and index < 10 else 0.0,
                }
            )
    return rows


def test_stop_risk_head_trains_only_on_train_fit_and_is_deterministic():
    first = fit_stop_risk_head(_fit_rows(), feature_names=("disagreement", "confidence_gap"), seed=20260729)
    second = fit_stop_risk_head(_fit_rows(), feature_names=("disagreement", "confidence_gap"), seed=20260729)
    assert first == second
    assert first["training_split"] == "train_fit"
    assert first["target"] == "gate_error_gt_0.25"
    risks = predict_stop_risk(first, [{"features": {"disagreement": 0.2, "confidence_gap": 0.8}}])
    assert len(risks) == 1 and 0.0 <= risks[0] <= 1.0
    with pytest.raises(ValueError, match="train_fit"):
        fit_stop_risk_head(_fit_rows("train_calibration"), feature_names=("disagreement", "confidence_gap"), seed=20260729)


def test_per_checkpoint_stop_boundary_is_automatic_safe_and_non_ranking():
    result = calibrate_stop_boundary(
        checkpoint_id="ckpt_a",
        checkpoint_hash="a" * 64,
        rows=_calibration_rows(),
        protocol=QualityMetricProtocol.formal_v13(),
        risk_limit=0.05,
        confidence_level=0.95,
        min_stops_per_dataset=100,
    )
    assert result["calibration_status"] == "success"
    assert result["stop_boundary"] is not None
    assert result["coverage"] == 1.0
    assert result["calibration_no_gradient"] is True
    assert result["calibration_no_replay"] is True
    assert result["calibration_no_checkpoint_ranking"] is True
    assert not ({"rank", "selected_checkpoint_id", "selected_final_router"} & set(result))

    failure = calibrate_stop_boundary(
        checkpoint_id="ckpt_b",
        checkpoint_hash="b" * 64,
        rows=_calibration_rows(unsafe=True),
        protocol=QualityMetricProtocol.formal_v13(),
        risk_limit=0.05,
        confidence_level=0.95,
        min_stops_per_dataset=100,
    )
    assert failure["calibration_status"] == "failure"
    assert failure["stop_boundary"] is None
    assert failure["failure_reason"] == "no_safe_stop_boundary"

    with pytest.raises(ValueError, match="train_calibration"):
        calibrate_stop_boundary(
            checkpoint_id="ckpt_dev",
            checkpoint_hash="c" * 64,
            rows=_calibration_rows(split="dev"),
            protocol=QualityMetricProtocol.formal_v13(),
            risk_limit=0.05,
            confidence_level=0.95,
            min_stops_per_dataset=100,
        )

def test_stop_risk_training_and_calibration_reject_nonfinite_or_duplicate_safety_evidence():
    invalid_fit = _fit_rows()
    invalid_fit[0]["gate_error"] = float("nan")
    with pytest.raises(ValueError, match="gate_error"):
        fit_stop_risk_head(
            invalid_fit,
            feature_names=("disagreement", "confidence_gap"),
            seed=20260729,
        )

    invalid_calibration = _calibration_rows()
    invalid_calibration[0]["gate_error"] = float("nan")
    with pytest.raises(ValueError, match="gate_error"):
        calibrate_stop_boundary(
            checkpoint_id="ckpt_nan",
            checkpoint_hash="d" * 64,
            rows=invalid_calibration,
            protocol=QualityMetricProtocol.formal_v13(),
            risk_limit=0.05,
            confidence_level=0.95,
            min_stops_per_dataset=100,
        )

    duplicate_calibration = _calibration_rows()
    duplicate_calibration.append(dict(duplicate_calibration[0]))
    with pytest.raises(ValueError, match="Paper/Item/Dataset"):
        calibrate_stop_boundary(
            checkpoint_id="ckpt_duplicate",
            checkpoint_hash="e" * 64,
            rows=duplicate_calibration,
            protocol=QualityMetricProtocol.formal_v13(),
            risk_limit=0.05,
            confidence_level=0.95,
            min_stops_per_dataset=100,
        )

