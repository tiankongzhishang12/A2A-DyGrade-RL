"""自托管 Pilot 的本地/服务器运行编排。"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.agents.cache import run_agent_cache
from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_jsonl, read_yaml, write_json, write_yaml


CHECKPOINT_AGENT_IDS = ["CheapAgent", "MidAgent", "StrongAgent"]


def run_selfhosted_checkpoint_cache(
    *,
    config_path: str | Path,
    items_path: str | Path,
    internal_item_manifest_path: str | Path,
    run_id: str,
    transport_kind: str,
    resume: bool = False,
    output_root: str | Path = "outputs/runs",
    server_approved: bool = False,
    agents: list[str] | None = None,
) -> dict[str, Any]:
    fixture = transport_kind == "fake"
    if fixture:
        if re.fullmatch(r"fixture_smoke_selfhosted_ministral3_[A-Za-z0-9._-]+", run_id) is None:
            raise ValueError("Fake run_id 必须使用 fixture_smoke_selfhosted_ministral3_ 前缀")
        execution_mode = "fixture_smoke"
    elif transport_kind == "urllib":
        if re.fullmatch(r"real_pilot_selfhosted_ministral3_[A-Za-z0-9._-]+", run_id) is None:
            raise ValueError("真实 run_id 必须使用 real_pilot_selfhosted_ministral3_ 前缀")
        if not server_approved:
            raise PermissionError("真实服务器运行必须显式传入 server_approved")
        execution_mode = "real_pilot"
    else:
        raise ValueError(f"不支持的 transport_kind: {transport_kind}")

    selected_agent_ids = list(agents or CHECKPOINT_AGENT_IDS)
    if not selected_agent_ids or len(selected_agent_ids) != len(set(selected_agent_ids)):
        raise ValueError("agents必须是非空且不重复的列表")
    unknown_agents = set(selected_agent_ids) - set(CHECKPOINT_AGENT_IDS)
    if unknown_agents:
        raise ValueError(f"five_item checkpoint只允许Cheap/Mid/Strong: {sorted(unknown_agents)}")

    config = read_yaml(config_path)
    if str(config.get("checkpoint", {}).get("stage")) != "five_item":
        raise ValueError("本入口只允许 five_item checkpoint 配置")
    if int(config.get("checkpoint", {}).get("expected_canonical_calls", 0)) != 15:
        raise ValueError("five_item checkpoint 必须固定15条canonical调用")
    items = read_jsonl(items_path)
    if len(items) != 5:
        raise ValueError("five_item checkpoint 输入必须恰好5个Item")
    preparation_run_dir = Path(items_path).resolve().parents[2]
    checkpoint_manifest_path = preparation_run_dir / "configs" / "selfhosted_checkpoint_manifest.json"
    if not checkpoint_manifest_path.is_file():
        raise ValueError("five_item checkpoint 缺少冻结的selfhosted_checkpoint_manifest.json")
    checkpoint_manifest = json.loads(checkpoint_manifest_path.read_text(encoding="utf-8"))
    if (
        checkpoint_manifest.get("semantic_readiness_status") != "PASS"
        or int(checkpoint_manifest.get("item_count", 0)) != 5
        or int(checkpoint_manifest.get("expected_canonical_calls", 0)) != 15
        or checkpoint_manifest.get("formal_eligible") is not False
        or checkpoint_manifest.get("outputs", {}).get("items_sha256") != file_sha256(items_path)
        or checkpoint_manifest.get("outputs", {}).get("internal_manifest_sha256") != file_sha256(internal_item_manifest_path)
    ):
        raise ValueError("five_item checkpoint 输入与冻结manifest不一致")
    if transport_kind == "urllib" and bool(config.get("local_preparation_only", False)):
        raise PermissionError("当前配置仍为 local_preparation_only，禁止真实服务器调用")
    if transport_kind == "urllib":
        top_prepared = Path(str(config.get("prepared_root", ""))).resolve()
        provider_prepared = Path(str(config.get("provider", {}).get("prepared_root", ""))).resolve()
        if top_prepared != provider_prepared:
            raise ValueError("真实服务器配置的顶层 prepared_root 与 provider.prepared_root 必须一致")
        if not provider_prepared.is_dir():
            raise ValueError(f"真实服务器 prepared_root 不存在或不是目录: {provider_prepared}")

    run_dir = Path(output_root) / run_id
    config_dir = ensure_dir(run_dir / "configs")
    logs_dir = ensure_dir(run_dir / "logs")
    runtime = copy.deepcopy(config)
    runtime["local_preparation_only"] = fixture
    runtime["formal_eligible"] = False
    provider = runtime.setdefault("provider", {})
    provider["transport"] = transport_kind
    provider["attempt_log_path"] = str(logs_dir / "call_attempts.jsonl")
    provider["captured_request_log_path"] = str(logs_dir / "captured_chat_requests.jsonl") if fixture else ""
    runtime_path = config_dir / "selfhosted_runtime.yaml"
    if runtime_path.exists():
        if read_yaml(runtime_path) != runtime:
            raise ValueError("Resume runtime配置与已冻结快照不一致")
    else:
        write_yaml(runtime_path, runtime, overwrite=False)

    if fixture:
        write_json(
            config_dir / "fixture_smoke_run_manifest.json",
            {
                "run_id": run_id,
                "execution_mode": "fixture_smoke",
                "formal_eligible": False,
                "transport_kind": "fake",
                "approved_agent_ids": CHECKPOINT_AGENT_IDS,
                "online_agent_calls": 0,
                "model_downloads": 0,
                "dependency_installs": 0,
                "server_rental_actions": 0,
            },
            overwrite=True,
        )
    else:
        pilot_manifest_path = config_dir / "pilot_sample_manifest.json"
        if not pilot_manifest_path.exists():
            write_json(
                pilot_manifest_path,
                {
                    "run_id": run_id,
                    "execution_mode": "real_pilot",
                    "formal_eligible": False,
                    "transport_kind": "urllib",
                    "split": "train_fit",
                    "item_count": len(items),
                    "selected_agent_ids": CHECKPOINT_AGENT_IDS,
                    "checkpoint_manifest_sha256": file_sha256(checkpoint_manifest_path),
                    "online_agent_calls_before_run": 0,
                },
                overwrite=False,
            )

    result = run_agent_cache(
        config_path=runtime_path,
        items_path=items_path,
        split="train_fit",
        run_id=run_id,
        execution_mode=execution_mode,
        seed=int(config.get("checkpoint", {}).get("selection_seed", 20260812)),
        agents=selected_agent_ids,
        resume=resume,
        final_evaluation=False,
        output_root=output_root,
        internal_item_manifest_path=internal_item_manifest_path,
        checkpoint_item_limit=5,
        concurrency=1,
        manifest_agent_ids=CHECKPOINT_AGENT_IDS,
    )
    return {
        **result,
        "transport_kind": transport_kind,
        "selected_agent_ids": selected_agent_ids,
        "runtime_config_path": str(runtime_path),
        "attempt_log_path": str(logs_dir / "call_attempts.jsonl"),
        "captured_request_log_path": str(logs_dir / "captured_chat_requests.jsonl") if fixture else None,
    }
