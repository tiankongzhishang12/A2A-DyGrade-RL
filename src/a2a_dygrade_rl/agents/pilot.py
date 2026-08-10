"""真实 Agent Pilot 的确定性 Paper/Item 样本构建。"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_csv, read_jsonl, write_json, write_jsonl


def _stable_rank(seed: int, paper_id: str) -> str:
    return hashlib.sha256(f"{seed}|{paper_id}|cliproxy_gpt56_pilot_v1".encode("utf-8")).hexdigest()


def build_real_pilot_sample(
    *,
    papers_path: str | Path,
    items_path: str | Path,
    internal_manifest_path: str | Path,
    run_id: str,
    paper_count: int = 20,
    seed: int = 42,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Any]:
    if re.fullmatch(r"real_pilot_[A-Za-z0-9._-]+", run_id) is None:
        raise ValueError("Pilot run_id 必须使用 real_pilot_ 前缀且为安全路径组件")
    if paper_count <= 0:
        raise ValueError("paper_count 必须为正整数")
    papers = read_jsonl(papers_path)
    eligible = [
        paper
        for paper in papers
        if paper.get("metadata", {}).get("internal_split") == "train_fit"
        and paper.get("metadata", {}).get("mix_status") == "strict"
        and len(paper.get("items", [])) == 5
    ]
    if len(eligible) < paper_count:
        raise ValueError("可用 train_fit strict Paper 数量不足")
    selected_papers = sorted(eligible, key=lambda row: _stable_rank(seed, str(row["paper_id"])))[:paper_count]
    selected_item_ids = [str(item_id) for paper in selected_papers for item_id in paper["items"]]
    if len(selected_item_ids) != paper_count * 5 or len(selected_item_ids) != len(set(selected_item_ids)):
        raise ValueError("Pilot Paper 引用 Item 数量或唯一性不合法")

    item_id_set = set(selected_item_ids)
    item_rows = {str(row["item_id"]): row for row in read_jsonl(items_path) if str(row.get("item_id", "")) in item_id_set}
    missing_items = sorted(item_id_set - set(item_rows))
    if missing_items:
        raise ValueError(f"Pilot Paper 引用不存在 Item: {missing_items[:10]}")
    manifest_rows = [row for row in read_csv(internal_manifest_path) if row.get("item_id") in item_id_set]
    manifest_index = {row["item_id"]: row for row in manifest_rows}
    if set(manifest_index) != item_id_set:
        raise ValueError("Pilot Item 与 internal manifest 不一致")
    if any(row.get("internal_split") != "train_fit" or row.get("source_split") != "train" for row in manifest_rows):
        raise ValueError("Pilot 只允许 train_fit Item")

    run_dir = Path(output_root) / run_id
    config_dir = ensure_dir(run_dir / "configs")
    input_dir = ensure_dir(run_dir / "predictions" / "pilot_inputs")
    ordered_items: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    paper_by_item = {
        str(item_id): (str(paper["paper_id"]), position)
        for paper in selected_papers
        for position, item_id in enumerate(paper["items"], start=1)
    }
    for item_id in selected_item_ids:
        row = dict(item_rows[item_id])
        row["metadata"] = {
            **dict(row.get("metadata") or {}),
            "source_split": str(row.get("metadata", {}).get("split", "train")),
            "split": "train_fit",
            "internal_split": "train_fit",
            "pilot_run_id": run_id,
            "formal_eligible": False,
        }
        ordered_items.append(row)
        paper_id, position = paper_by_item[item_id]
        sample_rows.append(
            {
                "paper_id": paper_id,
                "item_id": item_id,
                "paper_position": position,
                "dataset": row.get("dataset", ""),
                "prompt_group": row.get("metadata", {}).get("prompt_group", ""),
                "question_type": row.get("question_type", ""),
                "answer_length": row.get("metadata", {}).get("answer_length", len(str(row.get("student_answer", "")))),
                "selection_seed": seed,
                "selection_rule_version": "cliproxy_gpt56_pilot_v1",
            }
        )

    items_output = input_dir / "items_train_fit_pilot.jsonl"
    papers_output = input_dir / "papers_train_fit_pilot.jsonl"
    internal_output = config_dir / "internal_item_split_manifest.pilot.csv"
    sample_output = config_dir / "pilot_sample_manifest.csv"
    write_jsonl(items_output, ordered_items, overwrite=True)
    write_jsonl(papers_output, selected_papers, overwrite=True)
    _write_csv(internal_output, [manifest_index[item_id] for item_id in selected_item_ids])
    _write_csv(sample_output, sample_rows)
    manifest = {
        "run_id": run_id,
        "execution_mode": "real_pilot",
        "formal_eligible": False,
        "split": "train_fit",
        "paper_count": paper_count,
        "item_count": len(selected_item_ids),
        "seed": seed,
        "selection_rule_version": "cliproxy_gpt56_pilot_v1",
        "source_files": {
            "papers_path": str(Path(papers_path)),
            "papers_sha256": file_sha256(papers_path),
            "items_path": str(Path(items_path)),
            "items_sha256": file_sha256(items_path),
            "internal_manifest_path": str(Path(internal_manifest_path)),
            "internal_manifest_sha256": file_sha256(internal_manifest_path),
        },
        "outputs": {
            "items_path": str(items_output),
            "papers_path": str(papers_output),
            "internal_manifest_path": str(internal_output),
            "sample_manifest_path": str(sample_output),
        },
        "selected_paper_ids": [paper["paper_id"] for paper in selected_papers],
        "selected_item_ids": selected_item_ids,
    }
    manifest_path = config_dir / "pilot_sample_manifest.json"
    write_json(manifest_path, manifest, overwrite=True)
    return {**manifest, "manifest_path": str(manifest_path)}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("不能写入空 CSV")
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
