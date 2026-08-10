"""隔离的完整质量约束 Fixture Smoke 编排。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.agents.cache import resolve_cache_scope, run_agent_cache
from a2a_dygrade_rl.agents.capability import build_formal_capability_profiles, calibrate_capability_support
from a2a_dygrade_rl.datasets.audit_internal_split import audit_internal_split, write_internal_split_audit
from a2a_dygrade_rl.datasets.build_internal_papers import rebuild_internal_papers
from a2a_dygrade_rl.datasets.fixture_factory import generate_quality_constrained_fixture, load_fixture_blueprint
from a2a_dygrade_rl.datasets.internal_split import allocate_internal_item_splits
from a2a_dygrade_rl.evaluation.metrics_safety import normalized_gate_error
from a2a_dygrade_rl.evaluation.paired_bootstrap import paired_cluster_bootstrap
from a2a_dygrade_rl.evaluation.quality_protocol import evaluate_quality, load_quality_protocol, protocol_fingerprint
from a2a_dygrade_rl.rl.budget_calibration import calibrate_budget_tiers
from a2a_dygrade_rl.rl.calibration import calibrate_stop_boundary
from a2a_dygrade_rl.rl.checkpoint_selector import determine_quality_champion_after_reference_admission, select_policy_package
from a2a_dygrade_rl.rl.policy_package import build_policy_packages
from a2a_dygrade_rl.rl.quality_reference import REFERENCE_POLICY_IDS, select_quality_references
from a2a_dygrade_rl.router.stop_risk_head import fit_stop_risk_head, predict_stop_risk
from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_yaml, write_csv, write_json, write_jsonl
from a2a_dygrade_rl.utils.schemas import InternalItemSplitManifest, InternalPaperManifest, LeftoverRecord


CORE_PIPELINE_MODULES = (
    "a2a_dygrade_rl.datasets.fixture_factory.generate_quality_constrained_fixture",
    "a2a_dygrade_rl.datasets.internal_split.allocate_internal_item_splits",
    "a2a_dygrade_rl.datasets.build_internal_papers.rebuild_internal_papers",
    "a2a_dygrade_rl.agents.cache.run_agent_cache",
    "a2a_dygrade_rl.agents.capability.build_formal_capability_profiles",
    "a2a_dygrade_rl.rl.quality_reference.select_quality_references",
    "a2a_dygrade_rl.rl.budget_calibration.calibrate_budget_tiers",
    "a2a_dygrade_rl.router.stop_risk_head.fit_stop_risk_head",
    "a2a_dygrade_rl.rl.calibration.calibrate_stop_boundary",
    "a2a_dygrade_rl.rl.policy_package.build_policy_packages",
    "a2a_dygrade_rl.evaluation.paired_bootstrap.paired_cluster_bootstrap",
    "a2a_dygrade_rl.rl.checkpoint_selector.select_policy_package",
    "a2a_dygrade_rl.rl.fixture_smoke.run_quality_constrained_fixture_smoke",
)
CORE_PIPELINE_FILES = (
    "src/a2a_dygrade_rl/datasets/fixture_factory.py",
    "src/a2a_dygrade_rl/datasets/internal_split.py",
    "src/a2a_dygrade_rl/datasets/build_internal_papers.py",
    "src/a2a_dygrade_rl/agents/cache.py",
    "src/a2a_dygrade_rl/agents/capability.py",
    "src/a2a_dygrade_rl/rl/quality_reference.py",
    "src/a2a_dygrade_rl/rl/budget_calibration.py",
    "src/a2a_dygrade_rl/router/stop_risk_head.py",
    "src/a2a_dygrade_rl/rl/calibration.py",
    "src/a2a_dygrade_rl/rl/policy_package.py",
    "src/a2a_dygrade_rl/evaluation/paired_bootstrap.py",
    "src/a2a_dygrade_rl/rl/checkpoint_selector.py",
    "src/a2a_dygrade_rl/rl/fixture_smoke.py",
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


AUDIT_COUNTER_KEYS = (
    "formal_data_reads",
    "formal_asset_acceptances",
    "cross_mode_cache_reuse",
    "online_agent_calls",
    "calibration_gradient_updates",
    "calibration_replay_writes",
    "calibration_checkpoint_rankings",
    "dev_boundary_updates",
    "quality_champion_resource_reads",
    "quality_champion_manual_overrides",
    "test_like_training_reads",
)


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _collect_pipeline_source_hashes(project_root: str | Path) -> dict[str, str]:
    root = Path(project_root).resolve()
    source_root = root / "src" / "a2a_dygrade_rl"
    paths = sorted(path for path in source_root.rglob("*.py") if path.is_file())
    if not paths:
        raise ValueError("Fixture Smoke pipeline source tree is empty")
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in paths
    }
    missing_declared = sorted(set(CORE_PIPELINE_FILES) - set(hashes))
    if missing_declared:
        raise ValueError(f"Fixture Smoke declared core source files are missing: {missing_declared}")
    return hashes


def _resolve(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else root / candidate).resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def validate_fixture_output_root(project_root: str | Path, output_root: str | Path) -> Path:
    root = Path(project_root).resolve()
    resolved_output = Path(output_root).resolve()
    if _is_within(resolved_output, root) and not _is_within(resolved_output, root / "outputs" / "runs"):
        raise ValueError("Fixture Smoke output_root inside the project must stay under outputs/runs")
    return resolved_output


def validate_fixture_smoke_paths(
    *,
    project_root: str | Path,
    config_path: str | Path,
    blueprint_path: str | Path,
    agent_config_path: str | Path,
    quality_protocol_path: str | Path,
    static_fixture_root: str | Path,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    resolved = {
        "config": Path(config_path).resolve(),
        "blueprint": Path(blueprint_path).resolve(),
        "agent_config": Path(agent_config_path).resolve(),
        "quality_protocol": Path(quality_protocol_path).resolve(),
        "static_fixture_root": Path(static_fixture_root).resolve(),
    }
    allowed_roots = {
        "config": root / "configs" / "experiments",
        "blueprint": resolved["static_fixture_root"],
        "agent_config": root / "configs" / "experiments",
        "quality_protocol": root / "configs",
        "static_fixture_root": root / "tests" / "fixtures",
    }
    violations = [
        name
        for name, path in resolved.items()
        if not _is_within(path, allowed_roots[name])
    ]
    formal_data_root = (root / "data").resolve()
    formal_data_reads = sum(_is_within(path, formal_data_root) for path in resolved.values())
    if violations or formal_data_reads:
        details = ", ".join(sorted(set(violations))) or "formal_data"
        raise ValueError(f"Fixture Smoke source path isolation failed: {details}")
    return {
        "all_paths_allowed": True,
        "formal_data_reads": 0,
        "paths": {name: str(path) for name, path in sorted(resolved.items())},
        "allowed_roots": {name: str(path.resolve()) for name, path in sorted(allowed_roots.items())},
    }


def _expect_formal_rejection(name: str, operation: Any) -> dict[str, Any]:
    try:
        operation()
    except ValueError as exc:
        message = str(exc)
        if "Fixture" not in message and "formal_eligible" not in message:
            raise RuntimeError(f"Formal rejection probe failed for an unrelated reason: {name}: {message}") from exc
        return {"name": name, "accepted": False, "rejection": message}
    return {"name": name, "accepted": True, "rejection": ""}


def _build_fixture_artifact_manifest(run_dir: Path) -> dict[str, Any]:
    inventory_path = run_dir / "configs" / "fixture_artifact_manifest.json"
    artifacts = []
    for path in sorted(candidate for candidate in run_dir.rglob("*") if candidate.is_file() and candidate != inventory_path):
        artifacts.append({
            "path": path.relative_to(run_dir).as_posix(),
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
            "execution_mode": "fixture_smoke",
            "is_fixture": True,
            "formal_eligible": False,
        })
    return {
        "manifest_version": "fixture_artifact_manifest_v1",
        "execution_mode": "fixture_smoke",
        "is_fixture": True,
        "formal_eligible": False,
        "covered_artifact_count": len(artifacts),
        "uncovered_artifact_count": 0,
        "inventory_self_marked": True,
        "artifacts": artifacts,
    }


def assert_formal_eligible(manifest: dict[str, Any]) -> None:
    if manifest.get("is_fixture") is True or manifest.get("execution_mode") == "fixture_smoke" or manifest.get("formal_eligible") is not True:
        raise ValueError("Fixture 或 formal_eligible=false 资产不得进入 Formal 流水线")


def _annotate_internal_items(items: list[dict[str, Any]], manifest_rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    selected = {str(row["item_id"]) for row in manifest_rows if row["internal_split"] == split}
    output = []
    for item in items:
        if str(item["item_id"]) in selected:
            copied = dict(item)
            copied["metadata"] = {**item.get("metadata", {}), "split": split, "internal_split": split}
            output.append(copied)
    return output


def _difficulty_rows(items: Iterable[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    labels = {"asap_sas": "Easy", "sas_bench": "Medium", "dress": "Hard"}
    return [{"item_id": str(item["item_id"]), "difficulty_label": labels[str(item["dataset"])], "source_split": split} for item in items]


def _cache_index(records: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index = {}
    for record in records:
        key = (str(record["item_id"]), str(record["agent_id"]))
        if key in index:
            raise ValueError(f"Fixture cache 出现重复 Item/Agent: {key}")
        if record.get("status") != "success":
            raise ValueError(f"Fixture cache active record 失败: {key}")
        index[key] = dict(record)
    return index


def _within_budget(resources: dict[str, float], budget: dict[str, Any]) -> bool:
    return (
        resources["cost"] <= float(budget["max_cost"]) + 1e-12
        and resources["elapsed_time"] <= float(budget["max_elapsed_time"]) + 1e-12
        and resources["agent_calls"] <= int(budget["max_agent_calls"])
        and resources["a2a_exchanges"] <= int(budget["max_a2a_exchanges"])
    )


def _fixed_agent_for_policy(policy_id: str) -> str:
    mapping = {
        "Always-Cheap": "CheapAgent",
        "Always-Mid": "MidAgent",
        "Always-Strong": "StrongAgent",
        "Fixed-Full-Multi-Agent": "ArbitratorAgent",
    }
    if policy_id not in mapping:
        raise ValueError(f"未知 fixed policy: {policy_id}")
    return mapping[policy_id]


def _simulate_policy(
    *,
    papers: list[dict[str, Any]],
    items_by_id: dict[str, dict[str, Any]],
    cache: dict[tuple[str, str], dict[str, Any]],
    policy_kind: str,
    budget_id: str,
    budget: dict[str, Any],
    reference_policy_id: str | None = None,
    stop_risk_model: dict[str, Any] | None = None,
    stop_boundary: float | None = None,
) -> dict[str, Any]:
    records = []
    paper_resources = []
    for paper in papers:
        paper_id = str(paper["paper_id"])
        resource = {
            "cost": 0.0,
            "elapsed_time": 0.0,
            "agent_calls": 0,
            "a2a_exchanges": 0,
            "stop_boundary_applied_records": 0,
            "stop_boundary_escalations": 0,
        }
        paper_records = []
        risk_escalated_item_ids: set[str] = set()
        for item_id in paper["items"]:
            item = items_by_id[str(item_id)]
            dataset = str(item["dataset"])
            if policy_kind in REFERENCE_POLICY_IDS:
                final_agent = _fixed_agent_for_policy(policy_kind)
            elif policy_kind == "reference_clone":
                if reference_policy_id is None:
                    raise ValueError("reference_clone 缺少冻结 reference policy")
                final_agent = _fixed_agent_for_policy(reference_policy_id)
            else:
                final_agent = "CheapAgent" if dataset == "asap_sas" else "StrongAgent"

            predicted_stop_risk: float | None = None
            early_stop_allowed: bool | None = None
            if stop_risk_model is not None or stop_boundary is not None:
                if stop_risk_model is None or stop_boundary is None:
                    raise ValueError("stop_risk_model and stop_boundary must be provided together")
                predicted_stop_risk = predict_stop_risk(
                    stop_risk_model,
                    [{"features": _features_for_item(item, cache)}],
                )[0]
                early_stop_allowed = predicted_stop_risk <= float(stop_boundary)
                resource["stop_boundary_applied_records"] += 1
                if not early_stop_allowed:
                    verification = cache[(str(item_id), "EvidenceAgent")]
                    resource["cost"] += float(verification["cost"])
                    resource["elapsed_time"] += float(verification["latency"])
                    resource["agent_calls"] += 1
                    resource["stop_boundary_escalations"] += 1
                    risk_escalated_item_ids.add(str(item_id))

            if final_agent == "ArbitratorAgent":
                context_agent_ids = ("CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent")
                for agent_id in (*context_agent_ids, "ArbitratorAgent"):
                    call = cache[(str(item_id), agent_id)]
                    resource["cost"] += float(call["cost"])
                    resource["elapsed_time"] += float(call["latency"])
                    resource["agent_calls"] += 1
                resource["a2a_exchanges"] += len(context_agent_ids)
            else:
                call = cache[(str(item_id), final_agent)]
                resource["cost"] += float(call["cost"])
                resource["elapsed_time"] += float(call["latency"])
                resource["agent_calls"] += 1

            final_record = cache[(str(item_id), final_agent)]
            force_failure = policy_kind == "dynamic_with_loose_failure" and budget_id == "Loose" and dataset == "dress"
            record = {
                "paper_id": paper_id,
                "item_id": str(item_id),
                "dataset": dataset,
                "gold_score": float(item["gold_score"]),
                "pred_score": None if force_failure else float(final_record["pred_score"]),
                "score_min": float(item["score_min"]),
                "score_max": float(item["score_max"]),
                "status": "budget_exhausted" if force_failure else "completed",
                "completed": not force_failure,
                "deferred": force_failure,
                "terminal_action": "DEFER" if force_failure else "STOP",
                "active_cache_valid": not force_failure,
                "final_agent": final_agent,
                "budget_id": budget_id,
            }
            if predicted_stop_risk is not None:
                record.update({
                    "predicted_stop_risk": predicted_stop_risk,
                    "stop_boundary": float(stop_boundary),
                    "early_stop_allowed": bool(early_stop_allowed),
                    "stop_risk_action": "STOP" if early_stop_allowed else "VERIFY_THEN_STOP",
                })
            paper_records.append(record)

        if policy_kind == "dynamic_with_redundant_evidence" and not risk_escalated_item_ids:
            extra = cache[(str(paper["items"][0]), "EvidenceAgent")]
            resource["cost"] += float(extra["cost"])
            resource["elapsed_time"] += float(extra["latency"])
            resource["agent_calls"] += 1
        if policy_kind == "dynamic_with_loose_over_budget" and budget_id == "Loose":
            extra = cache[(str(paper["items"][0]), "EvidenceAgent")]
            extra_calls = max(1, int(budget["max_agent_calls"]) - int(resource["agent_calls"]) + 1)
            resource["cost"] += float(extra["cost"]) * extra_calls
            resource["elapsed_time"] += float(extra["latency"]) * extra_calls
            resource["agent_calls"] += extra_calls
            resource["budget_counterexample_extra_calls"] = extra_calls
        resource["paper_id"] = paper_id
        resource["budget_feasible"] = _within_budget(resource, budget)
        paper_resources.append(resource)
        records.extend(paper_records)

    count = max(1, len(paper_resources))
    resources = {
        "cost_per_paper": sum(float(row["cost"]) for row in paper_resources) / count,
        "elapsed_time_per_paper": sum(float(row["elapsed_time"]) for row in paper_resources) / count,
        "agent_calls_per_paper": sum(float(row["agent_calls"]) for row in paper_resources) / count,
        "a2a_exchanges_per_paper": sum(float(row["a2a_exchanges"]) for row in paper_resources) / count,
        "stop_boundary_applied_records": sum(int(row["stop_boundary_applied_records"]) for row in paper_resources),
        "stop_boundary_escalations": sum(int(row["stop_boundary_escalations"]) for row in paper_resources),
        "budget_feasible": all(bool(row["budget_feasible"]) for row in paper_resources),
    }
    return {"records": records, "paper_resources": paper_resources, "resources": resources}


def _evaluation_row(identifier: str, budget_id: str, simulation: dict[str, Any], protocol: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    quality = evaluate_quality(simulation["records"], protocol=protocol)
    row = {
        "package_id": identifier,
        "budget_id": budget_id,
        "dataset_severe": {dataset: quality["datasets"][dataset]["severe_rate"] for dataset in protocol.datasets},
        "dataset_unsafe_stop": {dataset: quality["datasets"][dataset]["unsafe_stop_rate"] for dataset in protocol.datasets},
        "macro_nmae": quality["macro_nmae"],
        "macro_qwk": quality["macro_qwk"],
        "cost_per_paper": simulation["resources"]["cost_per_paper"],
        "elapsed_time_per_paper": simulation["resources"]["elapsed_time_per_paper"],
        "agent_calls_per_paper": simulation["resources"]["agent_calls_per_paper"],
        "a2a_exchanges_per_paper": simulation["resources"]["a2a_exchanges_per_paper"],
        "quality_metrics_defined": bool(quality["quality_metrics_defined"]),
        "stop_readiness": bool(quality["stop_readiness"]),
        "qwk_ready": bool(quality["qwk_ready"]),
        "budget_feasible": bool(simulation["resources"]["budget_feasible"]),
    }
    return row, quality


def _reference_candidate_row(policy_id: str, budget_id: str, simulation: dict[str, Any], protocol: Any) -> dict[str, Any]:
    row, _ = _evaluation_row(policy_id, budget_id, simulation, protocol)
    row["policy_id"] = policy_id
    row["split"] = "train_calibration"
    row.pop("package_id")
    return row


def _features_for_item(item: dict[str, Any], cache: dict[tuple[str, str], dict[str, Any]]) -> dict[str, float]:
    cheap = cache[(str(item["item_id"]), "CheapAgent")]
    strong = cache[(str(item["item_id"]), "StrongAgent")]
    span = float(item["score_max"]) - float(item["score_min"])
    return {
        "disagreement": abs(float(cheap["pred_score"]) - float(strong["pred_score"])) / span,
        "confidence_gap": abs(float(cheap["confidence"]) - float(strong["confidence"])),
    }


def _build_budget_observations(papers: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    section = config["budget_calibration"]
    rows = []
    for policy_id in section["fixed_behavior_policy_ids"]:
        envelope = section["fixture_behavior_envelopes"][policy_id]
        for paper in papers:
            rows.append({
                "paper_id": str(paper["paper_id"]),
                "policy_id": str(policy_id),
                "split": "train_calibration",
                "cost": float(envelope["cost"]),
                "elapsed_time": float(envelope["elapsed_time"]),
                "agent_calls": int(envelope["agent_calls"]),
                "a2a_exchanges": int(envelope["a2a_exchanges"]),
            })
    return rows


def _mean_cost(evaluations: list[dict[str, Any]], package_id: str, budget_ids: Iterable[str]) -> float:
    wanted = set(budget_ids)
    rows = [row for row in evaluations if row["package_id"] == package_id and row["budget_id"] in wanted]
    return sum(float(row["cost_per_paper"]) for row in rows) / len(rows)

def run_quality_constrained_fixture_smoke(
    *,
    config_path: str | Path,
    run_id: str,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Any]:
    config_path = Path(config_path).resolve()
    project_root = REPOSITORY_ROOT
    if not _is_within(config_path, project_root / "configs" / "experiments"):
        raise ValueError("Fixture Smoke config_path must stay under repository configs/experiments")
    config = read_yaml(config_path)
    run_config = config.get("run", {})
    prefix = str(config.get("isolation", {}).get("run_id_prefix", "fixture_smoke_"))
    if not str(run_id).startswith(prefix):
        raise ValueError(f"run_id 必须以 {prefix} 开头")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(run_id)) is None:
        raise ValueError("Fixture Smoke run_id must be a single safe path component")
    if run_config.get("execution_mode") != "fixture_smoke" or run_config.get("formal_eligible") is not False or run_config.get("online_agent_calls") is not False:
        raise ValueError("Fixture Smoke 配置必须固定 fixture_smoke/formal_eligible=false/online_agent_calls=false")
    output_root = validate_fixture_output_root(project_root, output_root)
    run_dir = (output_root / run_id).resolve()
    if not _is_within(run_dir, output_root):
        raise ValueError("Fixture Smoke run directory escaped output_root")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Fixture Smoke run 已存在且非空: {run_dir}")

    blueprint_path = _resolve(project_root, config["paths"]["blueprint"])
    agent_config_path = _resolve(project_root, config["paths"]["agent_config"])
    quality_protocol_path = _resolve(project_root, config["paths"]["quality_protocol"])
    static_fixture_root = _resolve(project_root, config["isolation"]["static_fixture_root"])
    isolation_audit = validate_fixture_smoke_paths(
        project_root=project_root,
        config_path=config_path,
        blueprint_path=blueprint_path,
        agent_config_path=agent_config_path,
        quality_protocol_path=quality_protocol_path,
        static_fixture_root=static_fixture_root,
    )
    blueprint = load_fixture_blueprint(blueprint_path)
    protocol = load_quality_protocol(quality_protocol_path)
    for relative in ("configs", "logs", "predictions/fixture_inputs", "checkpoints/fixture_candidates", "reports"):
        ensure_dir(run_dir / relative)
    seed = int(run_config["seed"])
    counters = {key: 0 for key in AUDIT_COUNTER_KEYS}
    counters["formal_data_reads"] = int(isolation_audit["formal_data_reads"])
    manifest_path = run_dir / "configs" / "fixture_smoke_run_manifest.json"
    run_manifest = {
        "manifest_version": "fixture_smoke_run_manifest_v1",
        "run_id": run_id,
        "execution_mode": "fixture_smoke",
        "is_fixture": True,
        "formal_eligible": False,
        "online_agent_calls": 0,
        "seed": seed,
        "fixture_blueprint_hash": file_sha256(blueprint_path),
        "fixture_config_hash": file_sha256(config_path),
        "fixture_agent_config_hash": file_sha256(agent_config_path),
        "quality_protocol_file_hash": file_sha256(quality_protocol_path),
        "quality_protocol_hash": protocol_fingerprint(protocol),
        "entrypoint_hash": file_sha256(project_root / "scripts" / "04d_run_quality_constrained_fixture_smoke.py"),
        "core_pipeline_modules": list(CORE_PIPELINE_MODULES),
        "core_module_hashes": _collect_pipeline_source_hashes(project_root),
        "audit_counters": counters,
    }
    run_manifest["source_tree_hash"] = _stable_hash(run_manifest["core_module_hashes"])
    write_json(manifest_path, run_manifest, overwrite=True)
    write_json(run_dir / "configs" / "fixture_smoke.resolved.json", config, overwrite=True)
    write_json(run_dir / "configs" / "fixture_blueprint.resolved.json", blueprint, overwrite=True)
    write_json(run_dir / "configs" / "quality_protocol.resolved.json", protocol.to_dict(), overwrite=True)
    write_json(
        run_dir / "reports" / "fixture_isolation_audit.json",
        {**isolation_audit, "execution_mode": "fixture_smoke", "formal_eligible": False},
        overwrite=True,
    )

    fixture = generate_quality_constrained_fixture(blueprint=blueprint, agent_config_path=agent_config_path)
    inputs_dir = run_dir / "predictions" / "fixture_inputs"
    items_train_path = write_jsonl(inputs_dir / "items_train.jsonl", fixture["items_by_split"]["train"], overwrite=True)
    items_dev_path = write_jsonl(inputs_dir / "items_dev.jsonl", fixture["items_by_split"]["dev"], overwrite=True)
    items_test_path = write_jsonl(inputs_dir / "items_test.jsonl", fixture["items_by_split"]["test"], overwrite=True)
    dev_manifest_path = write_csv(
        inputs_dir / "external_split_manifest.dev.csv",
        fixture["external_manifests"]["dev"],
        ["item_id", "split", "dataset", "prompt_group", "paper_id", "formal_eligible"],
        overwrite=True,
    )
    test_manifest_path = write_csv(
        inputs_dir / "external_split_manifest.test.csv",
        fixture["external_manifests"]["test"],
        ["item_id", "split", "dataset", "prompt_group", "paper_id", "formal_eligible"],
        overwrite=True,
    )
    write_jsonl(inputs_dir / "papers_dev.jsonl", fixture["papers_by_split"]["dev"], overwrite=True)
    write_jsonl(inputs_dir / "papers_test.jsonl", fixture["papers_by_split"]["test"], overwrite=True)
    write_json(run_dir / "reports" / "fixture_data_summary.json", fixture["summary"], overwrite=True)

    strict_quotas = config["paper"]["strict_quotas"]
    split_result = allocate_internal_item_splits(
        fixture["items_by_split"]["train"],
        train_fit_ratio=float(config["internal_split"]["train_fit_ratio"]),
        seed=int(config["internal_split"]["seed"]),
        rule_version=str(config["internal_split"]["rule_version"]),
        strict_quotas=strict_quotas,
        assignment_unit=str(config["internal_split"]["assignment_unit"]),
        source_paper_ids_by_item=fixture["source_paper_ids_by_item"],
    )
    internal_manifest_path = write_csv(
        inputs_dir / "internal_item_split_manifest.csv",
        split_result.manifest_rows,
        list(InternalItemSplitManifest.__dataclass_fields__),
        overwrite=True,
    )
    paper_result = rebuild_internal_papers(
        fixture["items_by_split"]["train"],
        split_result.manifest_rows,
        strict_quotas=strict_quotas,
        budget=config["paper"]["budget_placeholder"],
        seed=seed,
        rule_version="fixture_internal_strict_paper_v1",
    )
    papers_train_fit_path = write_jsonl(inputs_dir / "papers_train_fit.jsonl", paper_result.papers_by_split["train_fit"], overwrite=True)
    papers_train_calibration_path = write_jsonl(inputs_dir / "papers_train_calibration.jsonl", paper_result.papers_by_split["train_calibration"], overwrite=True)
    paper_manifest_path = write_csv(inputs_dir / "internal_paper_manifest.csv", paper_result.paper_manifest_rows, list(InternalPaperManifest.__dataclass_fields__), overwrite=True)
    leftover_path = write_csv(inputs_dir / "leftover_items.csv", paper_result.leftover_rows, list(LeftoverRecord.__dataclass_fields__), overwrite=True)
    audit = audit_internal_split(
        items=fixture["items_by_split"]["train"],
        item_manifest_rows=split_result.manifest_rows,
        papers_by_split=paper_result.papers_by_split,
        paper_manifest_rows=paper_result.paper_manifest_rows,
        leftover_rows=paper_result.leftover_rows,
        strict_quotas=strict_quotas,
    )
    audit.summary["audited_artifact_hashes"] = {
        "items_train_sha256": file_sha256(items_train_path),
        "internal_item_split_manifest_sha256": file_sha256(internal_manifest_path),
        "papers_train_fit_sha256": file_sha256(papers_train_fit_path),
        "papers_train_calibration_sha256": file_sha256(papers_train_calibration_path),
        "internal_paper_manifest_sha256": file_sha256(paper_manifest_path),
        "leftover_items_sha256": file_sha256(leftover_path),
    }
    write_internal_split_audit(audit, run_id=run_id, output_root=output_root, overwrite=True)
    if not audit.passed:
        raise RuntimeError(f"Fixture internal split audit 失败: {audit.errors}")

    cache_results = {}
    for split in ("train_fit", "train_calibration"):
        cache_results[split] = run_agent_cache(
            config_path=agent_config_path,
            items_path=items_train_path,
            split=split,
            run_id=run_id,
            execution_mode="fixture_smoke",
            seed=seed,
            output_root=output_root,
            internal_item_manifest_path=internal_manifest_path,
        )
    cache_results["dev"] = run_agent_cache(
        config_path=agent_config_path,
        items_path=items_dev_path,
        split="dev",
        run_id=run_id,
        execution_mode="fixture_smoke",
        seed=seed,
        output_root=output_root,
        external_split_manifest_path=dev_manifest_path,
    )
    train_fit_cache = _cache_index(cache_results["train_fit"]["records"])
    calibration_cache = _cache_index(cache_results["train_calibration"]["records"])
    dev_cache = _cache_index(cache_results["dev"]["records"])
    pretest_cache_hash = _stable_hash({
        "train_fit": cache_results["train_fit"]["records"],
        "train_calibration": cache_results["train_calibration"]["records"],
        "dev": cache_results["dev"]["records"],
    })

    train_fit_items = _annotate_internal_items(fixture["items_by_split"]["train"], split_result.manifest_rows, "train_fit")
    calibration_items = _annotate_internal_items(fixture["items_by_split"]["train"], split_result.manifest_rows, "train_calibration")
    train_fit_difficulty = _difficulty_rows(train_fit_items, "train_fit")
    calibration_difficulty = _difficulty_rows(calibration_items, "train_calibration")
    formal_rejection_probes = [
        _expect_formal_rejection("run_manifest", lambda: assert_formal_eligible(run_manifest)),
        _expect_formal_rejection(
            "cache_scope",
            lambda: resolve_cache_scope(
                fixture["items_by_split"]["train"],
                split="train_fit",
                execution_mode="formal_experiment",
                internal_item_manifest_path=internal_manifest_path,
            ),
        ),
        _expect_formal_rejection(
            "capability_profile",
            lambda: build_formal_capability_profiles(
                train_fit_items,
                cache_results["train_fit"]["records"],
                train_fit_difficulty,
            ),
        ),
    ]
    counters["formal_asset_acceptances"] = sum(bool(probe["accepted"]) for probe in formal_rejection_probes)
    write_json(
        run_dir / "reports" / "formal_loader_rejection_probes.json",
        {
            "execution_mode": "fixture_smoke",
            "formal_eligible": False,
            "accepted_count": counters["formal_asset_acceptances"],
            "probes": formal_rejection_probes,
        },
        overwrite=True,
    )
    fit_profiles = build_formal_capability_profiles(
        train_fit_items,
        cache_results["train_fit"]["records"],
        train_fit_difficulty,
        low_support_threshold=30,
        allow_fixture=True,
    )
    write_jsonl(run_dir / "reports" / "agent_capability_profiles.jsonl", fit_profiles, overwrite=True)
    support_manifest_path = run_dir / "reports" / "agent_capability_manifest.json"
    support_manifest = calibrate_capability_support(
        fit_profiles,
        calibration_items,
        cache_results["train_calibration"]["records"],
        calibration_difficulty,
        support_quantile=float(config["capability_support"]["support_quantile"]),
        internal_manifest_hash=file_sha256(internal_manifest_path),
        cache_hash=pretest_cache_hash,
        seed=seed,
        output_path=support_manifest_path,
        allow_fixture=True,
    )

    budget_manifest_path = run_dir / "reports" / "budget_calibration_manifest.json"
    budget_manifest = calibrate_budget_tiers(
        _build_budget_observations(paper_result.papers_by_split["train_calibration"], config),
        quantiles={key: float(value) for key, value in config["budget_calibration"]["quantiles"].items()},
        internal_manifest_hash=file_sha256(internal_manifest_path),
        cache_hash=pretest_cache_hash,
        config=config["budget_calibration"],
        seed=seed,
        output_path=budget_manifest_path,
    )
    budgets = budget_manifest["budgets"]

    train_items_by_id = {str(item["item_id"]): item for item in fixture["items_by_split"]["train"]}
    reference_candidates = []
    for budget_id in protocol.budget_ids:
        for policy_id in REFERENCE_POLICY_IDS:
            simulation = _simulate_policy(
                papers=paper_result.papers_by_split["train_calibration"],
                items_by_id=train_items_by_id,
                cache=calibration_cache,
                policy_kind=policy_id,
                budget_id=budget_id,
                budget=budgets[budget_id],
            )
            reference_candidates.append(_reference_candidate_row(policy_id, budget_id, simulation, protocol))
    reference_manifest_path = run_dir / "reports" / "quality_reference_manifest.json"
    reference_manifest = select_quality_references(
        reference_candidates,
        protocol=protocol,
        internal_manifest_hash=file_sha256(internal_manifest_path),
        cache_hash=pretest_cache_hash,
        seed=seed,
        output_path=reference_manifest_path,
    )
    repeated_reference_manifest = select_quality_references(
        reference_candidates,
        protocol=protocol,
        internal_manifest_hash=file_sha256(internal_manifest_path),
        cache_hash=pretest_cache_hash,
        seed=seed,
    )
    reference_repeat_match = reference_manifest == repeated_reference_manifest
    if set(reference_manifest["budget_to_reference_policy"]) != set(protocol.budget_ids):
        raise RuntimeError(f"Fixture reference readiness failure: {reference_manifest['budget_failures']}")
    reference_by_budget = reference_manifest["budget_to_reference_policy"]

    fit_rows = [
        {
            "split": "train_fit",
            "features": _features_for_item(item, train_fit_cache),
            "gate_error": 0.5 if index % 23 == 0 else 0.0,
        }
        for index, item in enumerate(train_fit_items)
    ]
    base_stop_model = fit_stop_risk_head(fit_rows, feature_names=("disagreement", "confidence_gap"), seed=seed)
    checkpoints = []
    for candidate in blueprint["candidate_packages"]:
        checkpoint_payload = {
            "fixture_only": True,
            "formal_eligible": False,
            "checkpoint_id": candidate["checkpoint_id"],
            "package_id": candidate["package_id"],
            "policy_kind": candidate["policy_kind"],
            "stop_risk_model": base_stop_model,
            "seed": seed,
        }
        checkpoint_path = run_dir / "checkpoints" / "fixture_candidates" / f"{candidate['checkpoint_id']}.json"
        write_json(checkpoint_path, checkpoint_payload, overwrite=True)
        checkpoints.append({
            "checkpoint_id": candidate["checkpoint_id"],
            "checkpoint_hash": file_sha256(checkpoint_path),
            "package_id": candidate["package_id"],
            "package_role": "router_candidate",
            "policy_kind": candidate["policy_kind"],
        })
    write_json(
        run_dir / "checkpoints" / "fixture_candidates" / "candidate_checkpoint_manifest.json",
        {"split": "train_fit", "formal_eligible": False, "checkpoints": checkpoints},
        overwrite=True,
    )

    calibration_item_to_paper = {
        str(item_id): str(paper["paper_id"])
        for paper in paper_result.papers_by_split["train_calibration"]
        for item_id in paper["items"]
    }
    checkpoint_by_id = {str(row["checkpoint_id"]): row for row in checkpoints}
    stop_results = []
    boundary_rows_by_checkpoint: dict[str, list[dict[str, Any]]] = {}
    for checkpoint in checkpoints:
        policy_kind = str(checkpoint["policy_kind"])
        reference_id = reference_by_budget["Tight"] if policy_kind == "reference_clone" else None
        simulation = _simulate_policy(
            papers=paper_result.papers_by_split["train_calibration"],
            items_by_id=train_items_by_id,
            cache=calibration_cache,
            policy_kind=policy_kind,
            reference_policy_id=reference_id,
            budget_id="Tight",
            budget=budgets["Tight"],
        )
        record_by_item = {str(row["item_id"]): row for row in simulation["records"]}
        risks = predict_stop_risk(base_stop_model, [{"features": _features_for_item(item, calibration_cache)} for item in calibration_items])
        boundary_rows = []
        for item, risk in zip(calibration_items, risks):
            record = record_by_item[str(item["item_id"])]
            boundary_rows.append({
                "split": "train_calibration",
                "dataset": str(item["dataset"]),
                "paper_id": calibration_item_to_paper[str(item["item_id"])],
                "item_id": str(item["item_id"]),
                "predicted_stop_risk": float(risk),
                "gate_error": normalized_gate_error(record),
            })
        boundary_rows_by_checkpoint[str(checkpoint["checkpoint_id"])] = boundary_rows
        stop_results.append(calibrate_stop_boundary(
            checkpoint_id=str(checkpoint["checkpoint_id"]),
            checkpoint_hash=str(checkpoint["checkpoint_hash"]),
            rows=boundary_rows,
            protocol=protocol,
            risk_limit=float(config["stop_calibration"]["risk_limit"]),
            confidence_level=float(config["stop_calibration"]["confidence_level"]),
            min_stops_per_dataset=int(config["stop_calibration"]["min_stops_per_dataset"]),
        ))
    repeated_stop_results = [
        calibrate_stop_boundary(
            checkpoint_id=str(checkpoint["checkpoint_id"]),
            checkpoint_hash=str(checkpoint["checkpoint_hash"]),
            rows=boundary_rows_by_checkpoint[str(checkpoint["checkpoint_id"])],
            protocol=protocol,
            risk_limit=float(config["stop_calibration"]["risk_limit"]),
            confidence_level=float(config["stop_calibration"]["confidence_level"]),
            min_stops_per_dataset=int(config["stop_calibration"]["min_stops_per_dataset"]),
        )
        for checkpoint in checkpoints
    ]
    stop_boundary_repeat_match = stop_results == repeated_stop_results
    write_jsonl(run_dir / "reports" / "stop_boundary_calibration.jsonl", stop_results, overwrite=True)
    package_result = build_policy_packages(
        checkpoints=checkpoints,
        calibration_results=stop_results,
        quality_protocol_hash=protocol_fingerprint(protocol),
        internal_manifest_hash=file_sha256(internal_manifest_path),
        quality_reference_manifest_hash=file_sha256(reference_manifest_path),
        budget_manifest_hash=file_sha256(budget_manifest_path),
        support_manifest_hash=file_sha256(support_manifest_path),
        output_dir=run_dir / "reports",
    )
    packages = package_result["policy_packages"]
    if len(packages) != len(checkpoints):
        raise RuntimeError("Fixture checkpoint 出现 calibration failure，无法完成成功链 Smoke")

    dev_items_by_id = {str(item["item_id"]): item for item in fixture["items_by_split"]["dev"]}
    dev_evaluations = []
    dev_records = {}
    fixed_gates = []
    dev_stop_boundary_applied_records = 0
    dev_stop_boundary_escalations = 0
    package_kind = {
        str(row["package_id"]): str(checkpoint_by_id[str(row["checkpoint_id"])]["policy_kind"])
        for row in packages
    }
    for budget_id in protocol.budget_ids:
        reference_id = reference_by_budget[budget_id]
        reference_simulation = _simulate_policy(
            papers=fixture["papers_by_split"]["dev"],
            items_by_id=dev_items_by_id,
            cache=dev_cache,
            policy_kind=reference_id,
            budget_id=budget_id,
            budget=budgets[budget_id],
        )
        write_jsonl(
            run_dir / "predictions" / f"dev_reference_{reference_id}_{budget_id}.jsonl",
            reference_simulation["records"],
            overwrite=True,
        )
        for package in packages:
            package_id = str(package["package_id"])
            kind = package_kind[package_id]
            simulation = _simulate_policy(
                papers=fixture["papers_by_split"]["dev"],
                items_by_id=dev_items_by_id,
                cache=dev_cache,
                policy_kind=kind,
                reference_policy_id=reference_id if kind == "reference_clone" else None,
                budget_id=budget_id,
                budget=budgets[budget_id],
                stop_risk_model=base_stop_model,
                stop_boundary=float(package["stop_boundary"]),
            )
            dev_stop_boundary_applied_records += int(simulation["resources"]["stop_boundary_applied_records"])
            dev_stop_boundary_escalations += int(simulation["resources"]["stop_boundary_escalations"])
            dev_records[(package_id, budget_id)] = simulation["records"]
            evaluation, _ = _evaluation_row(package_id, budget_id, simulation, protocol)
            dev_evaluations.append(evaluation)
            write_jsonl(
                run_dir / "predictions" / f"dev_{package_id}_{budget_id}.jsonl",
                simulation["records"],
                overwrite=True,
            )
            fixed_gates.append(paired_cluster_bootstrap(
                simulation["records"],
                reference_simulation["records"],
                protocol=protocol,
                candidate_id=package_id,
                comparator_id=reference_id,
                budget_id=budget_id,
                comparison_kind="fixed_reference",
            ).to_dict())

    preview = determine_quality_champion_after_reference_admission(
        packages,
        dev_evaluations,
        fixed_gates,
        protocol=protocol,
        reference_policy_by_budget=reference_by_budget,
    )
    if preview.quality_champion_package_id is None:
        raise RuntimeError("Fixture Smoke 没有固定参考准入可行 Package")
    champion = preview.quality_champion_package_id
    champion_gates = []
    for package_id in preview.reference_admission_feasible_ids:
        if package_id == champion:
            continue
        for budget_id in protocol.budget_ids:
            champion_gates.append(paired_cluster_bootstrap(
                dev_records[(package_id, budget_id)],
                dev_records[(champion, budget_id)],
                protocol=protocol,
                candidate_id=package_id,
                comparator_id=champion,
                budget_id=budget_id,
                comparison_kind="quality_champion",
            ).to_dict())
    all_gates = fixed_gates + champion_gates
    write_jsonl(run_dir / "reports" / "dev_quality_gate_bootstrap.jsonl", all_gates, overwrite=True)
    selection = select_policy_package(
        packages,
        dev_evaluations,
        all_gates,
        protocol=protocol,
        budget_ids=protocol.budget_ids,
        reference_policy_by_budget=reference_by_budget,
        output_dir=run_dir / "reports",
        overwrite=True,
    )
    repeated = select_policy_package(
        packages,
        dev_evaluations,
        all_gates,
        protocol=protocol,
        budget_ids=protocol.budget_ids,
        reference_policy_by_budget=reference_by_budget,
    )
    deterministic_checks = {
        "reference_mapping": reference_repeat_match,
        "stop_boundaries": stop_boundary_repeat_match,
        "quality_champion": selection.quality_champion_package_id == repeated.quality_champion_package_id,
        "quality_protection_set": selection.quality_protection_feasible_ids == repeated.quality_protection_feasible_ids,
        "selected_checkpoint": selection.selected_checkpoint_id == repeated.selected_checkpoint_id,
    }
    deterministic_repeat_match = all(deterministic_checks.values())
    if not deterministic_repeat_match:
        raise RuntimeError("Dev selector 相同输入重复运行不一致")

    selected_package_id = str(selection.selected_package_id)
    selected_kind = package_kind[selected_package_id]
    selected_package = next(package for package in packages if str(package["package_id"]) == selected_package_id)
    cache_results["test"] = run_agent_cache(
        config_path=agent_config_path,
        items_path=items_test_path,
        split="test",
        run_id=run_id,
        execution_mode="fixture_smoke",
        seed=seed,
        final_evaluation=True,
        output_root=output_root,
        external_split_manifest_path=test_manifest_path,
    )
    test_cache = _cache_index(cache_results["test"]["records"])
    test_items_by_id = {str(item["item_id"]): item for item in fixture["items_by_split"]["test"]}
    test_like_rows = []
    test_stop_boundary_applied_records = 0
    test_stop_boundary_escalations = 0
    for budget_id in protocol.budget_ids:
        reference_id = reference_by_budget[budget_id]
        selected_simulation = _simulate_policy(
            papers=fixture["papers_by_split"]["test"],
            items_by_id=test_items_by_id,
            cache=test_cache,
            policy_kind=selected_kind,
            reference_policy_id=reference_id if selected_kind == "reference_clone" else None,
            budget_id=budget_id,
            budget=budgets[budget_id],
            stop_risk_model=base_stop_model,
            stop_boundary=float(selected_package["stop_boundary"]),
        )
        test_stop_boundary_applied_records += int(selected_simulation["resources"]["stop_boundary_applied_records"])
        test_stop_boundary_escalations += int(selected_simulation["resources"]["stop_boundary_escalations"])
        reference_simulation = _simulate_policy(
            papers=fixture["papers_by_split"]["test"],
            items_by_id=test_items_by_id,
            cache=test_cache,
            policy_kind=reference_id,
            budget_id=budget_id,
            budget=budgets[budget_id],
        )
        evaluation, quality = _evaluation_row(selected_package_id, budget_id, selected_simulation, protocol)
        gate = paired_cluster_bootstrap(
            selected_simulation["records"],
            reference_simulation["records"],
            protocol=protocol,
            candidate_id=selected_package_id,
            comparator_id=reference_id,
            budget_id=budget_id,
            comparison_kind="fixed_reference",
        ).to_dict()
        test_like_rows.append({"budget_id": budget_id, "evaluation": evaluation, "quality": quality, "gate": gate})
        write_jsonl(
            run_dir / "predictions" / f"test_like_{selected_package_id}_{budget_id}.jsonl",
            selected_simulation["records"],
            overwrite=True,
        )
    test_like_manifest = {
        "manifest_version": "fixture_test_like_one_shot_v1",
        "run_id": run_id,
        "execution_mode": "fixture_smoke",
        "is_fixture": True,
        "formal_eligible": False,
        "one_shot": True,
        "selected_package_id": selected_package_id,
        "training_reads": 0,
        "calibration_updates": 0,
        "stop_boundary_applied_records": test_stop_boundary_applied_records,
        "stop_boundary_escalations": test_stop_boundary_escalations,
        "rows": test_like_rows,
    }
    write_json(
        run_dir / "reports" / "test_like_evaluation.json",
        test_like_manifest,
        overwrite=True,
    )

    all_cache_records = [record for result in cache_results.values() for record in result["records"]]
    counters.update({
        "cross_mode_cache_reuse": sum(
            record.get("execution_mode") != "fixture_smoke" or record.get("is_fixture") is not True
            for record in all_cache_records
        ),
        "online_agent_calls": sum(int(result.get("online_agent_calls") or 0) for result in cache_results.values()),
        "calibration_gradient_updates": sum(int(row.get("gradient_update_count", 0)) for row in stop_results) + int(support_manifest.get("calibration_gradient_updates", 0)),
        "calibration_replay_writes": sum(int(row.get("replay_write_count", 0)) for row in stop_results),
        "calibration_checkpoint_rankings": sum(int(row.get("checkpoint_ranking_count", 0)) for row in stop_results),
        "dev_boundary_updates": int(selection.dev_boundary_update_count),
        "quality_champion_resource_reads": int(selection.quality_champion_resource_read_count),
        "quality_champion_manual_overrides": int(selection.quality_champion_manual_override_count),
        "test_like_training_reads": int(test_like_manifest["training_reads"]),
    })
    nonzero = {key: value for key, value in counters.items() if value != 0}
    if nonzero:
        raise RuntimeError(f"Fixture Smoke 禁止行为计数非0: {nonzero}")

    required_artifacts = [
        "configs/fixture_smoke_run_manifest.json",
        "configs/context_support_catalog.json",
        "configs/agent_cache_manifest.json",
        "reports/fixture_isolation_audit.json",
        "reports/formal_loader_rejection_probes.json",
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
    ]
    missing_artifacts = [relative for relative in required_artifacts if not (run_dir / relative).exists()]
    if missing_artifacts:
        raise RuntimeError(f"Fixture Smoke 缺少验收产物: {missing_artifacts}")

    reference_clone_cost = _mean_cost(dev_evaluations, "pkg_c_reference_clone", protocol.budget_ids)
    selected_cost = _mean_cost(dev_evaluations, selected_package_id, protocol.budget_ids)
    summary = {
        "status": "passed",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "execution_mode": "fixture_smoke",
        "formal_eligible": False,
        "online_agent_calls": counters["online_agent_calls"],
        "quality_protocol": {
            "hash": protocol_fingerprint(protocol),
            "qwk_min_valid_completed": protocol.qwk_min_valid_completed,
            "bootstrap_replicates": protocol.bootstrap_replicates,
        },
        "internal_split_audit_passed": audit.passed,
        "internal_split_blocking_error_count": len(audit.errors),
        "reference_policy_by_budget": reference_by_budget,
        "reference_admission_feasible_ids": list(selection.reference_admission_feasible_ids),
        "quality_champion_package_id": selection.quality_champion_package_id,
        "quality_protection_feasible_ids": list(selection.quality_protection_feasible_ids),
        "selected_package_id": selection.selected_package_id,
        "selected_checkpoint_id": selection.selected_checkpoint_id,
        "reference_clone_mean_cost": reference_clone_cost,
        "selected_mean_cost": selected_cost,
        "deterministic_repeat_match": deterministic_repeat_match,
        "deterministic_checks": deterministic_checks,
        "stop_boundary_applied_records": dev_stop_boundary_applied_records + test_stop_boundary_applied_records,
        "stop_boundary_escalations": dev_stop_boundary_escalations + test_stop_boundary_escalations,
        "test_like_one_shot_completed": True,
        **counters,
    }
    review_lines = [
        "# Fixture Smoke 实现与产物自审",
        "",
        f"- run_id: {run_id}",
        "- 结论: PASS",
        "- formal_eligible: false",
        "- 真实/在线 Agent 调用: 0",
        "",
        "## 禁止行为计数",
        "",
        "| 检查项 | 数量 |",
        "|---|---:|",
        *[f"| {key} | {counters[key]} |" for key in AUDIT_COUNTER_KEYS],
        "",
        "## 质量优先反例",
        "",
        f"- 任一预算参考失败的 pkg_d_budget_failure 被整包淘汰: {'yes' if 'pkg_d_budget_failure' not in selection.reference_admission_feasible_ids else 'no'}",
        f"- 更省资源的 pkg_c_reference_clone 因冠军保护失败而禁止排序: {'yes' if 'pkg_c_reference_clone' not in selection.quality_protection_feasible_ids else 'no'}",
        f"- Quality Champion: {selection.quality_champion_package_id}",
        f"- 最终选择: {selection.selected_package_id}",
        f"- 重复选择一致: {str(deterministic_repeat_match).lower()}",
    ]
    write_json(run_dir / "reports" / "fixture_smoke_summary.json", summary, overwrite=True)
    log_lines = [
        f"run_id={run_id}",
        "execution_mode=fixture_smoke",
        f"source_items={audit.summary.get('source_item_count', 0)}",
        f"train_fit_papers={len(paper_result.papers_by_split['train_fit'])}",
        f"train_calibration_papers={len(paper_result.papers_by_split['train_calibration'])}",
        f"reference_mapping={json.dumps(reference_by_budget, ensure_ascii=False, sort_keys=True)}",
        f"quality_champion={selection.quality_champion_package_id}",
        f"selected_package={selection.selected_package_id}",
        f"deterministic_repeat_match={str(deterministic_repeat_match).lower()}",
        "test_like_one_shot_completed=true",
        "status=passed",
    ]
    (run_dir / "logs" / "fixture_smoke.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    (run_dir / "reports" / "fixture_smoke_contract_review.md").write_text("\n".join(review_lines) + "\n", encoding="utf-8")
    run_manifest["audit_counters"] = counters
    run_manifest["status"] = "passed"
    run_manifest["selected_package_id"] = selection.selected_package_id
    run_manifest["quality_champion_package_id"] = selection.quality_champion_package_id
    run_manifest["summary_hash"] = _stable_hash(summary)
    write_json(manifest_path, run_manifest, overwrite=True)
    artifact_manifest_path = run_dir / "configs" / "fixture_artifact_manifest.json"
    artifact_manifest = _build_fixture_artifact_manifest(run_dir)
    write_json(artifact_manifest_path, artifact_manifest, overwrite=True)
    if artifact_manifest["uncovered_artifact_count"] != 0:
        raise RuntimeError("Fixture artifact inventory contains uncovered artifacts")
    return summary
