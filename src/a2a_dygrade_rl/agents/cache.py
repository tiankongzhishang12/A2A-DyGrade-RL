"""Auditable Agent cache generation, validation, and resume support."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.agents.agent_registry import build_agent_registry
from a2a_dygrade_rl.agents.base_agent import strip_gold
from a2a_dygrade_rl.utils.io import ensure_dir, read_jsonl, read_yaml, write_jsonl, write_yaml
from a2a_dygrade_rl.utils.validation import validate_agent_output


CACHE_SCHEMA_VERSION = "1.0"
RUN_PREFIXES = {
    "fixture_smoke": "fixture_smoke_",
    "real_pilot": "real_pilot_",
    "formal_experiment": "formal_agent_cache_",
}
BASE_AGENT_IDS = ("CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent")
DEFAULT_ARBITRATOR_CONTEXTS = (
    ("CheapAgent", "MidAgent"),
    ("CheapAgent", "StrongAgent"),
    ("MidAgent", "StrongAgent"),
    ("CheapAgent", "MidAgent", "StrongAgent"),
    ("CheapAgent", "MidAgent", "EvidenceAgent"),
    ("CheapAgent", "StrongAgent", "EvidenceAgent"),
    ("MidAgent", "StrongAgent", "EvidenceAgent"),
    ("CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent"),
)


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_cache_key(
    *,
    item_id: str,
    agent_id: str,
    split: str,
    model_id: str,
    model_revision: str,
    prompt_hash: str,
    generation_parameters: dict[str, Any],
    context_hash: str,
    cache_schema_version: str,
) -> str:
    return stable_hash(
        {
            "item_id": item_id,
            "agent_id": agent_id,
            "split": split,
            "model_id": model_id,
            "model_revision": model_revision,
            "prompt_hash": prompt_hash,
            "generation_parameters": generation_parameters,
            "context_hash": context_hash,
            "cache_schema_version": cache_schema_version,
        }
    )


def validate_run_identity(run_id: str, execution_mode: str, is_fixture: bool) -> None:
    if execution_mode not in RUN_PREFIXES:
        raise ValueError(f"未知 execution_mode: {execution_mode}")
    expected_fixture = execution_mode == "fixture_smoke"
    if bool(is_fixture) != expected_fixture:
        raise ValueError("is_fixture 与 execution_mode 不一致")
    prefix = RUN_PREFIXES[execution_mode]
    if not run_id.startswith(prefix):
        raise ValueError(f"run_id 必须使用前缀 {prefix}: {run_id}")


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(temporary, path)


def _sample_items(items: list[dict[str, Any]], sample_size: int | None, seed: int) -> list[dict[str, Any]]:
    ordered = sorted(items, key=lambda item: stable_hash({"seed": seed, "item_id": item["item_id"]}))
    if sample_size is None or sample_size >= len(ordered):
        return ordered
    by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in ordered:
        by_dataset[str(item.get("dataset", "unknown"))].append(item)
    selected: list[dict[str, Any]] = []
    dataset_names = sorted(by_dataset)
    while len(selected) < sample_size and any(by_dataset.values()):
        for dataset in dataset_names:
            if by_dataset[dataset] and len(selected) < sample_size:
                selected.append(by_dataset[dataset].pop(0))
    return selected


def _load_existing(split_dir: Path, agent_ids: Iterable[str]) -> dict[str, dict[str, dict[str, Any]]]:
    existing: dict[str, dict[str, dict[str, Any]]] = {agent_id: {} for agent_id in agent_ids}
    for agent_id in agent_ids:
        path = split_dir / f"{agent_id}.jsonl"
        if not path.exists():
            continue
        for record in read_jsonl(path):
            key = str(record["cache_key"])
            if key in existing[agent_id] and existing[agent_id][key] != record:
                raise ValueError(f"发现冲突 active cache key: {key}")
            existing[agent_id][key] = record
    return existing


def _public_opinion(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": record["agent_id"],
        "pred_score": record["pred_score"],
        "confidence": record["confidence"],
        "justification": record["justification"],
        "evidence": record.get("evidence", {}),
    }


def _record_from_prediction(
    *,
    item: dict[str, Any],
    agent: Any,
    prediction: dict[str, Any],
    request: dict[str, Any],
    context: dict[str, Any],
    cache_key: str,
    run_id: str,
    execution_mode: str,
    split: str,
    schema_version: str,
) -> dict[str, Any]:
    context_agents = [opinion["agent_id"] for opinion in context.get("opinions", [])]
    record = {
        "item_id": item["item_id"],
        "agent_id": agent.agent_id,
        "run_id": run_id,
        "execution_mode": execution_mode,
        "is_fixture": execution_mode == "fixture_smoke",
        "pred_score": prediction["pred_score"],
        "confidence": prediction["confidence"],
        "justification": prediction["justification"],
        "evidence": prediction.get("evidence", {}),
        "cost": prediction["cost"],
        "latency": prediction["latency"],
        "token_usage": prediction["token_usage"],
        "gold_score": float(item["gold_score"]),
        "split": split,
        "model_id": agent.model_id,
        "prompt_version": agent.prompt_version,
        "prompt_hash": agent.prompt_hash,
        "input_hash": stable_hash(request),
        "context_hash": stable_hash(strip_gold(context)),
        "cache_key": cache_key,
        "cache_schema_version": schema_version,
        "status": "success",
        "error": None,
        "metadata": {
            "dataset": item.get("dataset"),
            "question_type": item.get("question_type"),
            "prompt_group": item.get("metadata", {}).get("prompt_group"),
            "score_min": float(item["score_min"]),
            "score_max": float(item["score_max"]),
            "model_revision": agent.model_revision,
            "generation_parameters": dict(agent.config.get("generation_parameters", {})),
            "context_agents": context_agents,
            "client": prediction.get("client_metadata", {}),
        },
    }
    return record


def run_agent_cache(
    *,
    config_path: str | Path,
    items_path: str | Path,
    split: str,
    run_id: str,
    execution_mode: str,
    seed: int = 42,
    sample_size: int | None = None,
    agents: list[str] | None = None,
    resume: bool = False,
    final_evaluation: bool = False,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Any]:
    is_fixture = execution_mode == "fixture_smoke"
    validate_run_identity(run_id, execution_mode, is_fixture)
    if split not in {"train", "dev", "test"}:
        raise ValueError(f"非法 split: {split}")
    if split == "test" and not final_evaluation:
        raise ValueError("生成 test cache 必须显式启用 final_evaluation")

    config = read_yaml(config_path)
    schema_version = str(config.get("cache_schema_version", CACHE_SCHEMA_VERSION))
    registry = build_agent_registry(config, execution_mode=execution_mode, seed=seed)
    selected_agent_ids = list(agents or registry.keys())
    unknown = set(selected_agent_ids) - set(registry)
    if unknown:
        raise ValueError(f"请求了未注册 Agent: {sorted(unknown)}")
    if "ArbitratorAgent" in selected_agent_ids and not set(BASE_AGENT_IDS).issubset(selected_agent_ids):
        raise ValueError("生成 ArbitratorAgent cache 时必须同时生成四类基础上下文 Agent")

    items = [item for item in read_jsonl(items_path) if item.get("metadata", {}).get("split") == split]
    if not items:
        raise ValueError(f"输入中没有 split={split} 的 item")
    items = _sample_items(items, sample_size, seed)
    item_ids = [str(item["item_id"]) for item in items]
    data_fingerprint = stable_hash({"split": split, "items": items})
    config_fingerprint = stable_hash(config)

    run_dir = Path(output_root) / run_id
    split_dir = run_dir / "predictions" / "agent_cache" / split
    manifest_path = run_dir / "configs" / "agent_cache_manifest.json"
    expected_identity = {
        "run_id": run_id,
        "execution_mode": execution_mode,
        "is_fixture": is_fixture,
        "seed": int(seed),
        "config_fingerprint": config_fingerprint,
        "cache_schema_version": schema_version,
    }
    split_manifest = {
        "data_fingerprint": data_fingerprint,
        "item_count": len(items),
        "item_ids": item_ids,
        "selected_agent_ids": sorted(selected_agent_ids),
    }
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
        actual_identity = {key: manifest.get(key) for key in expected_identity}
        if actual_identity != expected_identity:
            raise ValueError("Run manifest mismatch; cross-mode or cross-config cache reuse is forbidden")
        existing_split = manifest.get("splits", {}).get(split)
        if existing_split is not None:
            if not resume:
                raise FileExistsError(f"Split cache already exists; use resume to continue: {split_dir}")
            if existing_split != split_manifest:
                raise ValueError("Resume manifest mismatch; cross-data cache reuse is forbidden")
        manifest.setdefault("splits", {})[split] = split_manifest
    elif run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"Run directory exists without a valid cache manifest: {run_dir}")
    else:
        manifest = {**expected_identity, "splits": {split: split_manifest}}
    _atomic_write_json(manifest_path, manifest)
    ensure_dir(split_dir)
    write_yaml(run_dir / "configs" / "agents.resolved.yaml", config, overwrite=True)
    _atomic_write_json(run_dir / "configs" / f"data_fingerprint.{split}.json", {"fingerprint": data_fingerprint, "item_count": len(items), "item_ids": item_ids, "split": split})
    _atomic_write_json(
        run_dir / "configs" / "prompts_manifest.json",
        {agent_id: {"prompt_hash": agent.prompt_hash, "prompt_version": agent.prompt_version} for agent_id, agent in registry.items()},
    )

    existing = _load_existing(split_dir, selected_agent_ids)
    generated = 0
    reused = 0
    active_keys: dict[str, set[str]] = {agent_id: set() for agent_id in selected_agent_ids}

    def execute(item: dict[str, Any], agent_id: str, context: dict[str, Any]) -> dict[str, Any]:
        nonlocal generated, reused
        agent = registry[agent_id]
        request: dict[str, Any] = {}
        context_hash = stable_hash(strip_gold(context))
        key = build_cache_key(
            item_id=str(item["item_id"]),
            agent_id=agent_id,
            split=split,
            model_id=agent.model_id,
            model_revision=agent.model_revision,
            prompt_hash=agent.prompt_hash,
            generation_parameters=dict(agent.config.get("generation_parameters", {})),
            context_hash=context_hash,
            cache_schema_version=schema_version,
        )
        active_keys[agent_id].add(key)
        cached = existing[agent_id].get(key)
        if cached is not None and cached.get("status") == "success":
            expected_cached_identity = {
                "item_id": item["item_id"],
                "agent_id": agent_id,
                "run_id": run_id,
                "execution_mode": execution_mode,
                "is_fixture": is_fixture,
                "split": split,
                "model_id": agent.model_id,
                "prompt_version": agent.prompt_version,
                "prompt_hash": agent.prompt_hash,
                "context_hash": context_hash,
                "cache_key": key,
                "cache_schema_version": schema_version,
            }
            cached_identity = {field: cached.get(field) for field in expected_cached_identity}
            try:
                validate_agent_output(cached, item=item, allowed_agents=set(registry))
            except (KeyError, TypeError, ValueError):
                cached = None
            if cached is not None and cached_identity == expected_cached_identity:
                reused += 1
                return cached
        try:
            request = agent.build_request(item, context)
            prediction = agent.predict(item, context)
            record = _record_from_prediction(
                item=item,
                agent=agent,
                prediction=prediction,
                request=request,
                context=context,
                cache_key=key,
                run_id=run_id,
                execution_mode=execution_mode,
                split=split,
                schema_version=schema_version,
            )
            validate_agent_output(record, item=item, allowed_agents=set(registry))
        except Exception as exc:
            record = {
                "item_id": item["item_id"], "agent_id": agent_id, "run_id": run_id,
                "execution_mode": execution_mode, "is_fixture": is_fixture, "pred_score": None,
                "confidence": 0.0, "justification": "", "evidence": {}, "cost": 0.0,
                "latency": 0.0, "token_usage": 0, "gold_score": float(item["gold_score"]),
                "split": split, "model_id": agent.model_id, "prompt_version": agent.prompt_version,
                "prompt_hash": agent.prompt_hash, "input_hash": stable_hash(request),
                "context_hash": context_hash, "cache_key": key, "cache_schema_version": schema_version,
                "status": "failed", "error": f"{type(exc).__name__}: {exc}",
                "metadata": {"score_min": float(item["score_min"]), "score_max": float(item["score_max"])},
            }
            validate_agent_output(record, item=item, allowed_agents=set(registry))
        existing[agent_id][key] = record
        generated += 1
        return record

    contexts = tuple(tuple(value) for value in config.get("arbitrator_contexts", DEFAULT_ARBITRATOR_CONTEXTS))
    for item in items:
        item_records: dict[str, dict[str, Any]] = {}
        for agent_id in BASE_AGENT_IDS:
            if agent_id in selected_agent_ids:
                item_records[agent_id] = execute(item, agent_id, {})
        if "ArbitratorAgent" in selected_agent_ids:
            for context_agent_ids in contexts:
                opinions = [_public_opinion(item_records[agent_id]) for agent_id in context_agent_ids]
                execute(item, "ArbitratorAgent", {"opinions": opinions})

    all_records: list[dict[str, Any]] = []
    for agent_id in selected_agent_ids:
        agent_records = sorted(
            (existing[agent_id][key] for key in active_keys[agent_id]),
            key=lambda record: record["cache_key"],
        )
        write_jsonl(split_dir / f"{agent_id}.jsonl", agent_records, overwrite=True)
        all_records.extend(agent_records)
    all_records.sort(key=lambda record: record["cache_key"])
    keys = [record["cache_key"] for record in all_records]
    if len(keys) != len(set(keys)):
        raise ValueError("cache 中存在重复 active cache key")

    manifest_fields = ["cache_key", "item_id", "agent_id", "split", "status", "model_id", "prompt_hash", "context_hash", "execution_mode", "is_fixture"]
    _write_csv(split_dir / "cache_manifest.csv", all_records, manifest_fields)
    active_failures = [record for record in all_records if record["status"] != "success"]
    failure_log_path = run_dir / "logs" / f"failures.{split}.jsonl"
    if active_failures:
        write_jsonl(failure_log_path, active_failures, overwrite=True)
    elif failure_log_path.exists():
        failure_log_path.unlink()

    coverage_rows = []
    cost_rows = []
    for agent_id in selected_agent_ids:
        rows = [record for record in all_records if record["agent_id"] == agent_id]
        success = [record for record in rows if record["status"] == "success"]
        coverage_rows.append({"agent_id": agent_id, "records": len(rows), "success": len(success), "failure": len(rows) - len(success), "coverage": len(success) / max(1, len(rows))})
        cost_rows.append({"agent_id": agent_id, "total_cost": sum(float(row["cost"]) for row in success), "mean_latency": sum(float(row["latency"]) for row in success) / max(1, len(success)), "total_tokens": sum(int(row["token_usage"]) for row in success)})
    _write_csv(run_dir / "reports" / f"agent_cache_coverage.{split}.csv", coverage_rows, ["agent_id", "records", "success", "failure", "coverage"])
    _write_csv(run_dir / "reports" / f"agent_cache_cost_summary.{split}.csv", cost_rows, ["agent_id", "total_cost", "mean_latency", "total_tokens"])
    audit = (
        "# Agent Cache Audit\n\n"
        f"- run_id: `{run_id}`\n- execution_mode: `{execution_mode}`\n- split: `{split}`\n"
        f"- item_count: {len(items)}\n- record_count: {len(all_records)}\n"
        f"- generated: {generated}\n- reused: {reused}\n- failures: {len(active_failures)}\n"
        "- gold_in_request: 0（由 BaseAgent/FixtureClient 双重校验）\n"
    )
    audit_path = run_dir / "reports" / f"agent_cache_audit.{split}.md"
    ensure_dir(audit_path.parent)
    audit_path.write_text(audit, encoding="utf-8")
    return {"run_dir": str(run_dir), "records": all_records, "generated": generated, "reused": reused, "failures": len(active_failures), "item_count": len(items)}


def read_cache_records(cache_dir: str | Path, split: str) -> list[dict[str, Any]]:
    split_dir = Path(cache_dir) / split
    records: list[dict[str, Any]] = []
    for path in sorted(split_dir.glob("*.jsonl")):
        records.extend(read_jsonl(path))
    return sorted(records, key=lambda record: record["cache_key"])
