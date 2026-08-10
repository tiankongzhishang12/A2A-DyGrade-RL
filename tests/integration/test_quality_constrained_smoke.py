from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from a2a_dygrade_rl.rl.fixture_smoke import (
    assert_formal_eligible,
    run_quality_constrained_fixture_smoke,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "fixture_smoke.yaml"


def test_complete_quality_constrained_fixture_smoke_isolated_quality_first_and_reproducible(tmp_path: Path):
    result = run_quality_constrained_fixture_smoke(
        config_path=CONFIG,
        run_id="fixture_smoke_pytest_full",
        output_root=tmp_path / "outputs" / "runs",
    )
    assert result["status"] == "passed"
    assert result["execution_mode"] == "fixture_smoke"
    assert result["formal_eligible"] is False
    assert result["online_agent_calls"] == 0
    assert result["quality_protocol"]["hash"] == "30010205a65ad926b25bc0183309704e4ba94e5c4b0a73eb088d8e956cb801af"
    assert result["quality_protocol"]["qwk_min_valid_completed"] == 100
    assert result["quality_protocol"]["bootstrap_replicates"] == 5000
    assert result["internal_split_audit_passed"] is True
    assert result["internal_split_blocking_error_count"] == 0
    assert result["calibration_gradient_updates"] == 0
    assert result["calibration_replay_writes"] == 0
    assert result["calibration_checkpoint_rankings"] == 0
    assert result["dev_boundary_updates"] == 0
    assert result["quality_champion_resource_reads"] == 0
    assert result["quality_champion_manual_overrides"] == 0
    assert result["test_like_training_reads"] == 0
    assert result["formal_data_reads"] == 0
    assert result["formal_asset_acceptances"] == 0
    assert result["cross_mode_cache_reuse"] == 0

    assert result["quality_champion_package_id"] == "pkg_a_champion"
    assert result["selected_package_id"] == "pkg_b_efficient"
    assert "pkg_c_reference_clone" in result["reference_admission_feasible_ids"]
    assert "pkg_c_reference_clone" not in result["quality_protection_feasible_ids"]
    assert result["reference_clone_mean_cost"] < result["selected_mean_cost"]
    assert "pkg_d_budget_failure" not in result["reference_admission_feasible_ids"]
    with (Path(result["run_dir"]) / "reports" / "checkpoint_selection.csv").open(encoding="utf-8", newline="") as handle:
        selection_rows = list(csv.DictReader(handle))
    budget_failure_row = next(row for row in selection_rows if row["package_id"] == "pkg_d_budget_failure")
    assert "budget_infeasible:Loose" in budget_failure_row["rejection_reason"]
    assert result["deterministic_repeat_match"] is True
    assert result["deterministic_checks"] == {
        "quality_champion": True,
        "quality_protection_set": True,
        "reference_mapping": True,
        "selected_checkpoint": True,
        "stop_boundaries": True,
    }
    assert result["stop_boundary_applied_records"] > 0
    assert result["stop_boundary_escalations"] > 0
    assert result["test_like_one_shot_completed"] is True

    run_dir = Path(result["run_dir"])
    required = [
        "configs/fixture_smoke_run_manifest.json",
        "configs/context_support_catalog.json",
        "configs/agent_cache_manifest.json",
        "configs/fixture_artifact_manifest.json",
        "logs/fixture_smoke.log",
        "reports/internal_split_audit.md",
        "reports/agent_capability_manifest.json",
        "reports/quality_reference_manifest.json",
        "reports/budget_calibration_manifest.json",
        "reports/stop_boundary_calibration.jsonl",
        "reports/calibration_package_manifest.jsonl",
        "reports/policy_package_manifest.jsonl",
        "reports/checkpoint_selection.csv",
        "reports/policy_freeze_manifest.json",
        "reports/test_like_evaluation.json",
        "reports/fixture_smoke_summary.json",
        "reports/fixture_smoke_contract_review.md",
        "reports/fixture_isolation_audit.json",
        "reports/formal_loader_rejection_probes.json",
    ]
    assert all((run_dir / relative).exists() for relative in required)
    manifest = json.loads((run_dir / "configs" / "fixture_smoke_run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["formal_eligible"] is False
    assert "src/a2a_dygrade_rl/rl/fixture_smoke.py" in manifest["core_module_hashes"]
    assert "src/a2a_dygrade_rl/datasets/fixture_factory.py" in manifest["core_module_hashes"]
    assert "src/a2a_dygrade_rl/evaluation/statistical_gate.py" in manifest["core_module_hashes"]
    assert "src/a2a_dygrade_rl/utils/validation.py" in manifest["core_module_hashes"]
    assert len(manifest["entrypoint_hash"]) == 64
    assert len(manifest["source_tree_hash"]) == 64
    with pytest.raises(ValueError, match="Fixture"):
        assert_formal_eligible(manifest)

    probes = json.loads((run_dir / "reports" / "formal_loader_rejection_probes.json").read_text(encoding="utf-8"))
    assert len(probes["probes"]) >= 3
    assert all(probe["accepted"] is False for probe in probes["probes"])

    reference_manifest = json.loads((run_dir / "reports" / "quality_reference_manifest.json").read_text(encoding="utf-8"))
    full_multi_agent = [
        row for row in reference_manifest["candidates"]
        if row["policy_id"] == "Fixed-Full-Multi-Agent"
    ]
    assert full_multi_agent
    assert all(row["a2a_exchanges_per_paper"] > 0 for row in full_multi_agent)
    assert any(row["budget_feasible"] is False for row in full_multi_agent)

    dev_prediction = next((run_dir / "predictions").glob("dev_pkg_b_efficient_*.jsonl"))
    first_prediction = json.loads(dev_prediction.read_text(encoding="utf-8").splitlines()[0])
    assert "predicted_stop_risk" in first_prediction
    assert "stop_boundary" in first_prediction

    inventory_path = run_dir / "configs" / "fixture_artifact_manifest.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert inventory["formal_eligible"] is False
    assert inventory["inventory_self_marked"] is True
    assert inventory["uncovered_artifact_count"] == 0
    assert inventory["covered_artifact_count"] == len(inventory["artifacts"])
    assert all(entry["formal_eligible"] is False for entry in inventory["artifacts"])
    for entry in inventory["artifacts"]:
        artifact_path = run_dir / entry["path"]
        assert artifact_path.stat().st_size == entry["size_bytes"]
        assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == entry["sha256"]
    listed = {entry["path"] for entry in inventory["artifacts"]}
    actual = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file() and path != inventory_path
    }
    assert listed == actual


def test_fixture_smoke_rejects_non_fixture_run_id(tmp_path: Path):
    with pytest.raises(ValueError, match="fixture_smoke_"):
        run_quality_constrained_fixture_smoke(
            config_path=CONFIG,
            run_id="formal_experiment_forbidden",
            output_root=tmp_path / "outputs" / "runs",
        )


def test_fixture_smoke_rejects_path_traversal_run_id(tmp_path: Path):
    with pytest.raises(ValueError, match="single safe path component"):
        run_quality_constrained_fixture_smoke(
            config_path=CONFIG,
            run_id="fixture_smoke_/../../data/processed",
            output_root=tmp_path / "outputs" / "runs",
        )
