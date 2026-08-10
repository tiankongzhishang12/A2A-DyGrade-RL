from __future__ import annotations

import json
from pathlib import Path

import pytest

from a2a_dygrade_rl.rl.policy_package import build_policy_packages
from a2a_dygrade_rl.utils.validation import validate_policy_package


def _checkpoint(checkpoint_id: str) -> dict:
    return {"checkpoint_id": checkpoint_id, "checkpoint_hash": checkpoint_id[-1] * 64, "package_role": "router_candidate"}


def _calibration(checkpoint_id: str, *, success: bool) -> dict:
    return {
        "checkpoint_id": checkpoint_id,
        "checkpoint_hash": checkpoint_id[-1] * 64,
        "calibration_status": "success" if success else "failure",
        "stop_boundary": 0.1 if success else None,
        "coverage": 1.0 if success else 0.0,
        "failure_reason": "" if success else "no_safe_stop_boundary",
        "calibration_no_gradient": True,
        "calibration_no_replay": True,
        "calibration_no_checkpoint_ranking": True,
    }


def test_policy_package_builder_keeps_failures_and_only_promotes_success(tmp_path: Path):
    result = build_policy_packages(
        checkpoints=[_checkpoint("ckpt_a"), _checkpoint("ckpt_b")],
        calibration_results=[_calibration("ckpt_a", success=True), _calibration("ckpt_b", success=False)],
        quality_protocol_hash="1" * 64,
        internal_manifest_hash="2" * 64,
        quality_reference_manifest_hash="3" * 64,
        budget_manifest_hash="4" * 64,
        support_manifest_hash="5" * 64,
        output_dir=tmp_path,
    )
    assert len(result["calibration_packages"]) == 2
    assert len(result["policy_packages"]) == 1
    assert result["policy_packages"][0]["checkpoint_id"] == "ckpt_a"
    prohibited = {"selected_final_router", "selected_checkpoint_id", "dev_rank", "checkpoint_rank", "resource_champion"}
    assert all(not (prohibited & set(row)) for row in result["calibration_packages"])
    assert (tmp_path / "calibration_package_manifest.jsonl").exists()
    assert (tmp_path / "policy_package_manifest.jsonl").exists()
    rows = [json.loads(line) for line in (tmp_path / "calibration_package_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["calibration_status"] for row in rows} == {"success", "failure"}



def test_policy_package_builder_rejects_string_calibration_safety_flags():
    calibration = _calibration("ckpt_a", success=True)
    calibration["calibration_no_gradient"] = "false"
    with pytest.raises(ValueError):
        build_policy_packages(
            checkpoints=[_checkpoint("ckpt_a")],
            calibration_results=[calibration],
            quality_protocol_hash="1" * 64,
            internal_manifest_hash="2" * 64,
            quality_reference_manifest_hash="3" * 64,
            budget_manifest_hash="4" * 64,
            support_manifest_hash="5" * 64,
        )


def test_policy_package_validator_rejects_string_boundary_frozen_flag():
    result = build_policy_packages(
        checkpoints=[_checkpoint("ckpt_a")],
        calibration_results=[_calibration("ckpt_a", success=True)],
        quality_protocol_hash="1" * 64,
        internal_manifest_hash="2" * 64,
        quality_reference_manifest_hash="3" * 64,
        budget_manifest_hash="4" * 64,
        support_manifest_hash="5" * 64,
    )
    package = dict(result["policy_packages"][0])
    package["boundary_frozen"] = "false"
    with pytest.raises(ValueError):
        validate_policy_package(package, expected_protocol_hash="1" * 64)
