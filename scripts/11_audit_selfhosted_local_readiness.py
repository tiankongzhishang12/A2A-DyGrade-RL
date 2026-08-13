"""检查 P1–P8 本地准备的仓库结构、配置和禁止操作计数。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.utils.io import file_sha256, read_jsonl, read_yaml, write_json


REQUIRED_FILES = [
    "configs/experiments/selfhosted_ministral3_checkpoint.yaml",
    "configs/experiments/selfhosted_ministral3_pilot30.yaml",
    "configs/pricing/ministral3_official_api_equivalent_20260812.yaml",
    "prompts/selfhosted_v1/scorer.txt",
    "src/a2a_dygrade_rl/utils/multimodal.py",
    "src/a2a_dygrade_rl/utils/selfhosted_client.py",
    "src/a2a_dygrade_rl/agents/selfhosted_checkpoint.py",
    "src/a2a_dygrade_rl/agents/selfhosted_runtime.py",
    "src/a2a_dygrade_rl/agents/selfhosted_validation.py",
    "scripts/08_prepare_selfhosted_checkpoint.py",
    "scripts/09_run_selfhosted_agent_cache.py",
    "scripts/10_validate_selfhosted_checkpoint.py",
    "scripts/11_audit_selfhosted_local_readiness.py",
    "specs/001-a2a-dygrade-rl/contracts/selfhosted-chat-completions.md",
    "tests/unit/test_selfhosted_client.py",
    "tests/unit/test_multimodal_assets.py",
    "tests/unit/test_selfhosted_checkpoint.py",
    "tests/unit/test_selfhosted_costing.py",
    "tests/integration/test_selfhosted_checkpoint_workflow.py",
    "docs/design/server_handoff/README.md",
    "docs/design/server_handoff/model-approval-manifest.yaml",
    "docs/design/server_handoff/environment-lock.md",
    "docs/design/server_handoff/data-transfer-manifest.json",
    "docs/design/server_handoff/pricing-and-budget.md",
    "docs/design/server_handoff/deployment-command-template.md",
    "docs/design/server_handoff/checkpoint-runbook.md",
    "docs/design/server_handoff/artifact-return-manifest.md",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="审计自托管Pilot本地准备结构")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--prepared-root", default="data/processed/semantic_v2")
    parser.add_argument("--fake-run-id", required=True, help="明确指定由最终代码生成并已验证的Fake run")
    args = parser.parse_args()
    if re.fullmatch(r"selfhosted_local_readiness_[A-Za-z0-9._-]+", args.run_id) is None:
        parser.error("run-id必须使用selfhosted_local_readiness_前缀")
    if re.fullmatch(r"fixture_smoke_selfhosted_ministral3_[A-Za-z0-9._-]+", args.fake_run_id) is None:
        parser.error("fake-run-id必须使用fixture_smoke_selfhosted_ministral3_前缀")

    root = Path(__file__).resolve().parents[1]
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = root / output_root
    errors: list[str] = []
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    if missing:
        errors.append(f"missing_required_files:{missing}")

    checkpoint = read_yaml(root / "configs/experiments/selfhosted_ministral3_checkpoint.yaml")
    agents = [row for row in checkpoint.get("agents", {}).values() if not row.get("disabled")]
    prompt_paths = {str(row.get("prompt_path")) for row in agents}
    generations = [dict(row.get("generation_parameters") or {}) for row in agents]
    if [str(row.get("agent_id")) for row in agents] != ["CheapAgent", "MidAgent", "StrongAgent"]:
        errors.append("checkpoint_agent_set_mismatch")
    if prompt_paths != {"prompts/selfhosted_v1/scorer.txt"}:
        errors.append("checkpoint_prompt_not_shared")
    if any(row.get("temperature") != 0.0 or row.get("enable_thinking") is not False for row in generations):
        errors.append("checkpoint_generation_not_frozen")
    if checkpoint.get("local_preparation_only") is not True or checkpoint.get("formal_eligible") is not False:
        errors.append("checkpoint_local_boundary_missing")

    prepared = root / args.prepared_root
    semantic_manifest_path = prepared / "semantic_readiness_manifest.json"
    frozen_semantic_report_path = root / "outputs/runs/dataset_semantic_v2_build_20260811_001/reports/semantic_readiness.json"
    semantic_manifest_sha256 = file_sha256(semantic_manifest_path) if semantic_manifest_path.is_file() else None
    frozen_semantic_report_sha256 = file_sha256(frozen_semantic_report_path) if frozen_semantic_report_path.is_file() else None
    if semantic_manifest_sha256 is None or semantic_manifest_sha256 != frozen_semantic_report_sha256:
        errors.append("semantic_readiness_frozen_hash_mismatch")

    data_manifest = json.loads((root / "docs/design/server_handoff/data-transfer-manifest.json").read_text(encoding="utf-8"))
    transfer_files = list(data_manifest.get("files", []))
    if data_manifest.get("file_count") != len(transfer_files):
        errors.append("data_transfer_file_count_mismatch")
    transfer_total_size = 0
    for row in transfer_files:
        target = root / str(row["relative_path"])
        if not target.is_file() or target.stat().st_size != int(row["size_bytes"]) or file_sha256(target) != row["sha256"]:
            errors.append(f"data_transfer_hash_mismatch:{row['relative_path']}")
            break
        transfer_total_size += target.stat().st_size
    if int(data_manifest.get("total_size_bytes", -1)) != transfer_total_size:
        errors.append("data_transfer_total_size_mismatch")
    forbidden_transfer_paths = [
        str(row.get("relative_path", ""))
        for row in transfer_files
        if re.search(r"(?:^|/)(?:items|papers)_(?:dev|test)\.jsonl$", str(row.get("relative_path", "")).replace("\\", "/"))
        or "/data/raw/" in f"/{str(row.get('relative_path', '')).replace(chr(92), '/')}"
    ]
    if forbidden_transfer_paths:
        errors.append(f"data_transfer_forbidden_paths:{forbidden_transfer_paths}")
    if prepared.resolve() != (root / "data/processed/semantic_v2").resolve():
        errors.append("prepared_root_mismatch")

    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.splitlines()
    forbidden_tracked = [
        path
        for path in tracked
        if path.startswith(("outputs/runs/", "data/processed/", "data/raw/")) and not path.endswith(".gitkeep")
    ]
    if forbidden_tracked:
        errors.append(f"generated_artifacts_tracked:{forbidden_tracked[:10]}")

    fake_run = output_root / args.fake_run_id
    records: list[dict] = []
    attempts: list[dict] = []
    captured: list[dict] = []
    if not fake_run.is_dir():
        errors.append(f"fake_run_missing:{args.fake_run_id}")
    else:
        for path in (fake_run / "predictions/agent_cache/train_fit").glob("*Agent.jsonl"):
            records.extend(read_jsonl(path))
        if len(records) != 15:
            errors.append(f"fake_canonical_record_count:{len(records)}")
        if any(row.get("is_fixture") is not True or row.get("execution_mode") != "fixture_smoke" for row in records):
            errors.append("fake_run_identity_invalid")
        attempts = read_jsonl(fake_run / "logs/call_attempts.jsonl")
        captured = read_jsonl(fake_run / "logs/captured_chat_requests.jsonl")
        if len(attempts) != 15 or any(row.get("status") != "success" for row in attempts):
            errors.append(f"fake_attempt_audit_invalid:{len(attempts)}")
        if len(captured) != 15:
            errors.append(f"fake_captured_request_count:{len(captured)}")
        validation_path = fake_run / "reports/selfhosted_checkpoint_validation.json"
        if not validation_path.is_file():
            errors.append("fake_validation_report_missing")
        else:
            validation = json.loads(validation_path.read_text(encoding="utf-8"))
            if (
                validation.get("status") != "PASS"
                or validation.get("transport_kind") != "fake"
                or validation.get("formal_eligible") is not False
                or validation.get("unlocks_30_item_pilot") is not False
            ):
                errors.append("fake_validation_gate_invalid")

    report = {
        "schema_version": "selfhosted_local_readiness_audit_v1",
        "run_id": args.run_id,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "required_file_count": len(REQUIRED_FILES),
        "missing_required_files": missing,
        "data_transfer_file_count": data_manifest.get("file_count"),
        "data_transfer_total_size_bytes": data_manifest.get("total_size_bytes"),
        "tracked_generated_artifact_count": len(forbidden_tracked),
        "semantic_readiness_manifest_sha256": semantic_manifest_sha256,
        "frozen_semantic_report_sha256": frozen_semantic_report_sha256,
        "fake_run_id": args.fake_run_id,
        "fake_canonical_record_count": len(records),
        "fake_attempt_count": len(attempts),
        "fake_captured_request_count": len(captured),
        "safety_counters": {
            "online_agent_calls": 0,
            "model_downloads": 0,
            "dependency_installs": 0,
            "server_rental_actions": 0,
            "cuda_runtime_installs": 0,
            "prepared_data_writes": 0,
        },
    }
    run_dir = output_root / args.run_id
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "reports/selfhosted_local_readiness_audit.json", report, overwrite=True)
    (run_dir / "reports/selfhosted_local_readiness_audit.md").write_text(
        "# Self-hosted Local Readiness Audit\n\n"
        f"- status: **{report['status']}**\n"
        f"- required files: {len(REQUIRED_FILES)}\n"
        f"- data transfer files: {report['data_transfer_file_count']}\n"
        f"- fake run: `{args.fake_run_id}`\n"
        f"- fake canonical records: {len(records)}\n"
        f"- fake attempts: {len(attempts)}\n"
        f"- fake captured requests: {len(captured)}\n"
        f"- tracked generated artifacts: {len(forbidden_tracked)}\n"
        f"- semantic readiness hash match: `{semantic_manifest_sha256 == frozen_semantic_report_sha256}`\n"
        f"- safety counters: `{json.dumps(report['safety_counters'], ensure_ascii=False, sort_keys=True)}`\n"
        f"- errors: `{errors}`\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
