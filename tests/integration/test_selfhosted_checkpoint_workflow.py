from __future__ import annotations

from pathlib import Path

import pytest

from a2a_dygrade_rl.agents.selfhosted_checkpoint import build_selfhosted_checkpoint_sample
from a2a_dygrade_rl.agents.selfhosted_runtime import run_selfhosted_checkpoint_cache
from a2a_dygrade_rl.agents.selfhosted_validation import validate_selfhosted_checkpoint
from a2a_dygrade_rl.utils.io import read_jsonl, read_yaml, write_yaml


def test_full_selfhosted_fake_checkpoint_and_resume(tmp_path: Path):
    prepare_id = "real_pilot_selfhosted_checkpoint_prepare_integration"
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id=prepare_id,
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_integration"
    first = run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    assert first["generated"] == 15
    assert first["failures"] == 0
    run_dir = tmp_path / "outputs" / "runs" / run_id
    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "PASS"
    assert report["unlocks_30_item_pilot"] is False
    captured_before = len(read_jsonl(run_dir / "logs" / "captured_chat_requests.jsonl"))
    attempts_before = len(read_jsonl(run_dir / "logs" / "call_attempts.jsonl"))

    resumed = run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        resume=True,
        output_root=tmp_path / "outputs" / "runs",
    )
    assert resumed["generated"] == 0
    assert resumed["reused"] == 15
    assert len(read_jsonl(run_dir / "logs" / "captured_chat_requests.jsonl")) == captured_before
    assert len(read_jsonl(run_dir / "logs" / "call_attempts.jsonl")) == attempts_before


def test_real_transport_is_blocked_during_local_preparation(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_blocked",
        output_root=tmp_path / "outputs" / "runs",
    )
    with pytest.raises(PermissionError, match="server_approved"):
        run_selfhosted_checkpoint_cache(
            config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
            items_path=prepared["outputs"]["items_path"],
            internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
            run_id="real_pilot_selfhosted_ministral3_blocked",
            transport_kind="urllib",
            output_root=tmp_path / "outputs" / "runs",
        )

def test_checkpoint_can_run_one_agent_per_server_model_then_merge(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_sequential",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_sequential"
    run_dir = tmp_path / "outputs" / "runs" / run_id
    for index, agent_id in enumerate(("CheapAgent", "MidAgent", "StrongAgent")):
        result = run_selfhosted_checkpoint_cache(
            config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
            items_path=prepared["outputs"]["items_path"],
            internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
            run_id=run_id,
            transport_kind="fake",
            agents=[agent_id],
            resume=index > 0,
            output_root=tmp_path / "outputs" / "runs",
        )
        assert result["generated"] == 5
        assert result["selected_agent_ids"] == [agent_id]

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "PASS"
    assert report["canonical_record_count"] == 15
    assert report["unlocks_30_item_pilot"] is False


def test_real_runtime_rejects_inconsistent_prepared_roots(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_root_mismatch",
        output_root=tmp_path / "outputs" / "runs",
    )
    config = read_yaml("configs/experiments/selfhosted_ministral3_checkpoint.yaml")
    config["local_preparation_only"] = False
    config["prepared_root"] = "data/processed/semantic_v2"
    config["provider"]["prepared_root"] = str(tmp_path / "wrong-prepared-root")
    for row in config["agents"].values():
        if not row.get("disabled"):
            row["model_revision"] = "fixture-frozen-revision"
    config_path = tmp_path / "server-root-mismatch.yaml"
    write_yaml(config_path, config)

    with pytest.raises(ValueError, match="prepared_root"):
        run_selfhosted_checkpoint_cache(
            config_path=config_path,
            items_path=prepared["outputs"]["items_path"],
            internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
            run_id="real_pilot_selfhosted_ministral3_root_mismatch",
            transport_kind="urllib",
            server_approved=True,
            agents=["CheapAgent"],
            output_root=tmp_path / "outputs" / "runs",
        )

def test_real_runtime_bootstrap_reaches_transport_after_server_approval(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_real_bootstrap",
        output_root=tmp_path / "outputs" / "runs",
    )
    config = read_yaml("configs/experiments/selfhosted_ministral3_checkpoint.yaml")
    config["local_preparation_only"] = False
    for row in config["agents"].values():
        if not row.get("disabled"):
            row["model_revision"] = "fixture-frozen-revision"
    config["provider"]["base_url"] = "http://127.0.0.1:1/v1"
    config["provider"]["timeout_seconds"] = 0.05
    config["provider"]["max_attempts"] = 1
    config_path = tmp_path / "server-resolved.yaml"
    write_yaml(config_path, config)
    run_id = "real_pilot_selfhosted_ministral3_bootstrap_probe"

    result = run_selfhosted_checkpoint_cache(
        config_path=config_path,
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="urllib",
        server_approved=True,
        agents=["CheapAgent"],
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    assert result["generated"] == 5
    assert result["failures"] == 5
    assert (run_dir / "configs" / "pilot_sample_manifest.json").is_file()
    runtime = read_yaml(run_dir / "configs" / "selfhosted_runtime.yaml")
    assert runtime["provider"]["transport"] == "urllib"
    assert runtime["local_preparation_only"] is False
    assert runtime["formal_eligible"] is False
    attempts = read_jsonl(run_dir / "logs" / "call_attempts.jsonl")
    assert len(attempts) == 5
    assert all(row["transport_kind"] == "urllib" and row["status"] == "terminal_failure" for row in attempts)


def test_validator_links_canonical_attempt_request_hash(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_attempt_request_hash",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_attempt_request_hash"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    attempts_path = run_dir / "logs" / "call_attempts.jsonl"
    from a2a_dygrade_rl.utils.io import write_jsonl
    attempts = read_jsonl(attempts_path)
    attempts[0]["request_body_sha256"] = "0" * 64
    write_jsonl(attempts_path, attempts, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    attempt_check = next(row for row in report["checks"] if row["name"] == "attempt_audit")
    assert attempt_check["passed"] is False

def test_validator_recomputes_attempt_costs(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_attempt_cost",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_attempt_cost"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    attempts_path = run_dir / "logs" / "call_attempts.jsonl"
    from a2a_dygrade_rl.utils.io import write_jsonl
    attempts = read_jsonl(attempts_path)
    attempts[0]["official_api_equivalent_cost_usd"] += 0.01
    write_jsonl(attempts_path, attempts, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    attempt_check = next(row for row in report["checks"] if row["name"] == "attempt_audit")
    assert attempt_check["passed"] is False

def test_validator_rejects_attempt_with_unknown_logical_call(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_unknown_attempt",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_unknown_attempt"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    attempts_path = run_dir / "logs" / "call_attempts.jsonl"
    from a2a_dygrade_rl.utils.io import write_jsonl
    attempts = read_jsonl(attempts_path)
    extra = dict(attempts[0])
    extra["logical_call_id"] = "e" * 64
    extra["attempt_id"] = "d" * 64
    extra["attempt_number"] = 1
    extra["status"] = "terminal_failure"
    attempts.append(extra)
    write_jsonl(attempts_path, attempts, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    linkage = next(row for row in report["checks"] if row["name"] == "canonical_attempt_linkage")
    assert linkage["passed"] is False

def test_validator_requires_each_agent_to_cover_all_frozen_items(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_agent_coverage",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_agent_coverage"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    cheap_path = run_dir / "predictions" / "agent_cache" / "train_fit" / "CheapAgent.jsonl"
    from a2a_dygrade_rl.utils.io import write_jsonl
    rows = read_jsonl(cheap_path)
    replacement = dict(rows[0])
    replacement["item_id"] = "unknown_item_not_in_checkpoint"
    replacement["cache_key"] = "f" * 64
    replacement["logical_call_id"] = replacement["cache_key"]
    rows[-1] = replacement
    write_jsonl(cheap_path, rows, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    coverage = next(row for row in report["checks"] if row["name"] == "canonical_uniqueness")
    assert coverage["passed"] is False

def test_validator_rejects_checkpoint_items_changed_after_prepare(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_tampered_items",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_tampered_items"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    from a2a_dygrade_rl.utils.io import write_jsonl
    item_rows = read_jsonl(prepared["outputs"]["items_path"])
    item_rows[0]["prompt"] += " tampered"
    write_jsonl(prepared["outputs"]["items_path"], item_rows, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=tmp_path / "outputs" / "runs" / run_id,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    identity = next(row for row in report["checks"] if row["name"] == "checkpoint_input_identity")
    assert identity["passed"] is False

def test_validator_requires_all_three_prompt_snapshots(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_prompt_snapshot",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_prompt_snapshot"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    manifest_path = run_dir / "configs" / "prompts_manifest.json"
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("StrongAgent")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    prompt_check = next(row for row in report["checks"] if row["name"] == "prompt_hash")
    assert prompt_check["passed"] is False

def test_validator_rejects_agent_record_in_wrong_cache_file(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_wrong_agent_file",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_wrong_agent_file"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    cache_path = run_dir / "predictions" / "agent_cache" / "train_fit" / "CheapAgent.jsonl"
    from a2a_dygrade_rl.utils.io import write_jsonl
    rows = read_jsonl(cache_path)
    rows[0]["agent_id"] = "MidAgent"
    write_jsonl(cache_path, rows, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    forbidden = next(row for row in report["checks"] if row["name"] == "forbidden_agents")
    assert forbidden["passed"] is False
    assert "CheapAgent.jsonl:MidAgent" in forbidden["detail"]

def test_validator_rejects_forbidden_agent_cache_file(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_forbidden_cache",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_forbidden_cache"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    cache_dir = run_dir / "predictions" / "agent_cache" / "train_fit"
    evidence_row = dict(read_jsonl(cache_dir / "CheapAgent.jsonl")[0])
    evidence_row["agent_id"] = "EvidenceAgent"
    from a2a_dygrade_rl.utils.io import write_jsonl
    write_jsonl(cache_dir / "EvidenceAgent.jsonl", [evidence_row], overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    forbidden = next(row for row in report["checks"] if row["name"] == "forbidden_agents")
    assert forbidden["passed"] is False
    assert "EvidenceAgent" in forbidden["detail"]

def test_validator_reports_invalid_token_ledger_without_crashing(tmp_path: Path):
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id="real_pilot_selfhosted_checkpoint_prepare_invalid_tokens",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = "fixture_smoke_selfhosted_ministral3_invalid_tokens"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_dir = tmp_path / "outputs" / "runs" / run_id
    cache_path = run_dir / "predictions" / "agent_cache" / "train_fit" / "CheapAgent.jsonl"
    rows = read_jsonl(cache_path)
    rows[0]["token_usage"] += 1
    from a2a_dygrade_rl.utils.io import write_jsonl
    write_jsonl(cache_path, rows, overwrite=True)

    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    token_check = next(row for row in report["checks"] if row["name"] == "token_usage")
    assert token_check["passed"] is False




def _build_fake_run_for_validator_tamper(tmp_path: Path, suffix: str) -> tuple[dict, Path]:
    prepared = build_selfhosted_checkpoint_sample(
        papers_path="data/processed/semantic_v2/papers_train_fit.jsonl",
        items_path="data/processed/semantic_v2/items_train.jsonl",
        internal_manifest_path="data/processed/semantic_v2/internal_item_split_manifest.csv",
        semantic_readiness_manifest_path="data/processed/semantic_v2/semantic_readiness_manifest.json",
        run_id=f"real_pilot_selfhosted_checkpoint_prepare_{suffix}",
        output_root=tmp_path / "outputs" / "runs",
    )
    run_id = f"fixture_smoke_selfhosted_ministral3_{suffix}"
    run_selfhosted_checkpoint_cache(
        config_path="configs/experiments/selfhosted_ministral3_checkpoint.yaml",
        items_path=prepared["outputs"]["items_path"],
        internal_item_manifest_path=prepared["outputs"]["internal_manifest_path"],
        run_id=run_id,
        transport_kind="fake",
        output_root=tmp_path / "outputs" / "runs",
    )
    return prepared, tmp_path / "outputs" / "runs" / run_id


def test_validator_rejects_tampered_captured_request_body(tmp_path: Path):
    prepared, run_dir = _build_fake_run_for_validator_tamper(tmp_path, "captured_tamper")
    captured_path = run_dir / "logs" / "captured_chat_requests.jsonl"
    captured = read_jsonl(captured_path)
    captured[0]["body"]["model"] = "tampered-model"
    from a2a_dygrade_rl.utils.io import write_jsonl

    write_jsonl(captured_path, captured, overwrite=True)
    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    linkage = next(row for row in report["checks"] if row["name"] == "captured_request_linkage")
    assert linkage["passed"] is False


def test_validator_recomputes_attempt_id(tmp_path: Path):
    prepared, run_dir = _build_fake_run_for_validator_tamper(tmp_path, "attempt_id_tamper")
    attempts_path = run_dir / "logs" / "call_attempts.jsonl"
    attempts = read_jsonl(attempts_path)
    attempts[0]["attempt_id"] = "f" * 64
    from a2a_dygrade_rl.utils.io import write_jsonl

    write_jsonl(attempts_path, attempts, overwrite=True)
    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    attempt_check = next(row for row in report["checks"] if row["name"] == "attempt_audit")
    assert attempt_check["passed"] is False
    assert "attempt_id" in attempt_check["detail"]


def test_validator_rejects_run_manifest_identity_mismatch(tmp_path: Path):
    prepared, run_dir = _build_fake_run_for_validator_tamper(tmp_path, "run_identity_tamper")
    manifest_path = run_dir / "configs" / "agent_cache_manifest.json"
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_id"] = "fixture_smoke_other_run"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    run_identity = next(row for row in report["checks"] if row["name"] == "run_identity")
    assert run_identity["passed"] is False
    assert "agent_cache_manifest" in run_identity["detail"]


def test_validator_recomputes_attempt_server_allocation(tmp_path: Path):
    prepared, run_dir = _build_fake_run_for_validator_tamper(tmp_path, "server_cost_tamper")
    attempts_path = run_dir / "logs" / "call_attempts.jsonl"
    attempts = read_jsonl(attempts_path)
    attempts[0]["actual_server_allocated_cost_usd"] = 1.0
    from a2a_dygrade_rl.utils.io import write_jsonl

    write_jsonl(attempts_path, attempts, overwrite=True)
    report = validate_selfhosted_checkpoint(
        run_dir=run_dir,
        items_path=prepared["outputs"]["items_path"],
        transport_kind="fake",
    )
    assert report["status"] == "FAIL"
    attempt_check = next(row for row in report["checks"] if row["name"] == "attempt_audit")
    assert attempt_check["passed"] is False
    assert "server allocation" in attempt_check["detail"]
