from __future__ import annotations

from pathlib import Path

import pytest

from a2a_dygrade_rl.rl.fixture_smoke import (
    _collect_pipeline_source_hashes,
    _simulate_policy,
    run_quality_constrained_fixture_smoke,
    validate_fixture_output_root,
    validate_fixture_smoke_paths,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "experiments" / "fixture_smoke.yaml"
BLUEPRINT = ROOT / "tests" / "fixtures" / "quality_constrained_smoke" / "fixture_blueprint.json"
AGENT_CONFIG = ROOT / "configs" / "experiments" / "fixture_smoke_agents.yaml"
PROTOCOL = ROOT / "configs" / "quality_protocol.yaml"
STATIC_ROOT = ROOT / "tests" / "fixtures" / "quality_constrained_smoke"


def test_fixture_smoke_source_paths_are_isolated_from_formal_data():
    result = validate_fixture_smoke_paths(
        project_root=ROOT,
        config_path=CONFIG,
        blueprint_path=BLUEPRINT,
        agent_config_path=AGENT_CONFIG,
        quality_protocol_path=PROTOCOL,
        static_fixture_root=STATIC_ROOT,
    )
    assert result["formal_data_reads"] == 0
    assert result["all_paths_allowed"] is True

    with pytest.raises(ValueError, match="blueprint"):
        validate_fixture_smoke_paths(
            project_root=ROOT,
            config_path=CONFIG,
            blueprint_path=ROOT / "data" / "processed" / "items_train.jsonl",
            agent_config_path=AGENT_CONFIG,
            quality_protocol_path=PROTOCOL,
            static_fixture_root=STATIC_ROOT,
        )

    with pytest.raises(ValueError, match="config"):
        validate_fixture_smoke_paths(
            project_root=ROOT,
            config_path=ROOT / "tests" / "fixtures" / "forbidden_config.yaml",
            blueprint_path=BLUEPRINT,
            agent_config_path=AGENT_CONFIG,
            quality_protocol_path=PROTOCOL,
            static_fixture_root=STATIC_ROOT,
        )


def test_fixture_smoke_output_root_cannot_target_formal_project_directories(tmp_path: Path):
    assert validate_fixture_output_root(ROOT, ROOT / "outputs" / "runs") == (ROOT / "outputs" / "runs").resolve()
    assert validate_fixture_output_root(ROOT, tmp_path / "outputs" / "runs") == (tmp_path / "outputs" / "runs").resolve()
    with pytest.raises(ValueError, match="output_root"):
        validate_fixture_output_root(ROOT, ROOT / "data" / "processed")



def test_fixture_smoke_orchestrator_rejects_config_outside_repository(tmp_path: Path):
    fake_config = tmp_path / "configs" / "experiments" / "fixture_smoke.yaml"
    fake_config.parent.mkdir(parents=True)
    fake_config.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="repository configs/experiments"):
        run_quality_constrained_fixture_smoke(
            config_path=fake_config,
            run_id="fixture_smoke_external_config_forbidden",
            output_root=tmp_path / "outputs" / "runs",
        )


def test_fixture_budget_failure_candidate_exceeds_loose_budget_without_corrupting_quality():
    item = {
        "item_id": "item_1",
        "dataset": "asap_sas",
        "gold_score": 1.0,
        "score_min": 0.0,
        "score_max": 2.0,
    }
    cache = {
        ("item_1", agent_id): {
            "item_id": "item_1",
            "agent_id": agent_id,
            "status": "success",
            "pred_score": 1.0,
            "confidence": 0.9,
            "cost": 0.01,
            "latency": 1.0,
        }
        for agent_id in ("CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent", "ArbitratorAgent")
    }
    budget = {
        "max_cost": 1.0,
        "max_elapsed_time": 100.0,
        "max_agent_calls": 1,
        "max_a2a_exchanges": 4,
    }

    simulation = _simulate_policy(
        papers=[{"paper_id": "paper_1", "items": ["item_1"]}],
        items_by_id={"item_1": item},
        cache=cache,
        policy_kind="dynamic_with_loose_over_budget",
        budget_id="Loose",
        budget=budget,
    )

    assert simulation["records"][0]["status"] == "completed"
    assert simulation["records"][0]["pred_score"] == 1.0
    assert simulation["resources"]["agent_calls_per_paper"] > budget["max_agent_calls"]
    assert simulation["resources"]["budget_feasible"] is False



def test_fixture_run_hashes_all_pipeline_source_files():
    hashes = _collect_pipeline_source_hashes(ROOT)
    required = {
        "src/a2a_dygrade_rl/rl/fixture_smoke.py",
        "src/a2a_dygrade_rl/agents/cache.py",
        "src/a2a_dygrade_rl/evaluation/quality_protocol.py",
        "src/a2a_dygrade_rl/evaluation/statistical_gate.py",
        "src/a2a_dygrade_rl/utils/validation.py",
    }
    assert required <= set(hashes)
    assert hashes
    assert all(len(value) == 64 for value in hashes.values())
