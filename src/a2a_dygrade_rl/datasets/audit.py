"""prepared data 审计逻辑。"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.normalize import score_range
from a2a_dygrade_rl.utils.io import ensure_dir, read_jsonl, write_csv
from a2a_dygrade_rl.utils.validation import validate_item, validate_paper


SPLITS = ("train", "dev", "test")
DATASET_MIX_TARGET = {
    "asap_sas": (2, 3),
    "sas_bench": (1, 2),
    "dress": (1, 1),
}


@dataclass
class AuditResult:
    processed_dir: Path
    run_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    distribution_rows: list[dict[str, Any]] = field(default_factory=list)
    report_path: Path | None = None
    distribution_path: Path | None = None

    @property
    def passed(self) -> bool:
        return not self.errors


def audit_prepared_data(
    processed_dir: str | Path,
    run_id: str,
    output_root: str | Path = "outputs/runs",
    min_paper_items: int = 5,
    max_paper_items: int = 8,
    write_reports: bool = True,
    overwrite: bool = False,
) -> AuditResult:
    processed_path = Path(processed_dir)
    result = AuditResult(processed_path, run_id)
    items_by_split = _load_split_jsonl(processed_path, "items", result)
    papers_by_split = _load_split_jsonl(processed_path, "papers", result)
    all_items = [item for rows in items_by_split.values() for item in rows]
    all_papers = [paper for rows in papers_by_split.values() for paper in rows]

    items_by_id = _audit_items(items_by_split, result)
    _audit_split_leakage(items_by_split, result)
    _audit_papers(papers_by_split, items_by_id, result, min_paper_items, max_paper_items)
    _audit_manifests(processed_path, result)
    _build_distribution(items_by_split, papers_by_split, items_by_id, result)
    _build_summary(all_items, all_papers, result)

    if write_reports:
        report_dir = ensure_dir(Path(output_root) / run_id / "reports")
        result.report_path = _write_markdown_report(report_dir / "data_audit.md", result, overwrite=overwrite)
        result.distribution_path = write_csv(
            report_dir / "data_distribution.csv",
            result.distribution_rows,
            ["category", "split", "dataset", "metric", "value"],
            overwrite=overwrite,
        )
    return result


def _load_split_jsonl(processed_dir: Path, prefix: str, result: AuditResult) -> dict[str, list[dict[str, Any]]]:
    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    for split in SPLITS:
        path = processed_dir / f"{prefix}_{split}.jsonl"
        if not path.exists():
            result.errors.append(f"缺少 {prefix}_{split}.jsonl: {path}")
            rows_by_split[split] = []
            continue
        rows_by_split[split] = read_jsonl(path)
    return rows_by_split


def _audit_items(items_by_split: dict[str, list[dict[str, Any]]], result: AuditResult) -> dict[str, dict[str, Any]]:
    items_by_id: dict[str, dict[str, Any]] = {}
    empty_prompt = 0
    empty_answer = 0
    missing_rubric_reference = 0
    duplicate_keys: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    score_ranges = Counter()
    for split, items in items_by_split.items():
        for item in items:
            item_id = str(item.get("item_id", ""))
            try:
                validate_item(item)
                score_range(float(item["score_min"]), float(item["score_max"]))
            except Exception as exc:  # noqa: BLE001 - 审计需要聚合所有坏样本。
                result.errors.append(f"Item 校验失败 [{split}] {item_id}: {exc}")
            metadata = item.setdefault("metadata", {})
            metadata_split = metadata.get("split")
            if metadata_split and str(metadata_split) != split:
                result.errors.append(f"Item split metadata 与文件 split 不一致: {item_id} metadata={metadata_split} file={split}")
            if not str(item.get("prompt", "")).strip():
                empty_prompt += 1
            if not str(item.get("student_answer", "")).strip():
                empty_answer += 1
            if not str(item.get("rubric", "")).strip() and not str(item.get("reference_answer", "")).strip():
                missing_rubric_reference += 1
            key = (str(item.get("dataset", "")), str(item.get("prompt", "")).strip(), str(item.get("student_answer", "")).strip())
            duplicate_keys[key].add(split)
            score_ranges[f"{item.get('score_min')}..{item.get('score_max')}"] += 1
            if item_id in items_by_id:
                result.errors.append(f"重复 item_id: {item_id}")
            items_by_id[item_id] = item

    exact_duplicates = sum(1 for splits in duplicate_keys.values() if len(splits) >= 1) - len(duplicate_keys)
    cross_split_duplicates = sum(1 for splits in duplicate_keys.values() if len(splits) > 1)
    if empty_prompt:
        result.errors.append(f"发现空 prompt: {empty_prompt}")
    if empty_answer:
        result.errors.append(f"发现空 student_answer: {empty_answer}")
    if missing_rubric_reference:
        result.errors.append(f"发现 rubric/reference_answer 同时缺失: {missing_rubric_reference}")
    if cross_split_duplicates:
        result.errors.append(f"发现 exact prompt-answer 跨 split 重复键: {cross_split_duplicates}")
    result.summary["score_ranges"] = dict(score_ranges)
    result.summary["exact_prompt_answer_cross_split_duplicates"] = cross_split_duplicates
    return items_by_id


def _audit_split_leakage(items_by_split: dict[str, list[dict[str, Any]]], result: AuditResult) -> None:
    item_splits: dict[str, set[str]] = defaultdict(set)
    prompt_splits: dict[str, set[str]] = defaultdict(set)
    for split, items in items_by_split.items():
        for item in items:
            item_splits[str(item.get("item_id", ""))].add(split)
            prompt_group = item.get("metadata", {}).get("prompt_group") or item.get("metadata", {}).get("prompt_id") or item.get("prompt")
            prompt_splits[f"{item.get('dataset')}::{prompt_group}"].add(split)
    leaked_items = {item_id: sorted(splits) for item_id, splits in item_splits.items() if len(splits) > 1}
    leaked_test_prompts = {
        prompt_group: sorted(splits)
        for prompt_group, splits in prompt_splits.items()
        if "test" in splits and ({"train", "dev"} & splits)
    }
    if leaked_items:
        result.errors.append(f"发现 item 跨 split 泄漏: {len(leaked_items)}")
    if leaked_test_prompts:
        result.errors.append(f"发现 test prompt group 与 train/dev 泄漏: {len(leaked_test_prompts)}")
    result.summary["item_split_leakage_count"] = len(leaked_items)
    result.summary["test_prompt_leakage_count"] = len(leaked_test_prompts)


def _audit_papers(
    papers_by_split: dict[str, list[dict[str, Any]]],
    items_by_id: dict[str, dict[str, Any]],
    result: AuditResult,
    min_paper_items: int,
    max_paper_items: int,
) -> None:
    mix_counter = Counter()
    strict_mix_mismatch = 0
    relaxed_mix_mismatch = 0
    missing_refs = 0
    cross_split_refs = 0
    for split, papers in papers_by_split.items():
        split_items = {item_id for item_id, item in items_by_id.items() if item.get("metadata", {}).get("split") == split}
        for paper in papers:
            paper_id = str(paper.get("paper_id", ""))
            try:
                validate_paper(paper, items_by_id)
            except Exception as exc:  # noqa: BLE001 - 审计需要聚合所有坏样本。
                result.errors.append(f"Paper 校验失败 [{split}] {paper_id}: {exc}")
            item_ids = list(paper.get("items") or [])
            if not min_paper_items <= len(item_ids) <= max_paper_items:
                result.errors.append(f"Paper item 数量非法 [{split}] {paper_id}: {len(item_ids)}")
            for item_id in item_ids:
                if item_id not in items_by_id:
                    missing_refs += 1
                    continue
                if item_id not in split_items:
                    cross_split_refs += 1
            dataset_counts = Counter(items_by_id[item_id]["dataset"] for item_id in item_ids if item_id in items_by_id)
            mix_key = ";".join(f"{dataset}:{dataset_counts[dataset]}" for dataset in sorted(dataset_counts))
            mix_counter[mix_key] += 1
            if not _dataset_mix_matches_target(dataset_counts):
                if paper.get("metadata", {}).get("mix_status") == "strict":
                    strict_mix_mismatch += 1
                else:
                    relaxed_mix_mismatch += 1
    if missing_refs:
        result.errors.append(f"Paper 引用不存在 item 数量: {missing_refs}")
    if cross_split_refs:
        result.errors.append(f"Paper 引用跨 split item 数量: {cross_split_refs}")
    if strict_mix_mismatch:
        result.errors.append(f"主实验 strict paper dataset mix 未达到 2-3 ASAP-SAS、1-2 SAS-Bench、1 DREsS 目标: {strict_mix_mismatch} 张")
    if relaxed_mix_mismatch:
        result.warnings.append(f"relaxed paper dataset mix 未达到主实验目标: {relaxed_mix_mismatch} 张")
    result.summary["paper_missing_item_refs"] = missing_refs
    result.summary["paper_cross_split_refs"] = cross_split_refs
    result.summary["paper_dataset_mix_mismatch"] = strict_mix_mismatch + relaxed_mix_mismatch
    result.summary["strict_paper_dataset_mix_mismatch"] = strict_mix_mismatch
    result.summary["relaxed_paper_dataset_mix_mismatch"] = relaxed_mix_mismatch
    result.summary["paper_dataset_mix_patterns"] = dict(mix_counter)


def _dataset_mix_matches_target(dataset_counts: Counter[str]) -> bool:
    for dataset, (minimum, maximum) in DATASET_MIX_TARGET.items():
        value = int(dataset_counts.get(dataset, 0))
        if value < minimum or value > maximum:
            return False
    return True


def _audit_manifests(processed_dir: Path, result: AuditResult) -> None:
    split_manifest = processed_dir / "split_manifest.csv"
    paper_manifest = processed_dir / "paper_manifest.csv"
    if not split_manifest.exists():
        result.errors.append(f"缺少 split_manifest.csv: {split_manifest}")
    else:
        split_rows = _read_csv_rows(split_manifest)
        required = {"item_id", "dataset", "prompt_group", "paper_id", "split", "seed", "rule_version", "split_scope"}
        _check_manifest_columns(split_rows, required, "split_manifest.csv", result)
    if not paper_manifest.exists():
        result.errors.append(f"缺少 paper_manifest.csv: {paper_manifest}")
    else:
        paper_rows = _read_csv_rows(paper_manifest)
        required = {"item_id", "dataset", "prompt_group", "paper_id", "split", "seed", "rule_version"}
        _check_manifest_columns(paper_rows, required, "paper_manifest.csv", result)
        empty_prompt_groups = sum(1 for row in paper_rows if not str(row.get("prompt_group", "")).strip())
        if empty_prompt_groups:
            result.errors.append(f"paper_manifest.csv 中 prompt_group 为空: {empty_prompt_groups} 行")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _check_manifest_columns(rows: list[dict[str, str]], required: set[str], label: str, result: AuditResult) -> None:
    if not rows:
        result.warnings.append(f"{label} 没有数据行")
        return
    columns = set(rows[0].keys())
    missing = sorted(required - columns)
    if missing:
        result.errors.append(f"{label} 缺少列: {missing}")


def _build_distribution(
    items_by_split: dict[str, list[dict[str, Any]]],
    papers_by_split: dict[str, list[dict[str, Any]]],
    items_by_id: dict[str, dict[str, Any]],
    result: AuditResult,
) -> None:
    rows: list[dict[str, Any]] = []
    for split, items in items_by_split.items():
        rows.append(_distribution_row("items", split, "ALL", "count", len(items)))
        dataset_counter = Counter(str(item.get("dataset", "")) for item in items)
        prompt_groups = defaultdict(set)
        for item in items:
            dataset = str(item.get("dataset", ""))
            prompt_group = item.get("metadata", {}).get("prompt_group") or item.get("prompt")
            prompt_groups[dataset].add(str(prompt_group))
        for dataset, count in sorted(dataset_counter.items()):
            rows.append(_distribution_row("items", split, dataset, "count", count))
            rows.append(_distribution_row("prompt_groups", split, dataset, "count", len(prompt_groups[dataset])))
    for split, papers in papers_by_split.items():
        rows.append(_distribution_row("papers", split, "ALL", "count", len(papers)))
        for paper in papers:
            dataset_counts = Counter(
                str(items_by_id[item_id].get("dataset", ""))
                for item_id in paper.get("items", [])
                if item_id in items_by_id
            )
            for dataset, count in sorted(dataset_counts.items()):
                rows.append(_distribution_row("paper_dataset_items", split, dataset, "count", count))
    for range_label, count in sorted(result.summary.get("score_ranges", {}).items()):
        rows.append(_distribution_row("score_ranges", "ALL", "ALL", range_label, count))
    result.distribution_rows = rows


def _distribution_row(category: str, split: str, dataset: str, metric: str, value: Any) -> dict[str, Any]:
    return {"category": category, "split": split, "dataset": dataset, "metric": metric, "value": value}


def _build_summary(all_items: list[dict[str, Any]], all_papers: list[dict[str, Any]], result: AuditResult) -> None:
    result.summary["total_items"] = len(all_items)
    result.summary["total_papers"] = len(all_papers)
    result.summary["formula"] = "R_i = score_max_i - score_min_i; E_i = abs(pred_score_i - gold_score_i) / R_i"
    result.summary["status"] = "PASS" if result.passed else "FAIL"


def _write_markdown_report(path: Path, result: AuditResult, overwrite: bool = False) -> Path:
    if path.exists() and not overwrite:
        raise FileExistsError(f"输出已存在，若需覆盖请显式传入 overwrite: {path}")
    ensure_dir(path.parent)
    lines = [
        "# Prepared Data 审计报告",
        "",
        f"- run_id: `{result.run_id}`",
        f"- processed_dir: `{result.processed_dir}`",
        f"- 审计状态: **{result.summary.get('status', 'UNKNOWN')}**",
        f"- item 总数: {result.summary.get('total_items', 0)}",
        f"- paper 总数: {result.summary.get('total_papers', 0)}",
        "",
        "## 分数归一化",
        "",
        "审计确认每条被接受 item 都必须满足 `R_i > 0`，后续 Agent 误差、difficulty labels、capability profiles 和 reward 统一使用：",
        "",
        "```text",
        str(result.summary.get("formula", "")),
        "```",
        "",
        "## 泄漏检查",
        "",
        f"- item 跨 split 泄漏数量: {result.summary.get('item_split_leakage_count', 0)}",
        f"- test prompt group 与 train/dev 泄漏数量: {result.summary.get('test_prompt_leakage_count', 0)}",
        f"- paper 引用不存在 item 数量: {result.summary.get('paper_missing_item_refs', 0)}",
        f"- paper 引用跨 split item 数量: {result.summary.get('paper_cross_split_refs', 0)}",
        "",
        "## Paper Dataset Mix",
        "",
        f"- 不满足目标 mix 的 paper 数量: {result.summary.get('paper_dataset_mix_mismatch', 0)}",
        "- 目标 mix: 2-3 ASAP-SAS、1-2 SAS-Bench、1 DREsS",
        "",
        "## Score Range 分布",
        "",
    ]
    for range_label, count in sorted(result.summary.get("score_ranges", {}).items()):
        lines.append(f"- `{range_label}`: {count}")
    lines.extend(["", "## 错误", ""])
    if result.errors:
        lines.extend(f"- {error}" for error in result.errors)
    else:
        lines.append("- 无")
    lines.extend(["", "## 警告", ""])
    if result.warnings:
        lines.extend(f"- {warning}" for warning in result.warnings)
    else:
        lines.append("- 无")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path
