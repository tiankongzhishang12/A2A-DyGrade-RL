"""自托管 Ministral 3 五题 checkpoint 的确定性样本构建。"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_csv, read_jsonl, write_json, write_jsonl


REQUIRED_DATASETS = {"asap_sas", "dress", "sas_bench"}
REQUIRED_AGENT_IDS = ["CheapAgent", "MidAgent", "StrongAgent"]
RULE_VERSION = "selfhosted_ministral3_checkpoint_v1"


def _stable_rank(seed: int, paper_id: str) -> str:
    return hashlib.sha256(f"{seed}|{paper_id}|{RULE_VERSION}".encode("utf-8")).hexdigest()


def build_selfhosted_checkpoint_sample(
    *,
    papers_path: str | Path,
    items_path: str | Path,
    internal_manifest_path: str | Path,
    semantic_readiness_manifest_path: str | Path,
    run_id: str,
    seed: int = 20260812,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Any]:
    if re.fullmatch(r"real_pilot_selfhosted_checkpoint_prepare_[A-Za-z0-9._-]+", run_id) is None:
        raise ValueError("checkpoint准备 run_id 必须使用 real_pilot_selfhosted_checkpoint_prepare_ 前缀")
    readiness = json.loads(Path(semantic_readiness_manifest_path).read_text(encoding="utf-8"))
    if readiness.get("status") != "PASS" or readiness.get("errors"):
        raise ValueError("Semantic Readiness 未通过，禁止准备自托管 checkpoint")

    items_all = read_jsonl(items_path)
    item_index = {str(row["item_id"]): row for row in items_all}
    if len(item_index) != len(items_all):
        raise ValueError("items_path 存在重复 item_id")
    manifest_rows = read_csv(internal_manifest_path)
    manifest_index = {str(row["item_id"]): row for row in manifest_rows}
    if len(manifest_index) != len(manifest_rows) or "" in manifest_index:
        raise ValueError("internal_item_split_manifest存在重复或空item_id")

    eligible: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for paper in read_jsonl(papers_path):
        metadata = dict(paper.get("metadata") or {})
        item_ids = [str(value) for value in paper.get("items", [])]
        if metadata.get("internal_split") != "train_fit" or metadata.get("mix_status") != "strict" or len(item_ids) != 5:
            continue
        if len(set(item_ids)) != 5 or any(item_id not in item_index for item_id in item_ids):
            continue
        rows = [item_index[item_id] for item_id in item_ids]
        if {str(row.get("dataset")) for row in rows} != REQUIRED_DATASETS:
            continue
        if not any(str(row.get("dataset")) == "asap_sas" and row.get("source_assets") for row in rows):
            continue
        if any(
            item_id not in manifest_index
            or manifest_index[item_id].get("source_split") != "train"
            or manifest_index[item_id].get("internal_split") != "train_fit"
            for item_id in item_ids
        ):
            continue
        eligible.append((paper, rows))
    if not eligible:
        raise ValueError("没有满足三数据集+ASAP-SAS图片要求的 train_fit strict Paper")

    selected_paper, selected_rows = min(
        eligible,
        key=lambda pair: _stable_rank(seed, str(pair[0]["paper_id"])),
    )
    selected_item_ids = [str(row["item_id"]) for row in selected_rows]
    prepared_items: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    for position, row in enumerate(selected_rows, start=1):
        prepared = dict(row)
        prepared["metadata"] = {
            **dict(row.get("metadata") or {}),
            "source_split": str(row.get("metadata", {}).get("split", "train")),
            "split": "train_fit",
            "internal_split": "train_fit",
            "checkpoint_prepare_run_id": run_id,
            "formal_eligible": False,
        }
        prepared_items.append(prepared)
        sample_rows.append(
            {
                "paper_id": str(selected_paper["paper_id"]),
                "paper_position": position,
                "item_id": str(row["item_id"]),
                "dataset": str(row.get("dataset", "")),
                "prompt_group": str(row.get("metadata", {}).get("prompt_group", "")),
                "has_source_assets": bool(row.get("source_assets")),
                "source_asset_count": len(row.get("source_assets") or []),
                "selection_seed": seed,
                "selection_rule_version": RULE_VERSION,
            }
        )

    run_dir = Path(output_root) / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"checkpoint准备run_id已存在，禁止覆盖: {run_dir}")
    config_dir = ensure_dir(run_dir / "configs")
    input_dir = ensure_dir(run_dir / "predictions" / "checkpoint_inputs")
    report_dir = ensure_dir(run_dir / "reports")
    items_output = input_dir / "items_train_fit_checkpoint.jsonl"
    papers_output = input_dir / "papers_train_fit_checkpoint.jsonl"
    internal_output = config_dir / "internal_item_split_manifest.checkpoint.csv"
    sample_output = config_dir / "checkpoint_sample_manifest.csv"
    write_jsonl(items_output, prepared_items, overwrite=True)
    write_jsonl(papers_output, [selected_paper], overwrite=True)
    _write_csv(internal_output, [manifest_index[item_id] for item_id in selected_item_ids])
    _write_csv(sample_output, sample_rows)

    manifest = {
        "schema_version": "selfhosted_checkpoint_manifest_v1",
        "run_id": run_id,
        "execution_mode": "preparation_only",
        "formal_eligible": False,
        "semantic_readiness_status": readiness.get("status"),
        "semantic_readiness_run_id": readiness.get("run_id"),
        "paper_count": 1,
        "item_count": 5,
        "paper_id": str(selected_paper["paper_id"]),
        "selected_paper_ids": [str(selected_paper["paper_id"])],
        "selected_item_ids": selected_item_ids,
        "dataset_counts": {
            dataset: sum(str(row.get("dataset")) == dataset for row in selected_rows)
            for dataset in sorted(REQUIRED_DATASETS)
        },
        "image_item_count": sum(bool(row.get("source_assets")) for row in selected_rows),
        "asap_sas_image_item_count": sum(str(row.get("dataset")) == "asap_sas" and bool(row.get("source_assets")) for row in selected_rows),
        "source_asset_count": sum(len(row.get("source_assets") or []) for row in selected_rows),
        "selection_seed": int(seed),
        "selection_rule_version": RULE_VERSION,
        "gold_fields_read_for_selection": 0,
        "expected_agent_ids": REQUIRED_AGENT_IDS,
        "expected_canonical_calls": 15,
        "unlocks_30_item_pilot": False,
        "source_files": {
            "papers_path": str(Path(papers_path)),
            "papers_sha256": file_sha256(papers_path),
            "items_path": str(Path(items_path)),
            "items_sha256": file_sha256(items_path),
            "internal_manifest_path": str(Path(internal_manifest_path)),
            "internal_manifest_sha256": file_sha256(internal_manifest_path),
            "semantic_readiness_manifest_path": str(Path(semantic_readiness_manifest_path)),
            "semantic_readiness_manifest_sha256": file_sha256(semantic_readiness_manifest_path),
        },
        "outputs": {
            "items_path": str(items_output),
            "items_sha256": file_sha256(items_output),
            "papers_path": str(papers_output),
            "papers_sha256": file_sha256(papers_output),
            "internal_manifest_path": str(internal_output),
            "internal_manifest_sha256": file_sha256(internal_output),
            "sample_manifest_path": str(sample_output),
            "sample_manifest_sha256": file_sha256(sample_output),
        },
        "safety_counters": {
            "online_agent_calls": 0,
            "model_downloads": 0,
            "dependency_installs": 0,
            "server_rental_actions": 0,
            "cuda_runtime_installs": 0,
            "prepared_data_writes": 0,
        },
    }
    manifest_path = config_dir / "selfhosted_checkpoint_manifest.json"
    write_json(manifest_path, manifest, overwrite=True)
    report_path = report_dir / "checkpoint_preparation_audit.md"
    report_path.write_text(
        "# Self-hosted Checkpoint Preparation Audit\n\n"
        f"- run_id: `{run_id}`\n"
        f"- paper_id: `{selected_paper['paper_id']}`\n"
        f"- item_count: 5\n"
        f"- datasets: `{manifest['dataset_counts']}`\n"
        f"- image_item_count: {manifest['image_item_count']}\n"
        "- gold_fields_read_for_selection: 0\n"
        "- online_agent_calls/model_downloads/dependency_installs/server_actions: 0\n",
        encoding="utf-8",
    )
    return {**manifest, "manifest_path": str(manifest_path), "report_path": str(report_path)}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("不能写入空 CSV")
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
