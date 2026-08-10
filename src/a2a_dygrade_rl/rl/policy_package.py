"""每个冻结 checkpoint 的 Calibration/Policy Package 构建器。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from a2a_dygrade_rl.utils.io import write_jsonl
from a2a_dygrade_rl.utils.schemas import CalibrationPackage, PolicyPackage
from a2a_dygrade_rl.utils.validation import validate_calibration_packages, validate_policy_package


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_policy_packages(
    *,
    checkpoints: Iterable[dict[str, Any]],
    calibration_results: Iterable[dict[str, Any]],
    quality_protocol_hash: str,
    internal_manifest_hash: str,
    quality_reference_manifest_hash: str,
    budget_manifest_hash: str,
    support_manifest_hash: str,
    output_dir: str | Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    checkpoint_rows = [dict(row) for row in checkpoints]
    calibration_rows = [dict(row) for row in calibration_results]
    checkpoint_index = {str(row["checkpoint_id"]): row for row in checkpoint_rows}
    calibration_index = {str(row["checkpoint_id"]): row for row in calibration_rows}
    if len(checkpoint_index) != len(checkpoint_rows) or len(calibration_index) != len(calibration_rows):
        raise ValueError("checkpoint 或 calibration result 重复")
    if set(checkpoint_index) != set(calibration_index):
        raise ValueError("checkpoint 与 calibration result 必须一一对应")

    package_ids = [str(row.get("package_id") or f"pkg_{row['checkpoint_id']}") for row in checkpoint_rows]
    if len(package_ids) != len(set(package_ids)):
        raise ValueError("Policy Package ID 必须唯一")

    calibration_packages: list[dict[str, Any]] = []
    policy_packages: list[dict[str, Any]] = []
    for checkpoint_id in sorted(checkpoint_index):
        checkpoint = checkpoint_index[checkpoint_id]
        calibration = calibration_index[checkpoint_id]
        if str(checkpoint["checkpoint_hash"]) != str(calibration["checkpoint_hash"]):
            raise ValueError(f"checkpoint_hash 与 calibration 不一致: {checkpoint_id}")
        status = calibration.get("calibration_status")
        if status not in {"success", "failure"}:
            raise ValueError(f"非法 calibration_status: {status}")
        for flag in ("calibration_no_gradient", "calibration_no_replay", "calibration_no_checkpoint_ranking"):
            if calibration.get(flag) is not True:
                raise ValueError(f"calibration {flag} 必须是显式 true")
        package_id = str(checkpoint.get("package_id") or f"pkg_{checkpoint_id}")
        success = status == "success"
        calibration_package = CalibrationPackage(
            package_id=package_id,
            checkpoint_id=checkpoint_id,
            checkpoint_hash=str(checkpoint["checkpoint_hash"]),
            calibration_status="success" if success else "failure",
            stop_boundary=float(calibration["stop_boundary"]) if success else None,
            calibration_failure_reason="" if success else str(calibration.get("failure_reason") or "unknown_calibration_failure"),
            boundary_frozen=bool(success),
            calibration_split="train_calibration",
            calibration_no_gradient=True,
            calibration_no_replay=True,
            calibration_no_checkpoint_ranking=True,
            main_method_upgrade_thresholds={},
            quality_protocol_hash=str(quality_protocol_hash),
            internal_manifest_hash=str(internal_manifest_hash),
            quality_reference_manifest_hash=str(quality_reference_manifest_hash),
            budget_manifest_hash=str(budget_manifest_hash),
            support_manifest_hash=str(support_manifest_hash),
            coverage=float(calibration.get("coverage", 0.0)),
        ).to_dict()
        calibration_packages.append(calibration_package)
        if success:
            calibration_hash = _stable_hash(calibration_package)
            policy_package = PolicyPackage(
                package_id=package_id,
                checkpoint_id=checkpoint_id,
                checkpoint_hash=str(checkpoint["checkpoint_hash"]),
                calibration_package_hash=calibration_hash,
                package_role=str(checkpoint.get("package_role", "router_candidate")),
                calibration_status="success",
                stop_boundary=float(calibration["stop_boundary"]),
                boundary_frozen=True,
                dev_boundary_updates=0,
                quality_protocol_hash=str(quality_protocol_hash),
                internal_manifest_hash=str(internal_manifest_hash),
                quality_reference_manifest_hash=str(quality_reference_manifest_hash),
                budget_manifest_hash=str(budget_manifest_hash),
                support_manifest_hash=str(support_manifest_hash),
                metadata={
                    "policy_kind": checkpoint.get("policy_kind", ""),
                    "calibration_coverage": float(calibration.get("coverage", 0.0)),
                },
            ).to_dict()
            validate_policy_package(policy_package, expected_protocol_hash=str(quality_protocol_hash))
            policy_packages.append(policy_package)

    validate_calibration_packages(calibration_packages, expected_protocol_hash=str(quality_protocol_hash))
    if output_dir is not None:
        output = Path(output_dir)
        write_jsonl(output / "calibration_package_manifest.jsonl", calibration_packages, overwrite=True)
        write_jsonl(output / "policy_package_manifest.jsonl", policy_packages, overwrite=True)
    return {"calibration_packages": calibration_packages, "policy_packages": policy_packages}
