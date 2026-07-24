"""schema 与数据完整性校验。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


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

SUCCESS_STATUS = "success"
VALID_AGENT_STATUSES = {SUCCESS_STATUS, "failed", "skipped"}



def require_fields(record: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(field for field in fields if field not in record)
    if missing:
        raise ValueError(f"{label} 缺少必填字段: {missing}")


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
    score_min = float(record["score_min"])
    score_max = float(record["score_max"])
    gold_score = float(record["gold_score"])
    if score_max <= score_min:
        raise ValueError(f"score_max 必须大于 score_min: {record['item_id']}")
    if not score_min <= gold_score <= score_max:
        raise ValueError(f"gold_score 越界: {record['item_id']}")


def validate_paper(record: dict[str, Any], items_by_id: dict[str, dict[str, Any]] | None = None) -> None:
    require_fields(record, PAPER_REQUIRED, "Paper")
    if not record["items"]:
        raise ValueError(f"Paper items 不能为空: {record['paper_id']}")
    budget = record["paper_budget"]
    for key in ("max_cost", "max_latency", "max_agent_calls", "max_a2a_messages"):
        if key not in budget:
            raise ValueError(f"Paper budget 缺少 {key}: {record['paper_id']}")
        if float(budget[key]) < 0:
            raise ValueError(f"Paper budget 不得为负: {record['paper_id']} {key}")
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
    if float(record["cost"]) < 0 or float(record["latency"]) < 0 or int(record["token_usage"]) < 0:
        raise ValueError("AgentOutput cost、latency 和 token_usage 必须非负")
    confidence = float(record["confidence"])
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("AgentOutput confidence 必须位于 [0, 1]")
    required_text = ("run_id", "execution_mode", "model_id", "prompt_version", "prompt_hash", "input_hash", "context_hash", "cache_key", "cache_schema_version")
    for field_name in required_text:
        if not str(record[field_name]).strip():
            raise ValueError(f"AgentOutput {field_name} 不能为空")
    if record["status"] == SUCCESS_STATUS:
        if record["pred_score"] is None:
            raise ValueError("成功 AgentOutput 必须包含 pred_score")
        if not str(record["justification"]).strip():
            raise ValueError("成功 AgentOutput 必须包含 justification")
        score_min = None
        score_max = None
        if item is not None:
            score_min = float(item["score_min"])
            score_max = float(item["score_max"])
        elif "score_min" in record["metadata"] and "score_max" in record["metadata"]:
            score_min = float(record["metadata"]["score_min"])
            score_max = float(record["metadata"]["score_max"])
        if score_min is not None and not score_min <= float(record["pred_score"]) <= float(score_max):
            raise ValueError(f"AgentOutput pred_score 越界: {record['item_id']}")
    elif not str(record.get("error") or "").strip():
        raise ValueError("失败或跳过记录必须包含 error")

    if item is not None:
        expected_split = item.get("metadata", {}).get("split")
        if expected_split and record["split"] != expected_split:
            raise ValueError(f"AgentOutput split 与 item 不一致: {record['item_id']}")
