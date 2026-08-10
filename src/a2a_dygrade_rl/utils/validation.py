"""schema、职责边界与数据完整性校验。"""

from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from typing import Any, Iterable


ITEM_REQUIRED = {
    "item_id",
    "dataset",
    "question_type",
    "subject",
    "prompt",
    "student_answer",
    "reference_answer",
    "rubric",
    "gold_score",
    "score_min",
    "score_max",
    "metadata",
}

PAPER_REQUIRED = {"paper_id", "items", "paper_budget"}

AGENT_OUTPUT_REQUIRED = {
    "item_id",
    "agent_id",
    "run_id",
    "execution_mode",
    "is_fixture",
    "pred_score",
    "confidence",
    "justification",
    "evidence",
    "cost",
    "latency",
    "token_usage",
    "gold_score",
    "split",
    "model_id",
    "prompt_version",
    "prompt_hash",
    "input_hash",
    "context_hash",
    "cache_key",
    "cache_schema_version",
    "status",
    "error",
    "metadata",
}

INTERNAL_ITEM_SPLIT_REQUIRED = {
    "item_id",
    "dataset",
    "prompt_group",
    "leakage_component_id",
    "component_id",
    "component_size",
    "source_split",
    "internal_split",
    "seed",
    "rule_version",
    "assignment_unit",
    "stable_hash",
    "source_paper_ids",
}

INTERNAL_PAPER_MANIFEST_REQUIRED = {
    "paper_id",
    "internal_split",
    "item_id",
    "paper_position",
    "dataset",
    "prompt_group",
    "component_id",
    "strict_quota_id",
    "paper_dataset_mix",
    "seed",
    "rule_version",
    "source_paper_ids",
}

LEFTOVER_REQUIRED = {
    "item_id",
    "dataset",
    "internal_split",
    "prompt_group",
    "component_id",
    "reason",
    "seed",
    "rule_version",
    "source_paper_ids",
}

CALIBRATION_PACKAGE_REQUIRED = {
    "package_id",
    "checkpoint_id",
    "checkpoint_hash",
    "calibration_status",
    "stop_boundary",
    "calibration_failure_reason",
    "boundary_frozen",
    "calibration_split",
    "calibration_no_gradient",
    "calibration_no_replay",
    "calibration_no_checkpoint_ranking",
    "main_method_upgrade_thresholds",
    "quality_protocol_hash",
    "internal_manifest_hash",
    "quality_reference_manifest_hash",
    "budget_manifest_hash",
    "support_manifest_hash",
}

POLICY_PACKAGE_REQUIRED = {
    "package_id",
    "checkpoint_id",
    "checkpoint_hash",
    "calibration_package_hash",
    "package_role",
    "calibration_status",
    "stop_boundary",
    "boundary_frozen",
    "dev_boundary_updates",
    "quality_protocol_hash",
    "internal_manifest_hash",
    "quality_reference_manifest_hash",
    "budget_manifest_hash",
    "support_manifest_hash",
}

HASH_FIELDS = {
    "quality_protocol_hash",
    "internal_manifest_hash",
    "quality_reference_manifest_hash",
    "budget_manifest_hash",
    "support_manifest_hash",
}

SUCCESS_STATUS = "success"
VALID_AGENT_STATUSES = {SUCCESS_STATUS, "failed", "skipped"}
EXECUTION_MODES = {"fixture_smoke", "real_pilot", "formal_experiment"}
EXECUTION_MODE_PREFIXES = {
    "fixture_smoke": "fixture_smoke_",
    "real_pilot": "real_pilot_",
    "formal_experiment": "formal_agent_cache_",
}
INTERNAL_SPLITS = {"train_fit", "train_calibration"}
PACKAGE_ROLES = {"router_candidate", "reference", "baseline", "ablation"}


def require_fields(record: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(field for field in fields if field not in record)
    if missing:
        raise ValueError(f"{label} 缺少必填字段: {missing}")


def _require_nonempty_text(record: dict[str, Any], fields: Iterable[str], label: str) -> None:
    for name in fields:
        if not str(record.get(name, "")).strip():
            raise ValueError(f"{label} {name} 不能为空")


def _require_finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} 必须是数值") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} 必须是有限数值")
    return number


def _require_bool(record: dict[str, Any], field: str, label: str) -> bool:
    value = record.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{label} {field} 必须是显式布尔值")
    return value


def validate_item(record: dict[str, Any]) -> None:
    require_fields(record, ITEM_REQUIRED, "Item")
    if not str(record["item_id"]).strip():
        raise ValueError("Item item_id 不能为空")
    if not str(record["prompt"]).strip():
        raise ValueError(f"Item prompt 不能为空: {record['item_id']}")
    if not str(record["student_answer"]).strip():
        raise ValueError(f"Item student_answer 不能为空: {record['item_id']}")
    if not str(record.get("rubric", "")).strip() and not str(record.get("reference_answer", "")).strip():
        raise ValueError(f"Item 至少需要 rubric 或 reference_answer: {record['item_id']}")
    score_min = _require_finite(record["score_min"], "score_min")
    score_max = _require_finite(record["score_max"], "score_max")
    gold_score = _require_finite(record["gold_score"], "gold_score")
    if score_max <= score_min:
        raise ValueError(f"score_max 必须大于 score_min: {record['item_id']}")
    if not score_min <= gold_score <= score_max:
        raise ValueError(f"gold_score 越界: {record['item_id']}")


def canonical_budget(budget: dict[str, Any]) -> dict[str, float | int]:
    """把 legacy 预算键转换为正式四维键。"""

    elapsed = budget.get("max_elapsed_time", budget.get("max_latency"))
    exchanges = budget.get("max_a2a_exchanges", budget.get("max_a2a_messages"))
    required_values = {
        "max_cost": budget.get("max_cost"),
        "max_elapsed_time": elapsed,
        "max_agent_calls": budget.get("max_agent_calls"),
        "max_a2a_exchanges": exchanges,
    }
    missing = [name for name, value in required_values.items() if value is None]
    if missing:
        raise ValueError(f"Paper budget 缺少字段: {missing}")
    canonical: dict[str, float | int] = {
        "max_cost": _require_finite(required_values["max_cost"], "max_cost"),
        "max_elapsed_time": _require_finite(required_values["max_elapsed_time"], "max_elapsed_time"),
        "max_agent_calls": int(required_values["max_agent_calls"]),
        "max_a2a_exchanges": int(required_values["max_a2a_exchanges"]),
    }
    for key, value in canonical.items():
        if float(value) < 0:
            raise ValueError(f"Paper budget 不得为负: {key}")
    return canonical


def validate_paper(
    record: dict[str, Any],
    items_by_id: dict[str, dict[str, Any]] | None = None,
    *,
    required_item_count: int | None = None,
) -> None:
    require_fields(record, PAPER_REQUIRED, "Paper")
    if not str(record.get("paper_id", "")).strip():
        raise ValueError("Paper paper_id 不能为空")
    if not record["items"]:
        raise ValueError(f"Paper items 不能为空: {record['paper_id']}")
    if len(record["items"]) != len(set(record["items"])):
        raise ValueError(f"Paper 内部存在重复 Item: {record['paper_id']}")
    if required_item_count is not None and len(record["items"]) != required_item_count:
        raise ValueError(f"Paper 必须固定包含 {required_item_count} 题: {record['paper_id']}")
    canonical_budget(record["paper_budget"])
    if items_by_id is not None:
        missing = [item_id for item_id in record["items"] if item_id not in items_by_id]
        if missing:
            raise ValueError(f"Paper 引用不存在 item: {record['paper_id']} {missing}")


def validate_no_split_leakage(items: list[dict[str, Any]]) -> None:
    item_splits: dict[str, set[str]] = defaultdict(set)
    prompt_splits: dict[str, set[str]] = defaultdict(set)
    for item in items:
        split = item.get("metadata", {}).get("split")
        prompt_group = item.get("metadata", {}).get("prompt_group") or item.get("metadata", {}).get("prompt_id")
        if not split:
            raise ValueError(f"Item 缺少 split metadata: {item.get('item_id')}")
        item_splits[str(item["item_id"])].add(str(split))
        prompt_splits[str(prompt_group or item["prompt"])].add(str(split))
    leaked_items = {key: value for key, value in item_splits.items() if len(value) > 1}
    leaked_prompts = {key: value for key, value in prompt_splits.items() if "test" in value and len(value) > 1}
    if leaked_items:
        raise ValueError(f"发现 item 跨 split 泄漏: {leaked_items}")
    if leaked_prompts:
        raise ValueError(f"发现 test prompt 跨 split 泄漏: {leaked_prompts}")


def validate_agent_output(
    record: dict[str, Any],
    item: dict[str, Any] | None = None,
    allowed_agents: set[str] | None = None,
) -> None:
    require_fields(record, AGENT_OUTPUT_REQUIRED, "AgentOutput")
    if not str(record["item_id"]).strip():
        raise ValueError("AgentOutput item_id 不能为空")
    if allowed_agents is not None and record["agent_id"] not in allowed_agents:
        raise ValueError(f"未注册的 Agent: {record['agent_id']}")
    if record["status"] not in VALID_AGENT_STATUSES:
        raise ValueError(f"非法 AgentOutput status: {record['status']}")
    execution_mode = str(record["execution_mode"])
    if execution_mode not in EXECUTION_MODES:
        raise ValueError(f"非法 AgentOutput execution_mode: {execution_mode}")
    is_fixture = _require_bool(record, "is_fixture", "AgentOutput")
    if is_fixture != (execution_mode == "fixture_smoke"):
        raise ValueError("AgentOutput is_fixture 与 execution_mode 不一致")
    run_id = str(record["run_id"])
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id) is None:
        raise ValueError("AgentOutput run_id 必须是单一安全路径组件")
    expected_prefix = EXECUTION_MODE_PREFIXES[execution_mode]
    if not run_id.startswith(expected_prefix):
        raise ValueError(f"AgentOutput run_id 必须使用前缀 {expected_prefix}")
    cost = _require_finite(record["cost"], "AgentOutput cost")
    latency = _require_finite(record["latency"], "AgentOutput latency")
    token_usage = record["token_usage"]
    if cost < 0.0 or latency < 0.0:
        raise ValueError("AgentOutput cost 与 latency 必须为非负有限数值")
    if not isinstance(token_usage, int) or isinstance(token_usage, bool) or token_usage < 0:
        raise ValueError("AgentOutput token_usage 必须为非负整数")
    detailed_token_fields = (
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
    )

    if any(field in record for field in detailed_token_fields):
        values: dict[str, int] = {}
        for field in detailed_token_fields:
            value = record.get(field, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"AgentOutput {field} 必须为非负整数")
            values[field] = value
        if values["cached_input_tokens"] > values["input_tokens"]:
            raise ValueError("AgentOutput cached_input_tokens 不得大于 input_tokens")
        if values["reasoning_tokens"] > values["output_tokens"]:
            raise ValueError("AgentOutput reasoning_tokens 不得大于 output_tokens")
        if token_usage != values["input_tokens"] + values["output_tokens"]:
            raise ValueError("AgentOutput token_usage 必须等于 input_tokens + output_tokens")
    confidence = _require_finite(record["confidence"], "AgentOutput confidence")
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("AgentOutput confidence 必须位于 [0, 1]")
    _require_finite(record["gold_score"], "AgentOutput gold_score")
    required_text = (
        "run_id",
        "execution_mode",
        "model_id",
        "prompt_version",
        "prompt_hash",
        "input_hash",
        "context_hash",
        "cache_key",
        "cache_schema_version",
    )
    _require_nonempty_text(record, required_text, "AgentOutput")
    _validate_sha256_fields(
        record,
        ("prompt_hash", "input_hash", "context_hash", "cache_key"),
        "AgentOutput",
    )
    if record["status"] == SUCCESS_STATUS:
        if record["pred_score"] is None:
            raise ValueError("成功 AgentOutput 必须包含 pred_score")
        prediction = _require_finite(record["pred_score"], "AgentOutput pred_score")
        if not str(record["justification"]).strip():
            raise ValueError("成功 AgentOutput 必须包含 justification")
        score_min = None
        score_max = None
        if item is not None:
            score_min = _require_finite(item["score_min"], "Item score_min")
            score_max = _require_finite(item["score_max"], "Item score_max")
        elif "score_min" in record["metadata"] and "score_max" in record["metadata"]:
            score_min = _require_finite(record["metadata"]["score_min"], "metadata.score_min")
            score_max = _require_finite(record["metadata"]["score_max"], "metadata.score_max")
        if score_min is not None and not score_min <= prediction <= float(score_max):
            raise ValueError(f"AgentOutput pred_score 越界: {record['item_id']}")
    elif not str(record.get("error") or "").strip():
        raise ValueError("失败或跳过记录必须包含 error")

    if item is not None:
        expected_split = item.get("metadata", {}).get("split")
        if expected_split and record["split"] != expected_split:
            raise ValueError(f"AgentOutput split 与 item 不一致: {record['item_id']}")

def validate_internal_item_split_record(record: dict[str, Any]) -> None:
    require_fields(record, INTERNAL_ITEM_SPLIT_REQUIRED, "InternalItemSplitManifest")
    _require_nonempty_text(
        record,
        ("item_id", "dataset", "prompt_group", "component_id", "source_split", "internal_split", "rule_version", "stable_hash"),
        "InternalItemSplitManifest",
    )
    if record["source_split"] != "train":
        raise ValueError("内部拆分仅允许外部 train Item")
    if record["internal_split"] not in INTERNAL_SPLITS:
        raise ValueError(f"非法 internal_split: {record['internal_split']}")
    if record["assignment_unit"] != "item_component":
        raise ValueError("禁止直接拆分旧 Paper；assignment_unit 必须为 item_component")
    if int(record["component_size"]) <= 0:
        raise ValueError("component_size 必须为正数")


def validate_internal_item_split_manifest(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("internal item split manifest 不能为空")
    seen_items: set[str] = set()
    component_splits: dict[str, set[str]] = defaultdict(set)
    prompt_splits: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in rows:
        validate_internal_item_split_record(record)
        item_id = str(record["item_id"])
        if item_id in seen_items:
            raise ValueError(f"internal manifest 出现重复 item_id: {item_id}")
        seen_items.add(item_id)
        component_splits[str(record["component_id"])].add(str(record["internal_split"]))
        prompt_splits[(str(record["dataset"]), str(record["prompt_group"]))].add(str(record["internal_split"]))
    component_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in rows:
        component_rows[str(record["component_id"])].append(record)
    inconsistent_components: list[str] = []
    for component_id, records in component_rows.items():
        declared_sizes = {int(record["component_size"]) for record in records}
        stable_hashes = {str(record["stable_hash"]) for record in records}
        datasets = {str(record["dataset"]) for record in records}
        item_ids = sorted(str(record["item_id"]) for record in records)
        expected_hash = hashlib.sha256(
            "\x1f".join(["internal_component_v1.4", *item_ids]).encode("utf-8")
        ).hexdigest()
        if (
            declared_sizes != {len(records)}
            or len(stable_hashes) != 1
            or len(datasets) != 1
            or stable_hashes != {expected_hash}
            or component_id != f"ic_{expected_hash[:20]}"
        ):
            inconsistent_components.append(component_id)
    leaked_components = sorted(key for key, splits in component_splits.items() if len(splits) > 1)
    leaked_prompts = sorted(key for key, splits in prompt_splits.items() if len(splits) > 1)
    if inconsistent_components:
        raise ValueError(f"内部 component manifest 大小/hash/dataset 不一致: {inconsistent_components[:10]}")
    if leaked_components:
        raise ValueError(f"内部 component 跨 split 泄漏: {leaked_components[:10]}")
    if leaked_prompts:
        raise ValueError(f"内部 prompt group 跨 split 泄漏: {leaked_prompts[:10]}")



def validate_internal_paper_manifest_record(record: dict[str, Any]) -> None:
    require_fields(record, INTERNAL_PAPER_MANIFEST_REQUIRED, "InternalPaperManifest")
    _require_nonempty_text(
        record,
        ("paper_id", "internal_split", "item_id", "dataset", "prompt_group", "component_id", "strict_quota_id", "rule_version"),
        "InternalPaperManifest",
    )
    if record["internal_split"] not in INTERNAL_SPLITS:
        raise ValueError(f"非法 internal_split: {record['internal_split']}")
    if re.fullmatch(r"paper_train_\d+", str(record["paper_id"])):
        raise ValueError("内部 Paper 不得继承旧 paper_train_<index> ID")
    if int(record["paper_position"]) < 0:
        raise ValueError("paper_position 不得为负")


def validate_leftover_record(record: dict[str, Any]) -> None:
    require_fields(record, LEFTOVER_REQUIRED, "LeftoverRecord")
    _require_nonempty_text(record, ("item_id", "dataset", "internal_split", "component_id", "reason"), "LeftoverRecord")
    if record["internal_split"] not in INTERNAL_SPLITS:
        raise ValueError(f"非法 internal_split: {record['internal_split']}")


def _validate_sha256_fields(record: dict[str, Any], fields: Iterable[str], label: str) -> None:
    for field_name in fields:
        value = str(record.get(field_name, "")).strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"{label} {field_name} 必须为64位 SHA-256 hex")


def validate_manifest_hashes(record: dict[str, Any], *, expected_protocol_hash: str | None = None) -> None:
    _validate_sha256_fields(record, HASH_FIELDS, "Package")
    if expected_protocol_hash is not None and record["quality_protocol_hash"] != expected_protocol_hash:
        raise ValueError("quality_protocol_hash 与冻结协议不一致")



def validate_calibration_package(record: dict[str, Any], *, expected_protocol_hash: str | None = None) -> None:
    require_fields(record, CALIBRATION_PACKAGE_REQUIRED, "CalibrationPackage")
    _require_nonempty_text(record, ("package_id", "checkpoint_id", "checkpoint_hash"), "CalibrationPackage")
    _validate_sha256_fields(record, ("checkpoint_hash",), "CalibrationPackage")
    validate_manifest_hashes(record, expected_protocol_hash=expected_protocol_hash)
    if record["calibration_split"] != "train_calibration":
        raise ValueError("CalibrationPackage 只能来自 train_calibration")
    if _require_bool(record, "calibration_no_gradient", "CalibrationPackage") is not True:
        raise ValueError("calibration 禁止梯度训练")
    if _require_bool(record, "calibration_no_replay", "CalibrationPackage") is not True:
        raise ValueError("calibration 禁止 replay 消费或写入")
    if _require_bool(record, "calibration_no_checkpoint_ranking", "CalibrationPackage") is not True:
        raise ValueError("calibration 禁止跨 checkpoint 排名")
    prohibited_selection_fields = {
        "selected_final_router",
        "selected_checkpoint_id",
        "dev_rank",
        "checkpoint_rank",
        "resource_champion",
    }
    present_prohibited = sorted(prohibited_selection_fields & set(record))
    if present_prohibited:
        raise ValueError(f"CalibrationPackage schema 禁止最终选择或跨 checkpoint 排名字段: {present_prohibited}")
    if record.get("main_method_upgrade_thresholds"):
        raise ValueError("主方法 calibration 只允许 STOP 边界，不允许升级阈值")
    if record.get("coverage") is not None:
        coverage = _require_finite(record["coverage"], "coverage")
        if not 0.0 <= coverage <= 1.0:
            raise ValueError("calibration coverage 必须位于 [0,1]")
    status = str(record["calibration_status"])
    if status not in {"success", "failure"}:
        raise ValueError(f"非法 calibration_status: {status}")
    if status == "success":
        if record["stop_boundary"] is None:
            raise ValueError("calibration success 必须包含 stop_boundary")
        boundary = _require_finite(record["stop_boundary"], "stop_boundary")
        if not 0.0 <= boundary <= 1.0:
            raise ValueError("stop_boundary 必须位于 [0,1]")
        if _require_bool(record, "boundary_frozen", "CalibrationPackage") is not True:
            raise ValueError("进入 Dev 前 STOP 边界必须冻结")
        if str(record.get("calibration_failure_reason", "")).strip():
            raise ValueError("calibration success 不应包含 failure reason")
    else:
        if record["stop_boundary"] is not None:
            raise ValueError("calibration failure 不得伪造 stop_boundary")
        if _require_bool(record, "boundary_frozen", "CalibrationPackage") is not False:
            raise ValueError("calibration failure 的 boundary_frozen 必须为 false")
        if not str(record.get("calibration_failure_reason", "")).strip():
            raise ValueError("calibration failure 必须记录失败原因")


def validate_calibration_packages(records: list[dict[str, Any]], *, expected_protocol_hash: str | None = None) -> None:
    seen_checkpoints: set[str] = set()
    for record in records:
        validate_calibration_package(record, expected_protocol_hash=expected_protocol_hash)
        checkpoint_id = str(record["checkpoint_id"])
        if checkpoint_id in seen_checkpoints:
            raise ValueError(f"CalibrationPackage 重复 checkpoint: {checkpoint_id}")
        seen_checkpoints.add(checkpoint_id)


def validate_policy_package(record: dict[str, Any], *, expected_protocol_hash: str | None = None) -> None:
    require_fields(record, POLICY_PACKAGE_REQUIRED, "PolicyPackage")
    _require_nonempty_text(
        record,
        ("package_id", "checkpoint_id", "checkpoint_hash", "calibration_package_hash", "package_role"),
        "PolicyPackage",
    )
    _validate_sha256_fields(record, ("checkpoint_hash", "calibration_package_hash"), "PolicyPackage")
    validate_manifest_hashes(record, expected_protocol_hash=expected_protocol_hash)
    if record["package_role"] not in PACKAGE_ROLES:
        raise ValueError(f"非法 package_role: {record['package_role']}")
    if record["calibration_status"] != "success":
        raise ValueError("Dev selector 只接受 calibration success Package")
    if record["stop_boundary"] is None or _require_bool(record, "boundary_frozen", "PolicyPackage") is not True:
        raise ValueError("Dev selector 拒绝未冻结 STOP 边界的 Package")
    boundary = _require_finite(record["stop_boundary"], "stop_boundary")
    if not 0.0 <= boundary <= 1.0:
        raise ValueError("stop_boundary 必须位于 [0,1]")
    updates = record["dev_boundary_updates"]
    if not isinstance(updates, int) or isinstance(updates, bool) or updates != 0:
        raise ValueError("Dev boundary immutable：边界修改次数必须为0的整数")


def validate_quality_metric_protocol(protocol: dict[str, Any]) -> None:
    if float(protocol.get("gate_error_invalid_value", -1)) != 1.0:
        raise ValueError("Gate Error 非法/未完成固定值必须为1")
    if float(protocol.get("severe_threshold", -1)) != 0.25 or protocol.get("severe_operator") != ">":
        raise ValueError("Severe 协议必须固定为 Gate Error > 0.25")
    if float(protocol.get("extreme_threshold", -1)) != 0.50 or protocol.get("extreme_operator") != ">=":
        raise ValueError("Extreme 协议必须固定为 Gate Error >= 0.50")
    if tuple(protocol.get("qwk_fixed_labels", ())) != tuple(range(11)):
        raise ValueError("正式 QWK labels 必须固定为0..10")
    if int(protocol.get("bootstrap_replicates", 0)) != 5000:
        raise ValueError("正式 Bootstrap 必须为5000次")
    if protocol.get("bootstrap_unit") != "paper" or not bool(protocol.get("bootstrap_paired")):
        raise ValueError("正式 Bootstrap 必须为 Paper 级配对")
    if float(protocol.get("bootstrap_confidence_level", 0)) != 0.95:
        raise ValueError("正式 Bootstrap 必须为单侧95%")
    if float(protocol.get("noninferiority_margin", 1)) != 0.0:
        raise ValueError("正式非劣效边界必须为0")
    if int(protocol.get("bootstrap_seed", 0)) != 20260729:
        raise ValueError("正式 Bootstrap seed 必须为20260729")


def validate_qwk_readiness_record(record: dict[str, Any]) -> None:
    required = {
        "dataset",
        "valid_completed_n",
        "gold_nonempty_bin_count",
        "expected_weighted_disagreement",
        "fixed_labels",
        "qwk_defined",
        "qwk",
        "readiness_failure_reason",
    }
    require_fields(record, required, "QWKReadinessRecord")
    if tuple(record["fixed_labels"]) != tuple(range(11)):
        raise ValueError("QWKReadinessRecord labels 必须固定为0..10")
    qwk_defined = _require_bool(record, "qwk_defined", "QWKReadinessRecord")
    if qwk_defined and record["qwk"] is None:
        raise ValueError("qwk_defined=True 时必须包含 QWK")
    if not qwk_defined and not str(record["readiness_failure_reason"]).strip():
        raise ValueError("QWK readiness failure 必须记录原因")


def validate_paired_bootstrap_gate_result(record: dict[str, Any]) -> None:
    point_and_bound_fields = {
        "point_max_dataset_delta_severe",
        "ucb95_max_dataset_delta_severe",
        "point_max_dataset_delta_unsafe_stop",
        "ucb95_max_dataset_delta_unsafe_stop",
        "point_delta_macro_nmae",
        "ucb95_delta_macro_nmae",
        "point_delta_macro_qwk",
        "lcb95_delta_macro_qwk",
    }
    required = {
        "candidate_id",
        "comparator_id",
        "budget_id",
        "comparison_kind",
        "unit",
        "paired",
        "replicates",
        "confidence_level",
        "noninferiority_margin",
        "seed",
        "pass_max_dataset_delta_severe",
        "pass_max_dataset_delta_unsafe_stop",
        "pass_delta_macro_nmae",
        "pass_delta_macro_qwk",
        "quality_feasible",
        "status",
        "failure_reason",
        "quality_protocol_hash",
        "resample_index_digest",
        *point_and_bound_fields,
    }
    require_fields(record, required, "PairedBootstrapGateResult")
    _require_nonempty_text(
        record,
        ("candidate_id", "comparator_id", "budget_id", "comparison_kind", "resample_index_digest"),
        "PairedBootstrapGateResult",
    )
    if record["comparison_kind"] not in {"fixed_reference", "quality_champion", "candidate_to_champion"}:
        raise ValueError(f"非法 comparison_kind: {record['comparison_kind']}")
    _validate_sha256_fields(record, ("resample_index_digest",), "PairedBootstrapGateResult")
    if not isinstance(record["paired"], bool) or record["paired"] is not True or record["unit"] != "paper":
        raise ValueError("PairedBootstrapGateResult 必须使用显式布尔 paired=true 的 Paper 级配对")
    if not isinstance(record["replicates"], int) or isinstance(record["replicates"], bool) or record["replicates"] <= 0:
        raise ValueError("PairedBootstrapGateResult replicates 必须为正整数")
    confidence = _require_finite(record["confidence_level"], "confidence_level")
    if not 0.5 < confidence < 1.0:
        raise ValueError("PairedBootstrapGateResult confidence_level 必须位于 (0.5,1)")
    margin = _require_finite(record["noninferiority_margin"], "noninferiority_margin")
    if margin < 0.0:
        raise ValueError("PairedBootstrapGateResult noninferiority_margin 必须非负")
    if not isinstance(record["seed"], int) or isinstance(record["seed"], bool):
        raise ValueError("PairedBootstrapGateResult seed 必须为整数")
    _validate_sha256_fields(record, ("quality_protocol_hash",), "PairedBootstrapGateResult")

    pass_fields = (
        "pass_max_dataset_delta_severe",
        "pass_max_dataset_delta_unsafe_stop",
        "pass_delta_macro_nmae",
        "pass_delta_macro_qwk",
    )
    for field in (*pass_fields, "quality_feasible"):
        if not isinstance(record[field], bool):
            raise ValueError(f"PairedBootstrapGateResult {field} 必须是显式布尔值")

    metric_evidence = (
        ("point_max_dataset_delta_severe", "ucb95_max_dataset_delta_severe", "pass_max_dataset_delta_severe", "upper"),
        ("point_max_dataset_delta_unsafe_stop", "ucb95_max_dataset_delta_unsafe_stop", "pass_max_dataset_delta_unsafe_stop", "upper"),
        ("point_delta_macro_nmae", "ucb95_delta_macro_nmae", "pass_delta_macro_nmae", "upper"),
        ("point_delta_macro_qwk", "lcb95_delta_macro_qwk", "pass_delta_macro_qwk", "lower"),
    )
    for point_field, bound_field, pass_field, direction in metric_evidence:
        point = record[point_field]
        bound = record[bound_field]
        passed = record[pass_field]
        if point is not None:
            _require_finite(point, point_field)
        if bound is not None:
            bound_value = _require_finite(bound, bound_field)
            expected_pass = bound_value <= margin if direction == "upper" else bound_value >= -margin
        else:
            expected_pass = False
        if bound is not None and point is None:
            raise ValueError(f"PairedBootstrapGateResult {bound_field} 存在时必须包含 {point_field}")
        if passed != expected_pass:
            raise ValueError(f"PairedBootstrapGateResult {pass_field} 与置信边界证据不一致")

    feasible = record["quality_feasible"]
    all_pass = all(record[name] for name in pass_fields)
    if feasible != all_pass:
        raise ValueError("quality_feasible 必须与四项 pass flag 严格一致")
    allowed_statuses = {
        "quality_noninferiority_pass",
        "quality_noninferiority_inconclusive",
        "quality_inferior",
    }
    if record["status"] not in allowed_statuses:
        raise ValueError(f"非法 Gate status: {record['status']}")
    if feasible:
        if record["status"] != "quality_noninferiority_pass":
            raise ValueError("quality_feasible=true 时 status 必须是 quality_noninferiority_pass")
        if str(record.get("failure_reason", "")).strip():
            raise ValueError("通过的 Gate 不得包含 failure_reason")
    else:
        if record["status"] == "quality_noninferiority_pass":
            raise ValueError("失败 Gate 不得标记 quality_noninferiority_pass")
        if not str(record.get("failure_reason", "")).strip():
            raise ValueError("失败或不确定 Gate 必须记录 failure_reason")



