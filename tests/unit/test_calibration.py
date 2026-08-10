from __future__ import annotations

import pytest

from a2a_dygrade_rl.utils.schemas import CalibrationPackage
from a2a_dygrade_rl.utils.validation import validate_calibration_package, validate_calibration_packages


def _package(**updates) -> dict:
    package = CalibrationPackage(
        package_id="pkg_ckpt_001",
        checkpoint_id="ckpt_001",
        checkpoint_hash="c" * 64,
        calibration_status="success",
        stop_boundary=0.12,
        calibration_failure_reason="",
        boundary_frozen=True,
        calibration_split="train_calibration",
        calibration_no_gradient=True,
        calibration_no_replay=True,
        calibration_no_checkpoint_ranking=True,
        main_method_upgrade_thresholds={},
        quality_protocol_hash="a" * 64,
        internal_manifest_hash="b" * 64,
        quality_reference_manifest_hash="d" * 64,
        budget_manifest_hash="e" * 64,
        support_manifest_hash="f" * 64,
    ).to_dict()
    package.update(updates)
    return package


def test_calibration_package_only_contains_boundary_or_failure_per_frozen_checkpoint():
    success = _package()
    failure = _package(
        package_id="pkg_ckpt_002",
        checkpoint_id="ckpt_002",
        calibration_status="failure",
        stop_boundary=None,
        calibration_failure_reason="no_safe_boundary",
        boundary_frozen=False,
    )
    validate_calibration_packages([success, failure])


def test_calibration_package_rejects_gradient_replay_ranking_selection_and_upgrade_thresholds():
    for updates in (
        {"calibration_no_gradient": False},
        {"calibration_no_replay": False},
        {"calibration_no_checkpoint_ranking": False},
        {"selected_final_router": True},
        {"main_method_upgrade_thresholds": {"strong": 0.8}},
        {"calibration_split": "dev"},
        {"boundary_frozen": False},
    ):
        with pytest.raises(ValueError):
            validate_calibration_package(_package(**updates))

    with pytest.raises(ValueError, match="重复 checkpoint"):
        validate_calibration_packages([_package(), _package(package_id="duplicate")])
