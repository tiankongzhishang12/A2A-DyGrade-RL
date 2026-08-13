"""Auditable Agent cache generation, validation, and resume support."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import inspect
import os
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.agents.agent_registry import build_agent_registry
from a2a_dygrade_rl.agents.base_agent import strip_gold
from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_csv, read_jsonl, read_yaml, write_jsonl, write_yaml
from a2a_dygrade_rl.utils.validation import validate_agent_output


CACHE_SCHEMA_VERSION = "1.0"
RUN_PREFIXES = {
    "fixture_smoke": "fixture_smoke_",
    "real_pilot": "real_pilot_",
    "formal_experiment": "formal_agent_cache_",
}
CACHE_SPLITS = {"train", "train_fit", "train_calibration", "dev", "test"}
BASE_AGENT_IDS = ("CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent")
SCORING_AGENT_IDS = ("CheapAgent", "MidAgent", "StrongAgent")
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

@dataclass(frozen=True)
class CacheScope:
    split: str
    item_ids: tuple[str, ...]
    scope_source: str
    scope_fingerprint: str
    formal_eligible: bool


def resolve_cache_scope(
    items: Iterable[dict[str, Any]],
    *,
    split: str,
    execution_mode: str,
    internal_item_manifest_path: str | Path | None = None,
    external_split_manifest_path: str | Path | None = None,
) -> CacheScope:
    """解析 cache Item 范围；Formal train 侧不得从旧 Paper 或 metadata 推断。"""

    if split not in CACHE_SPLITS:
        raise ValueError(f"非法 split: {split}")
    item_list = [dict(item) for item in items]
    item_index = {str(item.get("item_id", "")): item for item in item_list}
    if len(item_index) != len(item_list) or "" in item_index:
        raise ValueError("cache scope 输入存在重复或空 item_id")
    source: str
    selected_ids: set[str]
    source_payload: Any
    selected_manifest_rows: list[dict[str, Any]] = []

    if split in {"train_fit", "train_calibration"}:
        if internal_item_manifest_path is None:
            raise ValueError("train_fit/train_calibration 必须由 internal_item_split_manifest 提供 scope")
        manifest_path = Path(internal_item_manifest_path)
        if "paper_train" in manifest_path.name.lower():
            raise ValueError("禁止根据旧 Paper 推断内部 cache split")
        rows = read_csv(manifest_path)
        if not rows or any("internal_split" not in row or "source_split" not in row for row in rows):
            raise ValueError("internal_item_split_manifest schema 不完整")
        selected_manifest_rows = [row for row in rows if row.get("source_split") == "train" and row.get("internal_split") == split]
        selected_ids = {str(row.get("item_id", "")) for row in selected_manifest_rows}
        source = "internal_item_split_manifest"
        source_payload = {"file_sha256": file_sha256(manifest_path), "selected_item_ids": sorted(selected_ids)}
    elif split in {"dev", "test"} and external_split_manifest_path is not None:
        manifest_path = Path(external_split_manifest_path)
        rows = read_csv(manifest_path)
        if not rows or any("split" not in row or "item_id" not in row for row in rows):
            raise ValueError("external split manifest schema 不完整")
        selected_manifest_rows = [row for row in rows if row.get("split") == split]
        selected_ids = {str(row["item_id"]) for row in selected_manifest_rows}
        source = "external_split_manifest"
        source_payload = {"file_sha256": file_sha256(manifest_path), "selected_item_ids": sorted(selected_ids)}
    else:
        if execution_mode == "formal_experiment":
            if split == "train":
                raise ValueError("Formal cache 必须使用 train_fit/train_calibration，禁止 legacy train split")
            raise ValueError("Formal dev/test cache 必须提供 external split manifest")
        selected_ids = {
            item_id
            for item_id, item in item_index.items()
            if str(item.get("metadata", {}).get("split", "")) == split
        }
        source = "item_metadata_fixture_compat"
        source_payload = {"selected_item_ids": sorted(selected_ids)}

    if not selected_ids:
        raise ValueError(f"cache scope 中没有 split={split} 的 Item")
    missing = sorted(selected_ids - set(item_index))
    if missing:
        raise ValueError(f"cache manifest 引用输入中不存在的 Item: {missing[:10]}")
    if execution_mode == "formal_experiment":
        fixture_ids = []
        for item_id in sorted(selected_ids):
            metadata = item_index[item_id].get("metadata", {})
            if metadata.get("fixture") is True or metadata.get("is_fixture") is True or metadata.get("formal_eligible") is False or str(metadata.get("data_scope", "")).lower() == "fixture":
                fixture_ids.append(item_id)
        fixture_manifest_ids = []
        for row in selected_manifest_rows:
            formal_flag = str(row.get("formal_eligible", "")).strip().lower()
            fixture_flag = str(row.get("is_fixture", row.get("fixture", ""))).strip().lower()
            if formal_flag in {"false", "0", "no"} or fixture_flag in {"true", "1", "yes"}:
                fixture_manifest_ids.append(str(row.get("item_id", "")))
        if fixture_ids or fixture_manifest_ids:
            examples = sorted(set(fixture_ids + fixture_manifest_ids))[:10]
            raise ValueError(f"Fixture Item/manifest 不得进入 Formal cache scope: {examples}")
    return CacheScope(
        split=split,
        item_ids=tuple(sorted(selected_ids)),
        scope_source=source,
        scope_fingerprint=stable_hash({"split": split, "source": source, "payload": source_payload}),
        formal_eligible=execution_mode == "formal_experiment",
    )


def build_context_support_catalog(
    config: dict[str, Any],
    *,
    selected_agent_ids: Iterable[str],
    execution_mode: str,
    scope_source: str,
    scope_fingerprint: str,
) -> dict[str, Any]:
    raw_selected = [str(value).strip() for value in selected_agent_ids]
    if not raw_selected or any(not value for value in raw_selected):
        raise ValueError("context support catalog 至少需要一个非空 Agent")
    if len(raw_selected) != len(set(raw_selected)):
        raise ValueError("context support catalog 的 selected Agent 不得重复")
    allowed_agents = set(BASE_AGENT_IDS) | {"ArbitratorAgent"}
    unknown_agents = sorted(set(raw_selected) - allowed_agents)
    if unknown_agents:
        raise ValueError(f"context support catalog 包含未注册 Agent: {unknown_agents}")
    selected = tuple(sorted(raw_selected))
    selected_set = set(selected)
    contexts: set[tuple[str, ...]] = set()
    if "ArbitratorAgent" in selected_set:
        for raw_context in config.get("arbitrator_contexts", DEFAULT_ARBITRATOR_CONTEXTS):
            context = tuple(str(value) for value in raw_context)
            if not context or len(context) != len(set(context)):
                raise ValueError("context support catalog 包含空或重复 Agent context")
            if "ArbitratorAgent" in context or not set(context).issubset(selected_set):
                raise ValueError("context support catalog 包含未选择或非法 Agent")
            contexts.add(context)
    payload = {
        "catalog_version": "context_support_catalog_v1",
        "execution_mode": execution_mode,
        "formal_eligible": execution_mode == "formal_experiment",
        "online_agent_calls": 0 if execution_mode == "fixture_smoke" else None,
        "scope_source": str(scope_source),
        "scope_fingerprint": str(scope_fingerprint),
        "agent_ids": list(selected),
        "arbitrator_contexts": [list(context) for context in sorted(contexts)],
    }
    return {**payload, "catalog_hash": stable_hash(payload)}

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
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", str(run_id)) is None:
        raise ValueError("run_id must be a single safe path component")
    if execution_mode not in RUN_PREFIXES:
        raise ValueError(f"未知 execution_mode: {execution_mode}")
    expected_fixture = execution_mode == "fixture_smoke"
    if bool(is_fixture) != expected_fixture:
        raise ValueError("is_fixture 与 execution_mode 不一致")
    prefix = RUN_PREFIXES[execution_mode]
    if not run_id.startswith(prefix):
        raise ValueError(f"run_id 必须使用前缀 {prefix}: {run_id}")


def validate_cache_output_root(output_root: str | Path) -> Path:
    repository_root = Path(__file__).resolve().parents[3]
    resolved = Path(output_root).resolve()
    try:
        resolved.relative_to(repository_root)
        inside_repository = True
    except ValueError:
        inside_repository = False
    if inside_repository:
        try:
            resolved.relative_to(repository_root / "outputs" / "runs")
        except ValueError as exc:
            raise ValueError("Agent cache output_root inside the project must stay under outputs/runs") from exc
    return resolved


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_jsonl_durable(path: Path, record: dict[str, Any]) -> None:
    """Append a completed record and force it to disk before returning."""
    ensure_dir(path.parent)
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(payload + "\n")
        handle.flush()
        os.fsync(handle.fileno())


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


def _merge_recovery_journal(
    existing: dict[str, dict[str, dict[str, Any]]],
    journal_path: Path,
) -> int:
    if not journal_path.exists():
        return 0
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in read_jsonl(journal_path):
        agent_id = str(record.get("agent_id", ""))
        if agent_id not in existing:
            continue
        latest[(agent_id, str(record["cache_key"]))] = record
    recovered = 0
    for (agent_id, key), record in latest.items():
        if key not in existing[agent_id]:
            existing[agent_id][key] = record
            recovered += 1
    return recovered


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
    usage = dict(prediction.get("usage") or {})
    record = {
        "item_id": item["item_id"],
        "agent_id": agent.agent_id,
        "run_id": run_id,
        "execution_mode": execution_mode,
        "is_fixture": bool(getattr(agent.client, "is_fixture", False)),
        "pred_score": prediction["pred_score"],
        "confidence": prediction["confidence"],
        "justification": prediction["justification"],
        "evidence": prediction.get("evidence", {}),
        "trait_scores": prediction.get("trait_scores", {}),
        "cost": prediction["cost"],
        "latency": prediction["latency"],
        "token_usage": prediction["token_usage"],
        "input_tokens": int(usage.get("input_tokens", 0)),
        "cached_input_tokens": int(usage.get("cached_input_tokens", 0)),
        "cache_write_tokens": int(usage.get("cache_write_tokens", 0)),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_tokens": int(usage.get("reasoning_tokens", 0)),
        "input_text_tokens": int(usage.get("input_text_tokens", 0)),
        "input_vision_tokens": int(usage.get("input_vision_tokens", 0)),
        "gold_score": float(item["gold_score"]),
        "split": split,
        "model_id": agent.model_id,
        "prompt_version": agent.prompt_version,
        "prompt_hash": agent.prompt_hash,
        "input_hash": stable_hash(request),
        "context_hash": stable_hash(strip_gold(context)),
        "cache_key": cache_key,
        "logical_call_id": cache_key,
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
            "canonical_attempt_id": prediction.get("client_metadata", {}).get("canonical_attempt_id"),
            "serialized_request_sha256": prediction.get("client_metadata", {}).get("request_body_sha256"),
            "request_semantics_sha256": prediction.get("client_metadata", {}).get("request_semantics_sha256"),
            "asset_audit": prediction.get("client_metadata", {}).get("asset_audit", []),
            "official_api_equivalent_cost_usd": prediction.get("client_metadata", {}).get("pricing", {}).get("official_api_equivalent_cost_usd", prediction["cost"]),
            "actual_server_allocated_cost_usd": prediction.get("client_metadata", {}).get("pricing", {}).get("actual_server_allocated_cost_usd"),
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
    internal_item_manifest_path: str | Path | None = None,
    external_split_manifest_path: str | Path | None = None,
    checkpoint_item_limit: int | None = None,
    concurrency: int | None = None,
    max_total_calls_override: int | None = None,
    manifest_agent_ids: list[str] | None = None,
) -> dict[str, Any]:
    is_fixture = execution_mode == "fixture_smoke"
    validate_run_identity(run_id, execution_mode, is_fixture)
    output_root = validate_cache_output_root(output_root)
    if split not in CACHE_SPLITS:
        raise ValueError(f"非法 split: {split}")
    if split == "test" and not final_evaluation:
        raise ValueError("生成 test cache 必须显式启用 final_evaluation")

    config = read_yaml(config_path)
    runtime_config = copy.deepcopy(config)
    if max_total_calls_override is not None:
        if execution_mode != "real_pilot":
            raise ValueError("max_total_calls_override is only allowed for real_pilot recovery")
        approved_limit = int(config.get("provider", {}).get("max_total_calls", 0))
        if max_total_calls_override < approved_limit or max_total_calls_override <= 0:
            raise ValueError("max_total_calls_override must be at least the frozen configured limit")
        runtime_config.setdefault("provider", {})["max_total_calls"] = int(max_total_calls_override)
    schema_version = str(config.get("cache_schema_version", CACHE_SCHEMA_VERSION))
    registry = build_agent_registry(runtime_config, execution_mode=execution_mode, seed=seed)
    selected_agent_ids = list(agents or registry.keys())
    approved_agent_ids = list(manifest_agent_ids or selected_agent_ids)
    if not selected_agent_ids or len(selected_agent_ids) != len(set(selected_agent_ids)):
        raise ValueError("selected agent列表必须非空且不重复")
    if not approved_agent_ids or len(approved_agent_ids) != len(set(approved_agent_ids)):
        raise ValueError("manifest agent列表必须非空且不重复")
    unknown = (set(selected_agent_ids) | set(approved_agent_ids)) - set(registry)
    if unknown:
        raise ValueError(f"请求了未注册 Agent: {sorted(unknown)}")
    if not set(selected_agent_ids).issubset(approved_agent_ids):
        raise ValueError("执行Agent必须是manifest Agent集合的子集")
    if "ArbitratorAgent" in selected_agent_ids and not set(BASE_AGENT_IDS).issubset(selected_agent_ids):
        raise ValueError("生成 ArbitratorAgent cache 时必须同时生成四类基础上下文 Agent")

    all_items = read_jsonl(items_path)
    scope = resolve_cache_scope(
        all_items,
        split=split,
        execution_mode=execution_mode,
        internal_item_manifest_path=internal_item_manifest_path,
        external_split_manifest_path=external_split_manifest_path,
    )
    selected_item_id_set = set(scope.item_ids)
    items = []
    for item in all_items:
        if str(item.get("item_id", "")) not in selected_item_id_set:
            continue
        selected_item = dict(item)
        if split in {"train_fit", "train_calibration"}:
            selected_item["metadata"] = {
                **item.get("metadata", {}),
                "source_split": str(item.get("metadata", {}).get("split", "train")),
                "split": split,
                "internal_split": split,
            }
        items.append(selected_item)
    items = _sample_items(items, sample_size, seed)
    item_ids = [str(item["item_id"]) for item in items]
    if checkpoint_item_limit is not None and checkpoint_item_limit <= 0:
        raise ValueError("checkpoint_item_limit must be a positive integer")
    execution_items = items[:checkpoint_item_limit] if checkpoint_item_limit is not None else items
    data_fingerprint = stable_hash({"split": split, "items": items})
    config_fingerprint = stable_hash(config)
    pricing_manifest_path = config.get("provider", {}).get("pricing_manifest_path")
    pricing_manifest_hash = file_sha256(pricing_manifest_path) if pricing_manifest_path else None
    context_catalog = build_context_support_catalog(
        config,
        selected_agent_ids=approved_agent_ids,
        execution_mode=execution_mode,
        scope_source="cache_run_config",
        scope_fingerprint=config_fingerprint,
    )

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
        "formal_eligible": execution_mode == "formal_experiment",
        "context_support_catalog_hash": context_catalog["catalog_hash"],
        "pricing_manifest_hash": pricing_manifest_hash,
    }
    split_manifest = {
        "data_fingerprint": data_fingerprint,
        "item_count": len(items),
        "item_ids": item_ids,
        "selected_agent_ids": sorted(approved_agent_ids),
        "scope_source": scope.scope_source,
        "scope_fingerprint": scope.scope_fingerprint,
        "formal_eligible": scope.formal_eligible,
        "checkpoint_item_limit": None,
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
        fixture_manifest_path = run_dir / "configs" / "fixture_smoke_run_manifest.json"
        pilot_manifest_path = run_dir / "configs" / "pilot_sample_manifest.json"
        allowed_bootstrap = False
        if execution_mode == "fixture_smoke" and fixture_manifest_path.exists():
            fixture_manifest = _read_json(fixture_manifest_path)
            allowed_bootstrap = (
                fixture_manifest.get("run_id") == run_id
                and fixture_manifest.get("execution_mode") == "fixture_smoke"
                and fixture_manifest.get("formal_eligible") is False
            )
        elif execution_mode == "real_pilot" and pilot_manifest_path.exists():
            pilot_manifest = _read_json(pilot_manifest_path)
            allowed_bootstrap = (
                pilot_manifest.get("run_id") == run_id
                and pilot_manifest.get("execution_mode") == "real_pilot"
                and pilot_manifest.get("formal_eligible") is False
                and pilot_manifest.get("split") == split
                and int(pilot_manifest.get("item_count", 0)) == len(items)
            )
        if not allowed_bootstrap:
            raise FileExistsError(f"Run directory exists without a valid cache bootstrap manifest: {run_dir}")
        manifest = {**expected_identity, "splits": {split: split_manifest}}
    else:
        manifest = {**expected_identity, "splits": {split: split_manifest}}
    if max_total_calls_override is not None:
        manifest["operational_max_total_calls_override"] = int(max_total_calls_override)
        manifest["experimental_effective_call_target"] = len(execution_items) * (len(BASE_AGENT_IDS) + len(context_catalog["arbitrator_contexts"]))
    manifest["latest_execution_agent_ids"] = sorted(selected_agent_ids)
    manifest["approved_manifest_agent_ids"] = sorted(approved_agent_ids)
    _atomic_write_json(manifest_path, manifest)
    _atomic_write_json(run_dir / "configs" / "context_support_catalog.json", context_catalog)
    ensure_dir(split_dir)
    write_yaml(run_dir / "configs" / "agents.resolved.yaml", config, overwrite=True)
    if pricing_manifest_path:
        write_yaml(
            run_dir / "configs" / "pricing_manifest.yaml",
            read_yaml(pricing_manifest_path),
            overwrite=True,
        )
    _atomic_write_json(run_dir / "configs" / f"data_fingerprint.{split}.json", {"fingerprint": data_fingerprint, "item_count": len(items), "item_ids": item_ids, "split": split})
    prompt_snapshot_dir = ensure_dir(run_dir / "configs" / "prompts")
    prompt_manifest: dict[str, dict[str, Any]] = {}
    for agent_id, agent in registry.items():
        snapshot_path = prompt_snapshot_dir / f"{agent_id}.txt"
        snapshot_path.write_text(agent.prompt_text, encoding="utf-8", newline="\n")
        prompt_manifest[agent_id] = {
            "prompt_hash": agent.prompt_hash,
            "prompt_version": agent.prompt_version,
            "snapshot_path": str(snapshot_path.relative_to(run_dir)),
            "snapshot_sha256": file_sha256(snapshot_path),
        }
    _atomic_write_json(run_dir / "configs" / "prompts_manifest.json", prompt_manifest)

    journal_path = run_dir / "logs" / f"cache_journal.{split}.jsonl"
    reporting_agent_ids = approved_agent_ids
    existing = _load_existing(split_dir, reporting_agent_ids)
    journal_recovered_records = _merge_recovery_journal(existing, journal_path)
    shared_client = next(iter(registry.values())).client
    existing_success = [
        record
        for agent_records in existing.values()
        for record in agent_records.values()
        if record.get("status") == "success"
    ]
    success_calls = sum(
        int(record.get("metadata", {}).get("client", {}).get("attempt_count", 1))
        for record in existing_success
    )
    success_cost = sum(float(record.get("cost", 0.0)) for record in existing_success)
    shared_client.initialize_budget(
        calls=max(success_calls, int(manifest.get("online_agent_calls", 0))),
        cost_usd=max(success_cost, float(manifest.get("api_cost_usd", 0.0))),
    )
    generated = 0
    reused = 0
    state_lock = threading.Lock()
    invalid_reuse_events: list[dict[str, Any]] = []
    active_keys: dict[str, set[str]] = {
        # 本轮会重新计算被选 Agent 的完整逻辑调用图；只保留本轮实际命中的 key，
        # 避免依赖失败恢复后把旧 context_hash 对应的失败记录继续当作 active cache。
        # 未在本阶段执行的 Agent 则必须保留，供单卡服务器按模型分阶段合并同一 run。
        agent_id: (set() if agent_id in selected_agent_ids else set(existing[agent_id]))
        for agent_id in reporting_agent_ids
    }

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
        with state_lock:
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
            rejection_reason = ""
            try:
                validate_agent_output(cached, item=item, allowed_agents=set(registry))
            except (KeyError, TypeError, ValueError) as exc:
                rejection_reason = f"validation_error:{type(exc).__name__}:{exc}"
            if not rejection_reason and cached_identity != expected_cached_identity:
                rejection_reason = "cached_identity_mismatch"
            if rejection_reason:
                invalid_reuse_events.append({
                    "run_id": run_id,
                    "execution_mode": execution_mode,
                    "split": split,
                    "item_id": str(item["item_id"]),
                    "agent_id": agent_id,
                    "cache_key": key,
                    "reason": rejection_reason,
                    "expected_identity": expected_cached_identity,
                    "observed_identity": cached_identity,
                })
                cached = None
            else:
                with state_lock:
                    reused += 1
                return cached
        try:
            request = agent.build_request(item, context)
            predict_parameters = inspect.signature(agent.predict).parameters
            if "logical_call_id" in predict_parameters:
                prediction = agent.predict(item, context, logical_call_id=key)
            else:  # 兼容测试或历史扩展中只接受 item/context 的包装器。
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
                "execution_mode": execution_mode, "is_fixture": bool(getattr(agent.client, "is_fixture", False)), "pred_score": None,
                "confidence": 0.0, "justification": "", "evidence": {}, "trait_scores": {}, "cost": 0.0,
                "latency": 0.0, "token_usage": 0, "input_tokens": 0,
                "cached_input_tokens": 0, "cache_write_tokens": 0, "output_tokens": 0,
                "reasoning_tokens": 0, "input_text_tokens": 0, "input_vision_tokens": 0, "gold_score": float(item["gold_score"]),
                "split": split, "model_id": agent.model_id, "prompt_version": agent.prompt_version,
                "prompt_hash": agent.prompt_hash, "input_hash": stable_hash(request),
                "context_hash": context_hash, "cache_key": key, "logical_call_id": key, "cache_schema_version": schema_version,
                "status": "failed", "error": f"{type(exc).__name__}: {exc}",
                "metadata": {"score_min": float(item["score_min"]), "score_max": float(item["score_max"]), "client": {}},
            }
            validate_agent_output(record, item=item, allowed_agents=set(registry))
        with state_lock:
            _append_jsonl_durable(journal_path, record)
            existing[agent_id][key] = record
            generated += 1
            progress_budget = shared_client.budget_snapshot()
            manifest["online_agent_calls"] = int(progress_budget.get("calls", 0)) if not is_fixture else 0
            manifest["api_cost_usd"] = float(progress_budget.get("cost_usd", 0.0)) if not is_fixture else 0.0
            manifest["journal_record_count"] = sum(len(records) for records in existing.values())
            manifest["in_progress_target_item_count"] = len(execution_items)
            _atomic_write_json(manifest_path, manifest)
        return record

    contexts = tuple(tuple(value) for value in context_catalog["arbitrator_contexts"])

    def process_item(item: dict[str, Any]) -> None:
        item_records: dict[str, dict[str, Any]] = {}
        for agent_id in BASE_AGENT_IDS:
            if agent_id in selected_agent_ids:
                item_records[agent_id] = execute(item, agent_id, {})
        if "ArbitratorAgent" in selected_agent_ids:
            for context_agent_ids in contexts:
                opinions = [_public_opinion(item_records[agent_id]) for agent_id in context_agent_ids]
                execute(item, "ArbitratorAgent", {"opinions": opinions})

    configured_concurrency = int(concurrency or config.get("provider", {}).get("concurrency", 1))
    if configured_concurrency <= 0:
        raise ValueError("concurrency must be a positive integer")
    if configured_concurrency == 1 or len(execution_items) <= 1:
        for item in execution_items:
            process_item(item)
    else:
        with ThreadPoolExecutor(max_workers=configured_concurrency, thread_name_prefix="agent-cache") as executor:
            list(executor.map(process_item, execution_items))

    all_records: list[dict[str, Any]] = []
    for agent_id in reporting_agent_ids:
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
    failure_history = read_jsonl(failure_log_path) if failure_log_path.exists() else []
    if active_failures:
        snapshots: dict[str, dict[str, Any]] = {stable_hash(record): record for record in failure_history}
        for record in active_failures:
            snapshots.setdefault(stable_hash(record), record)
        failure_history = [snapshots[key] for key in sorted(snapshots)]
        write_jsonl(failure_log_path, failure_history, overwrite=True)

    rejection_log_path = run_dir / "logs" / f"cache_reuse_rejections.{split}.jsonl"
    rejection_history = read_jsonl(rejection_log_path) if rejection_log_path.exists() else []
    if invalid_reuse_events:
        rejection_snapshots: dict[str, dict[str, Any]] = {
            stable_hash(record): record for record in rejection_history
        }
        for record in invalid_reuse_events:
            rejection_snapshots.setdefault(stable_hash(record), record)
        rejection_history = [rejection_snapshots[key] for key in sorted(rejection_snapshots)]
        write_jsonl(rejection_log_path, rejection_history, overwrite=True)

    attempt_log_path = Path(str(config.get("provider", {}).get("attempt_log_path", "")))
    attempt_rows = read_jsonl(attempt_log_path) if str(attempt_log_path) not in {"", "."} and attempt_log_path.exists() else []
    retry_overhead_by_agent = {
        agent_id: sum(
            float(row.get("official_api_equivalent_cost_usd", 0.0))
            for row in attempt_rows
            if row.get("agent_id") == agent_id and row.get("status") != "success"
        )
        for agent_id in reporting_agent_ids
    }
    retry_server_overhead_by_agent = {
        agent_id: sum(
            float(row.get("actual_server_allocated_cost_usd") or 0.0)
            for row in attempt_rows
            if row.get("agent_id") == agent_id and row.get("status") != "success"
        )
        for agent_id in reporting_agent_ids
    }
    coverage_rows = []
    cost_rows = []
    for agent_id in reporting_agent_ids:
        rows = [record for record in all_records if record["agent_id"] == agent_id]
        success = [record for record in rows if record["status"] == "success"]
        coverage_rows.append({"agent_id": agent_id, "records": len(rows), "success": len(success), "failure": len(rows) - len(success), "coverage": len(success) / max(1, len(rows))})
        cost_rows.append({
            "agent_id": agent_id,
            "total_cost": sum(float(row["cost"]) for row in success),
            "mean_latency": sum(float(row["latency"]) for row in success) / max(1, len(success)),
            "total_tokens": sum(int(row["token_usage"]) for row in success),
            "input_tokens": sum(int(row.get("input_tokens", 0)) for row in success),
            "input_text_tokens": sum(int(row.get("input_text_tokens", 0)) for row in success),
            "input_vision_tokens": sum(int(row.get("input_vision_tokens", 0)) for row in success),
            "cached_input_tokens": sum(int(row.get("cached_input_tokens", 0)) for row in success),
            "cache_write_tokens": sum(int(row.get("cache_write_tokens", 0)) for row in success),
            "output_tokens": sum(int(row.get("output_tokens", 0)) for row in success),
            "reasoning_tokens": sum(int(row.get("reasoning_tokens", 0)) for row in success),
            "canonical_actual_server_allocated_cost_usd": sum(
                float(row.get("metadata", {}).get("actual_server_allocated_cost_usd") or 0.0)
                for row in success
            ),
            "operational_retry_overhead_usd": retry_overhead_by_agent.get(agent_id, 0.0),
            "operational_retry_server_overhead_usd": retry_server_overhead_by_agent.get(agent_id, 0.0),
        })
    _write_csv(run_dir / "reports" / f"agent_cache_coverage.{split}.csv", coverage_rows, ["agent_id", "records", "success", "failure", "coverage"])
    _write_csv(
        run_dir / "reports" / f"agent_cache_cost_summary.{split}.csv",
        cost_rows,
        ["agent_id", "total_cost", "mean_latency", "total_tokens", "input_tokens", "input_text_tokens", "input_vision_tokens", "cached_input_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "canonical_actual_server_allocated_cost_usd", "operational_retry_overhead_usd", "operational_retry_server_overhead_usd"],
    )
    audit = (
        "# Agent Cache Audit\n\n"
        f"- run_id: `{run_id}`\n- execution_mode: `{execution_mode}`\n- split: `{split}`\n"
        f"- item_count: {len(items)}\n- record_count: {len(all_records)}\n"
        f"- generated: {generated}\n- reused: {reused}\n- failures: {len(active_failures)}\n"
        f"- failure_history_count: {len(failure_history)}\n"
        f"- invalid_cache_reuse_rejections: {len(invalid_reuse_events)}\n"
        f"- invalid_cache_reuse_history_count: {len(rejection_history)}\n"
        "- gold_in_request: 0（由 BaseAgent 与客户端序列化审计双重校验）\n"
    )
    audit_path = run_dir / "reports" / f"agent_cache_audit.{split}.md"
    ensure_dir(audit_path.parent)
    audit_path.write_text(audit, encoding="utf-8")
    budget_snapshot = shared_client.budget_snapshot()
    manifest["online_agent_calls"] = int(budget_snapshot.get("calls", 0)) if not is_fixture else 0
    manifest["api_cost_usd"] = float(budget_snapshot.get("cost_usd", 0.0)) if not is_fixture else 0.0
    manifest["operational_retry_overhead_usd"] = sum(retry_overhead_by_agent.values())
    manifest["operational_retry_server_overhead_usd"] = sum(retry_server_overhead_by_agent.values())
    manifest["completed_item_count"] = len(execution_items)
    _atomic_write_json(manifest_path, manifest)
    return {
        "run_dir": str(run_dir),
        "records": all_records,
        "generated": generated,
        "reused": reused,
        "failures": len(active_failures),
        "failure_history_count": len(failure_history),
        "invalid_cache_reuse_rejections": len(invalid_reuse_events),
        "invalid_cache_reuse_history_count": len(rejection_history),
        "journal_recovered_records": journal_recovered_records,
        "item_count": len(items),
        "completed_item_count": len(execution_items),
        "scope_source": scope.scope_source,
        "scope_fingerprint": scope.scope_fingerprint,
        "context_support_catalog_hash": context_catalog["catalog_hash"],
        "formal_eligible": scope.formal_eligible,
        "online_agent_calls": int(budget_snapshot.get("calls", 0)) if not is_fixture else 0,
        "api_cost_usd": float(budget_snapshot.get("cost_usd", 0.0)) if not is_fixture else 0.0,
    }


def read_cache_records(cache_dir: str | Path, split: str) -> list[dict[str, Any]]:
    split_dir = Path(cache_dir) / split
    records: list[dict[str, Any]] = []
    for path in sorted(split_dir.glob("*.jsonl")):
        records.extend(read_jsonl(path))
    return sorted(records, key=lambda record: record["cache_key"])
