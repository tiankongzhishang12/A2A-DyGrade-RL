"""自托管五题 checkpoint 的 fail-closed 验收。"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.agents.pricing import (
    TokenUsage,
    compute_api_cost,
    compute_server_allocated_cost,
    load_pricing_manifest,
)
from a2a_dygrade_rl.utils.io import file_sha256, read_jsonl, read_yaml, write_json
from a2a_dygrade_rl.utils.llm_client import SELFHOSTED_AGENT_RESPONSE_SCHEMA
from a2a_dygrade_rl.utils.model_input import find_banned_keys
from a2a_dygrade_rl.utils.validation import validate_agent_output


EXPECTED_AGENTS = {"CheapAgent", "MidAgent", "StrongAgent"}
EXPECTED_MODELS = {
    "CheapAgent": "mistralai/Ministral-3-3B-Instruct-2512-BF16",
    "MidAgent": "mistralai/Ministral-3-8B-Instruct-2512-BF16",
    "StrongAgent": "mistralai/Ministral-3-14B-Instruct-2512-BF16",
}
MODEL_TO_AGENT = {model_id: agent_id for agent_id, model_id in EXPECTED_MODELS.items()}


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_captured_request(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise ValueError("captured body缺少messages列表")
    text_blocks = [
        block
        for message in messages
        if isinstance(message, dict)
        for block in (message.get("content") if isinstance(message.get("content"), list) else [])
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    if len(text_blocks) != 1:
        raise ValueError(f"captured body必须恰有一个text block，实际={len(text_blocks)}")
    payload = json.loads(str(text_blocks[0].get("text", "")))
    if not isinstance(payload, dict) or not isinstance(payload.get("request"), dict):
        raise ValueError("captured text block缺少request对象")
    return dict(payload["request"])


def validate_selfhosted_checkpoint(
    *,
    run_dir: str | Path,
    items_path: str | Path,
    transport_kind: str,
) -> dict[str, Any]:
    root = Path(run_dir)
    if transport_kind not in {"fake", "urllib"}:
        raise ValueError(f"不支持的transport_kind: {transport_kind}")
    items_file = Path(items_path).resolve()
    items = read_jsonl(items_file)
    item_index = {str(row["item_id"]): row for row in items}
    expected_item_ids = set(item_index)
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "blocking": True, "detail": detail})

    records: list[dict[str, Any]] = []
    cache_dir = root / "predictions" / "agent_cache" / "train_fit"
    cache_agent_files = sorted(cache_dir.glob("*.jsonl")) if cache_dir.is_dir() else []
    present_cache_agents = {path.stem for path in cache_agent_files}
    unexpected_cache_agents = sorted(present_cache_agents - EXPECTED_AGENTS)
    missing_cache_agents = sorted(EXPECTED_AGENTS - present_cache_agents)
    for path in cache_agent_files:
        records.extend(read_jsonl(path))
    check("item_count", len(items) == 5 and len(item_index) == 5, f"rows={len(items)} unique_items={len(item_index)}")
    checkpoint_manifest_path = items_file.parents[2] / "configs" / "selfhosted_checkpoint_manifest.json"
    checkpoint_manifest = (
        json.loads(checkpoint_manifest_path.read_text(encoding="utf-8"))
        if checkpoint_manifest_path.is_file()
        else {}
    )
    checkpoint_identity_valid = (
        checkpoint_manifest.get("semantic_readiness_status") == "PASS"
        and checkpoint_manifest.get("formal_eligible") is False
        and int(checkpoint_manifest.get("item_count", 0)) == 5
        and int(checkpoint_manifest.get("expected_canonical_calls", 0)) == 15
        and checkpoint_manifest.get("outputs", {}).get("items_sha256") == file_sha256(items_file)
        and set(map(str, checkpoint_manifest.get("selected_item_ids", []))) == set(item_index)
    )
    check(
        "checkpoint_input_identity",
        checkpoint_identity_valid,
        f"manifest={checkpoint_manifest_path} sha_match={checkpoint_manifest.get('outputs', {}).get('items_sha256') == file_sha256(items_file) if checkpoint_manifest else False}",
    )
    check("canonical_record_count", len(records) == 15, f"records={len(records)}")
    agent_counts = Counter(str(row.get("agent_id")) for row in records)
    check("agent_set", agent_counts == Counter({agent_id: 5 for agent_id in EXPECTED_AGENTS}), str(agent_counts))
    combo_counts = Counter((str(row.get("item_id")), str(row.get("agent_id"))) for row in records)
    expected_combos = {(item_id, agent_id) for item_id in expected_item_ids for agent_id in EXPECTED_AGENTS}
    check("canonical_uniqueness", set(combo_counts) == expected_combos and all(value == 1 for value in combo_counts.values()), f"combos={len(combo_counts)} expected={len(expected_combos)} max={max(combo_counts.values(), default=0)}")
    check("all_success", all(row.get("status") == "success" for row in records), f"failures={sum(row.get('status') != 'success' for row in records)}")
    record_agent_file_mismatches = sorted(
        f"{path.name}:{row.get('agent_id')}"
        for path in cache_agent_files
        for row in read_jsonl(path)
        if str(row.get("agent_id", "")) != path.stem
    )
    check(
        "forbidden_agents",
        not unexpected_cache_agents
        and not missing_cache_agents
        and not record_agent_file_mismatches
        and not any(row.get("agent_id") in {"EvidenceAgent", "ArbitratorAgent"} for row in records),
        f"unexpected_files={unexpected_cache_agents} missing_files={missing_cache_agents} "
        f"file_record_mismatches={record_agent_file_mismatches[:5]}",
    )
    expected_execution_mode = "fixture_smoke" if transport_kind == "fake" else "real_pilot"
    expected_fixture_flag = transport_kind == "fake"
    expected_run_id = root.name
    identity_errors = [
        f"{row.get('item_id')}:{row.get('agent_id')}:run={row.get('run_id')}:mode={row.get('execution_mode')}:fixture={row.get('is_fixture')}"
        for row in records
        if row.get("run_id") != expected_run_id
        or row.get("execution_mode") != expected_execution_mode
        or row.get("is_fixture") is not expected_fixture_flag
    ]
    agent_cache_manifest_path = root / "configs" / "agent_cache_manifest.json"
    agent_cache_manifest = (
        json.loads(agent_cache_manifest_path.read_text(encoding="utf-8"))
        if agent_cache_manifest_path.is_file()
        else {}
    )
    stage_manifest_path = root / "configs" / (
        "fixture_smoke_run_manifest.json" if transport_kind == "fake" else "pilot_sample_manifest.json"
    )
    stage_manifest = (
        json.loads(stage_manifest_path.read_text(encoding="utf-8"))
        if stage_manifest_path.is_file()
        else {}
    )
    manifest_identity_errors = []
    if (
        agent_cache_manifest.get("run_id") != expected_run_id
        or agent_cache_manifest.get("execution_mode") != expected_execution_mode
        or agent_cache_manifest.get("is_fixture") is not expected_fixture_flag
    ):
        manifest_identity_errors.append("agent_cache_manifest")
    if (
        stage_manifest.get("run_id") != expected_run_id
        or stage_manifest.get("execution_mode") != expected_execution_mode
        or stage_manifest.get("transport_kind") != transport_kind
        or stage_manifest.get("formal_eligible") is not False
    ):
        manifest_identity_errors.append(stage_manifest_path.name)
    check(
        "run_identity",
        not identity_errors and not manifest_identity_errors,
        f"record_errors={identity_errors[:10]} manifest_errors={manifest_identity_errors}",
    )

    validation_errors: list[str] = []
    model_errors: list[str] = []
    dress_errors: list[str] = []
    asset_errors: list[str] = []
    token_errors: list[str] = []
    cost_errors: list[str] = []
    logical_ids: list[str] = []
    canonical_attempt_ids: list[str] = []
    request_audit_errors: list[str] = []
    request_semantics_by_item: dict[str, set[str]] = {}
    record_request_semantics_by_combo: dict[tuple[str, str], str] = {}
    image_strategy_by_item: dict[str, set[str]] = {}
    run_config_path = root / "configs" / "agents.resolved.yaml"
    run_config = read_yaml(run_config_path) if run_config_path.exists() else {}
    pricing_path = root / "configs" / "pricing_manifest.yaml"
    pricing = load_pricing_manifest(pricing_path) if pricing_path.exists() else None
    server_hourly_price = run_config.get("provider", {}).get("server_hourly_price_usd")
    runtime_identity_valid = (
        str(run_config.get("provider", {}).get("transport", "")) == transport_kind
        and bool(run_config.get("local_preparation_only", False)) == (transport_kind == "fake")
        and run_config.get("formal_eligible") is False
        and str(run_config.get("provider", {}).get("usage_source", "")) == "server_reported"
        and run_config.get("provider", {}).get("require_reported_model_match") is True
        and run_config.get("provider", {}).get("require_usage") is True
        and run_config.get("provider", {}).get("require_multimodal_token_breakdown") is True
    )
    check("runtime_identity", runtime_identity_valid, str({
        "transport": run_config.get("provider", {}).get("transport"),
        "local_preparation_only": run_config.get("local_preparation_only"),
        "formal_eligible": run_config.get("formal_eligible"),
    }))
    for row in records:
        item = item_index.get(str(row.get("item_id")))
        if item is None:
            validation_errors.append(f"missing item:{row.get('item_id')}")
            continue
        try:
            validate_agent_output(row, item=item, allowed_agents=EXPECTED_AGENTS)
        except Exception as exc:
            validation_errors.append(f"{row.get('item_id')}:{row.get('agent_id')}:{exc}")
        expected_model = EXPECTED_MODELS.get(str(row.get("agent_id")))
        client_metadata = dict(row.get("metadata", {}).get("client") or {})
        if (
            str(row.get("model_id")) != expected_model
            or str(client_metadata.get("requested_model_id", "")) != expected_model
            or str(client_metadata.get("reported_model_id", "")) != expected_model
        ):
            model_errors.append(
                f"{row.get('agent_id')}:record={row.get('model_id')}:"
                f"requested={client_metadata.get('requested_model_id')}:"
                f"reported={client_metadata.get('reported_model_id')}"
            )
        serialized_request_sha = str(row.get("metadata", {}).get("serialized_request_sha256") or "")
        if (
            client_metadata.get("gold_key_findings") != []
            or len(str(client_metadata.get("request_body_sha256", ""))) != 64
            or serialized_request_sha != str(client_metadata.get("request_body_sha256", ""))
        ):
            request_audit_errors.append(f"{row.get('item_id')}:{row.get('agent_id')}")
        request_semantics = str(client_metadata.get("request_semantics_sha256", ""))
        if len(request_semantics) != 64:
            request_audit_errors.append(f"request_semantics:{row.get('item_id')}:{row.get('agent_id')}")
        item_id = str(row.get("item_id"))
        agent_id = str(row.get("agent_id"))
        request_semantics_by_item.setdefault(item_id, set()).add(request_semantics)
        record_request_semantics_by_combo[(item_id, agent_id)] = request_semantics
        logical_id = str(row.get("logical_call_id", ""))
        if logical_id != str(row.get("cache_key", "")):
            validation_errors.append(f"logical_call_id mismatch:{row.get('cache_key')}")
        logical_ids.append(logical_id)
        canonical_attempt = str(row.get("metadata", {}).get("canonical_attempt_id") or "")
        canonical_attempt_ids.append(canonical_attempt)
        usage_payload = {
            "input_tokens": int(row.get("input_tokens", 0)),
            "input_tokens_details": {
                "text_tokens": int(row.get("input_text_tokens", 0)),
                "image_tokens": int(row.get("input_vision_tokens", 0)),
                "cached_tokens": int(row.get("cached_input_tokens", 0)),
                "cache_write_tokens": int(row.get("cache_write_tokens", 0)),
            },
            "output_tokens": int(row.get("output_tokens", 0)),
            "output_tokens_details": {"reasoning_tokens": int(row.get("reasoning_tokens", 0))},
            "total_tokens": int(row.get("token_usage", 0)),
        }
        usage: TokenUsage | None = None
        try:
            usage = TokenUsage.from_api(usage_payload)
            if usage.total_tokens <= 0:
                raise ValueError("total_tokens=0")
        except (TypeError, ValueError) as exc:
            token_errors.append(f"{row.get('item_id')}:{row.get('agent_id')}:{exc}")
        if float(row.get("cost", -1.0)) < 0.0:
            cost_errors.append(f"negative:{row.get('cache_key')}")
        official = row.get("metadata", {}).get("official_api_equivalent_cost_usd")
        if official is None or abs(float(official) - float(row.get("cost", 0.0))) > 1e-12:
            cost_errors.append(f"official mismatch:{row.get('cache_key')}")
        if pricing is None:
            cost_errors.append("pricing manifest missing")
        elif usage is not None:
            try:
                expected_cost = compute_api_cost(usage, pricing.rule_for(str(row.get("model_id"))))
                if abs(expected_cost - float(row.get("cost", 0.0))) > 1e-12:
                    cost_errors.append(f"recompute mismatch:{row.get('cache_key')}")
            except (KeyError, TypeError, ValueError) as exc:
                cost_errors.append(f"recompute failed:{row.get('cache_key')}:{exc}")
        allocated = row.get("metadata", {}).get("actual_server_allocated_cost_usd")
        if server_hourly_price is None:
            if allocated is not None:
                cost_errors.append(f"unexpected server allocation:{row.get('cache_key')}")
        elif allocated is None or float(allocated) < 0.0:
            cost_errors.append(f"missing server allocation:{row.get('cache_key')}")
        traits = dict(row.get("trait_scores") or {})
        if str(item.get("scoring_mode")) == "analytic_three_dimension":
            if set(traits) != {"content", "organization", "language"} or abs(sum(float(v) for v in traits.values()) - float(row.get("pred_score"))) > 1e-6:
                dress_errors.append(f"{row.get('item_id')}:{row.get('agent_id')}")
        elif traits:
            dress_errors.append(f"non-dress traits:{row.get('item_id')}:{row.get('agent_id')}")
        asset_audit = list(row.get("metadata", {}).get("asset_audit") or [])
        expected_assets = list(item.get("source_assets") or [])
        if len(asset_audit) != len(expected_assets):
            asset_errors.append(f"count:{row.get('item_id')}:{row.get('agent_id')}")
        if expected_assets and int(row.get("input_vision_tokens", 0)) <= 0:
            asset_errors.append(f"vision_tokens:{row.get('item_id')}:{row.get('agent_id')}")
        for expected, observed in zip(expected_assets, asset_audit):
            if expected.get("sha256") != observed.get("source_sha256") or expected.get("mime_type") != observed.get("source_mime_type"):
                asset_errors.append(f"identity:{row.get('item_id')}:{row.get('agent_id')}")
        image_strategy_by_item.setdefault(str(row.get("item_id")), set()).add(
            json.dumps(asset_audit, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )

    check("record_schema_and_range", not validation_errors, str(validation_errors[:10]))
    check("model_identity", not model_errors, str(model_errors[:10]))
    check("dress_trait_sum", not dress_errors, str(dress_errors[:10]))
    check("sas_whole_response", all(item.get("scoring_unit") == "whole_response" for item in items if item.get("dataset") == "sas_bench"), "SAS Item均为whole_response")
    check("asset_audit", not asset_errors, str(asset_errors[:10]))
    check("token_usage", not token_errors, str(token_errors[:10]))
    check("cost_ledger", not cost_errors, str(cost_errors[:10]))
    check("serialized_request_audit", not request_audit_errors, str(request_audit_errors[:10]))
    check("request_semantics_fairness", all(len(values) == 1 for values in request_semantics_by_item.values()), str({key: len(value) for key, value in request_semantics_by_item.items()}))
    check("image_strategy", all(len(values) == 1 for values in image_strategy_by_item.values()), str({key: len(value) for key, value in image_strategy_by_item.items()}))
    check("logical_call_ids", len(set(logical_ids)) == 15 and all(logical_ids), f"unique={len(set(logical_ids))}")
    check("canonical_attempt_ids", len(set(canonical_attempt_ids)) == 15 and all(canonical_attempt_ids), f"unique={len(set(canonical_attempt_ids))}")

    attempt_path = root / "logs" / "call_attempts.jsonl"
    attempts = read_jsonl(attempt_path) if attempt_path.exists() else []
    attempt_ids = [str(row.get("attempt_id", "")) for row in attempts]
    successful_attempts = [row for row in attempts if row.get("status") == "success"]
    attempt_identity_errors = []
    for row in attempts:
        agent_id = str(row.get("agent_id", ""))
        expected_model = EXPECTED_MODELS.get(agent_id)
        reported = row.get("reported_model_id")
        if str(row.get("requested_model_id", "")) != expected_model:
            attempt_identity_errors.append(f"requested:{agent_id}:{row.get('requested_model_id')}")
        if reported is not None and str(reported) != expected_model:
            attempt_identity_errors.append(f"reported:{agent_id}:{reported}")
        if row.get("status") == "success" and str(row.get("pricing_model_id", "")) != expected_model:
            attempt_identity_errors.append(f"pricing:{agent_id}:{row.get('pricing_model_id')}")
        if str(row.get("transport_kind", "")) != transport_kind:
            attempt_identity_errors.append(f"transport:{agent_id}:{row.get('transport_kind')}")
        logical_id = str(row.get("logical_call_id", ""))
        try:
            attempt_number = int(row.get("attempt_number", 0))
        except (TypeError, ValueError):
            attempt_number = 0
        expected_attempt_id = _stable_hash(
            {"logical_call_id": logical_id, "attempt_number": attempt_number}
        )
        if str(row.get("attempt_id", "")) != expected_attempt_id:
            attempt_identity_errors.append(f"attempt_id:{agent_id}:{row.get('attempt_id')}")
    attempt_logical_ids = [str(row.get("logical_call_id", "")) for row in attempts]
    attempt_numbers_by_logical: dict[str, list[int]] = {}
    for row in attempts:
        logical_id = str(row.get("logical_call_id", ""))
        try:
            attempt_number = int(row.get("attempt_number", 0))
        except (TypeError, ValueError):
            attempt_number = 0
        attempt_numbers_by_logical.setdefault(logical_id, []).append(attempt_number)
    attempt_number_errors = {
        logical_id: numbers
        for logical_id, numbers in attempt_numbers_by_logical.items()
        if not logical_id or any(number <= 0 for number in numbers) or len(numbers) != len(set(numbers))
    }
    attempt_cost_errors: list[str] = []
    attempt_statuses = {"success", "retryable_failure", "terminal_failure"}
    canonical_attempt_map = {
        str(row.get("metadata", {}).get("canonical_attempt_id") or ""): row
        for row in records
    }
    for row in attempts:
        try:
            attempt_cost = float(row.get("official_api_equivalent_cost_usd", -1.0))
            if attempt_cost < 0.0:
                raise ValueError("negative")
            usage_row = row.get("usage")
            if usage_row is not None and pricing is not None:
                attempt_usage = TokenUsage.from_api(dict(usage_row))
                expected_attempt_cost = compute_api_cost(
                    attempt_usage,
                    pricing.rule_for(str(row.get("pricing_model_id", ""))),
                )
                if abs(expected_attempt_cost - attempt_cost) > 1e-12:
                    raise ValueError("recompute mismatch")
            if row.get("status") not in attempt_statuses:
                raise ValueError(f"invalid status={row.get('status')}")
            latency_seconds = float(row.get("latency_seconds", -1.0))
            expected_server_cost = compute_server_allocated_cost(
                latency_seconds=latency_seconds,
                server_hourly_price_usd=(
                    None if server_hourly_price is None else float(server_hourly_price)
                ),
            )
            observed_server_cost = row.get("actual_server_allocated_cost_usd")
            if expected_server_cost is None:
                if observed_server_cost is not None:
                    raise ValueError("unexpected server allocation")
            elif observed_server_cost is None or abs(float(observed_server_cost) - expected_server_cost) > 1e-12:
                raise ValueError("server allocation recompute mismatch")
            canonical_record = canonical_attempt_map.get(str(row.get("attempt_id", "")))
            if canonical_record is not None:
                expected_body_sha = str(canonical_record.get("metadata", {}).get("serialized_request_sha256") or "")
                if str(row.get("request_body_sha256", "")) != expected_body_sha:
                    raise ValueError("canonical request_body_sha256 mismatch")
                canonical_server_cost = canonical_record.get("metadata", {}).get(
                    "actual_server_allocated_cost_usd"
                )
                if canonical_server_cost != observed_server_cost:
                    raise ValueError("canonical server allocation mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            attempt_cost_errors.append(f"{row.get('attempt_id')}:{exc}")
    check(
        "attempt_audit",
        len(successful_attempts) == 15
        and len(set(attempt_ids)) == len(attempt_ids)
        and all(attempt_ids)
        and len(attempt_logical_ids) == len(attempts)
        and not attempt_number_errors
        and not attempt_cost_errors
        and not attempt_identity_errors,
        f"attempts={len(attempts)} success={len(successful_attempts)} "
        f"number_errors={list(attempt_number_errors.items())[:3]} "
        f"cost_errors={attempt_cost_errors[:3]} identity_errors={attempt_identity_errors[:5]}",
    )
    canonical_attempt_set = set(canonical_attempt_ids)
    canonical_logical_ids = set(logical_ids)
    successful_attempt_ids = {str(row.get("attempt_id")) for row in successful_attempts}
    successful_logical_ids = {str(row.get("logical_call_id")) for row in successful_attempts}
    check(
        "canonical_attempt_linkage",
        canonical_attempt_set == successful_attempt_ids
        and canonical_logical_ids == successful_logical_ids
        and all(str(row.get("logical_call_id")) in canonical_logical_ids for row in attempts),
        f"canonical_attempts={len(canonical_attempt_set)} canonical_logical={len(canonical_logical_ids)}",
    )

    captured_path = root / "logs" / "captured_chat_requests.jsonl"
    captured = read_jsonl(captured_path) if captured_path.exists() else []
    body_findings: list[str] = []
    captured_linkage_errors: list[str] = []
    captured_body_hashes: list[str] = []
    captured_semantics_by_item: dict[str, set[str]] = {}
    for call in captured:
        body = dict(call.get("body") or {})
        body_findings.extend(find_banned_keys(body))
        captured_body_hashes.append(_stable_hash(body))
        try:
            call_number = int(call.get("call_number", 0))
        except (TypeError, ValueError):
            call_number = 0
        if call_number <= 0:
            captured_linkage_errors.append(f"call_number:{call.get('call_number')}")
        if not str(call.get("url", "")).endswith("/v1/chat/completions"):
            captured_linkage_errors.append(f"url:{call.get('url')}")
        try:
            visible_request = _extract_captured_request(body)
            body_findings.extend(find_banned_keys(visible_request))
            item_id = str(visible_request.get("item_id", ""))
            agent_id = MODEL_TO_AGENT.get(str(body.get("model", "")), "")
            if not item_id or not agent_id:
                raise ValueError("captured request缺少受支持的item/model身份")
            semantics_hash = _stable_hash(
                {key: value for key, value in body.items() if key != "model"}
            )
            captured_semantics_by_item.setdefault(item_id, set()).add(semantics_hash)
            if record_request_semantics_by_combo.get((item_id, agent_id)) != semantics_hash:
                captured_linkage_errors.append(f"semantics:{item_id}:{agent_id}")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            captured_linkage_errors.append(f"parse:{call_number}:{exc}")
    if transport_kind == "fake":
        attempt_body_hashes = [str(row.get("request_body_sha256", "")) for row in attempts]
        body_hash_match = Counter(captured_body_hashes) == Counter(attempt_body_hashes)
        check(
            "captured_request_count",
            len(captured) == len(attempts) and len(captured) >= 15,
            f"captured={len(captured)} attempts={len(attempts)}",
        )
        check(
            "captured_request_linkage",
            not captured_linkage_errors
            and body_hash_match
            and all(len(values) == 1 for values in captured_semantics_by_item.values()),
            f"errors={captured_linkage_errors[:10]} body_hash_match={body_hash_match}",
        )
    else:
        check("captured_request_count", not captured, "真实transport不持久化base64请求正文")
        check("captured_request_linkage", not captured, "真实transport由attempt/canonical hash完成关联")
    check("serialized_gold_isolation", not body_findings, str(body_findings[:10]))

    active_agents = [row for row in run_config.get("agents", {}).values() if not row.get("disabled")]
    prompt_paths = {str(row.get("prompt_path", "")) for row in active_agents}
    generations = [dict(row.get("generation_parameters") or {}) for row in active_agents]
    check("shared_prompt", len(active_agents) == 3 and prompt_paths == {"prompts/selfhosted_v1/scorer.txt"}, str(sorted(prompt_paths)))
    prompts_manifest_path = root / "configs" / "prompts_manifest.json"
    prompts_manifest = (
        json.loads(prompts_manifest_path.read_text(encoding="utf-8"))
        if prompts_manifest_path.exists()
        else {}
    )
    prompt_manifest_agent_ids = {agent_id for agent_id in prompts_manifest if agent_id in EXPECTED_AGENTS}
    snapshot_hashes = {
        str(row.get("prompt_hash", ""))
        for agent_id, row in prompts_manifest.items()
        if agent_id in EXPECTED_AGENTS
    }
    snapshot_files_valid = prompt_manifest_agent_ids == EXPECTED_AGENTS and all(
        (root / str(row.get("snapshot_path", ""))).is_file()
        and len(str(row.get("snapshot_sha256", ""))) == 64
        and file_sha256(root / str(row.get("snapshot_path", ""))) == str(row.get("snapshot_sha256"))
        and str(row.get("snapshot_sha256")) == str(row.get("prompt_hash"))
        for agent_id, row in prompts_manifest.items()
        if agent_id in EXPECTED_AGENTS
    )
    record_prompt_hashes = {str(row.get("prompt_hash", "")) for row in records}
    check(
        "prompt_hash",
        len(record_prompt_hashes) == 1
        and record_prompt_hashes == snapshot_hashes
        and snapshot_files_valid,
        f"records={record_prompt_hashes} snapshots={snapshot_hashes} files_valid={snapshot_files_valid}",
    )
    check("non_thinking", len(generations) == 3 and all(row.get("enable_thinking") is False for row in generations), "enable_thinking=false")
    check("temperature_zero", len(generations) == 3 and all(float(row.get("temperature", -1.0)) == 0.0 for row in generations), "temperature=0.0")
    check("max_output_tokens", len(generations) == 3 and len({int(row.get("max_tokens", -1)) for row in generations}) == 1, str([row.get("max_tokens") for row in generations]))
    schema_hashes = {
        str(row.get("metadata", {}).get("client", {}).get("schema_sha256", ""))
        for row in records
    }
    expected_schema_hash = hashlib.sha256(
        json.dumps(SELFHOSTED_AGENT_RESPONSE_SCHEMA, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    check(
        "schema_hash",
        schema_hashes == {expected_schema_hash},
        f"observed={schema_hashes} expected={expected_schema_hash}",
    )
    if transport_kind == "urllib":
        revisions = [str(row.get("model_revision", "")) for row in active_agents]
        check("model_revisions_frozen", all(value not in {"", "pending_server_freeze"} for value in revisions), str(revisions))

    blocking_failures = [row for row in checks if not row["passed"]]
    is_fake = transport_kind == "fake"
    report = {
        "schema_version": "selfhosted_checkpoint_validation_v1",
        "status": "PASS" if not blocking_failures else "FAIL",
        "run_dir": str(root),
        "transport_kind": transport_kind,
        "formal_eligible": False,
        "checks": checks,
        "blocking_failure_count": len(blocking_failures),
        "canonical_record_count": len(records),
        "attempt_count": len(attempts),
        "captured_request_count": len(captured),
        "operational_retry_overhead_usd": sum(float(row.get("official_api_equivalent_cost_usd", 0.0)) for row in attempts if row.get("status") != "success"),
        "operational_retry_server_overhead_usd": sum(float(row.get("actual_server_allocated_cost_usd") or 0.0) for row in attempts if row.get("status") != "success"),
        "canonical_cost_usd": sum(float(row.get("cost", 0.0)) for row in records if row.get("status") == "success"),
        "unlocks_30_item_pilot": (not blocking_failures) and transport_kind == "urllib",
        "note": "Fake PASS仅证明本地执行契约成立，不解锁30 Item Pilot。" if is_fake else "真实checkpoint全部通过后方可解锁30 Item Pilot。",
    }
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    write_json(reports_dir / "selfhosted_checkpoint_validation.json", report, overwrite=True)
    with (reports_dir / "selfhosted_checkpoint_validation.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "passed", "blocking", "detail"])
        writer.writeheader()
        writer.writerows(checks)
    (reports_dir / "selfhosted_checkpoint_validation.md").write_text(
        "# Self-hosted Checkpoint Validation\n\n"
        f"- status: **{report['status']}**\n"
        f"- transport_kind: `{transport_kind}`\n"
        f"- canonical records: {len(records)}\n"
        f"- attempts: {len(attempts)}\n"
        f"- captured requests: {len(captured)}\n"
        f"- unlocks_30_item_pilot: `{report['unlocks_30_item_pilot']}`\n"
        f"- note: {report['note']}\n\n"
        + "\n".join(f"- [{'x' if row['passed'] else ' '}] {row['name']}: {row['detail']}" for row in checks)
        + "\n",
        encoding="utf-8",
    )
    return report
