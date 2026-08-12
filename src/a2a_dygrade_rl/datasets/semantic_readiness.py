"""Dataset Semantic V2 fail-closed Semantic Readiness 门禁。"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.audit import audit_prepared_data
from a2a_dygrade_rl.datasets.load_asap_sas import ASAP_SCORE_RANGES
from a2a_dygrade_rl.utils.io import ensure_dir, file_sha256, read_csv, read_jsonl, read_yaml, write_json
from a2a_dygrade_rl.utils.model_input import find_banned_keys, project_model_visible_item
from a2a_dygrade_rl.utils.validation import validate_item, validate_no_split_leakage, validate_paper


SPLITS = ("train", "dev", "test")
PLACEHOLDER_PATTERNS = (
    re.compile(r"see\s+data_set_descriptions\.zip", re.IGNORECASE),
    re.compile(r"see\s+training_materials\.zip", re.IGNORECASE),
    re.compile(r"\bplaceholder(?:\s+text)?\b", re.IGNORECASE),
    re.compile(r"\b(?:TODO|TBD)\b"),
)
MODEL_SPECIFIC_KEYS = {
    "input_ids",
    "attention_mask",
    "pixel_values",
    "image_embeds",
    "image_embeddings",
    "vision_embeddings",
    "visual_tokens",
    "vision_tokens",
    "token_ids",
    "tokenizer_name",
    "processor_name",
    "model_inputs",
}


@dataclass
class SemanticReadinessResult:
    processed_dir: Path
    run_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    manifest_path: Path | None = None
    report_path: Path | None = None
    json_report_path: Path | None = None

    @property
    def passed(self) -> bool:
        return not self.errors

    def add_check(self, name: str, passed: bool, detail: str, *, blocking: bool = True) -> None:
        self.checks.append({"name": name, "passed": bool(passed), "blocking": bool(blocking), "detail": detail})
        if blocking and not passed:
            self.errors.append(f"{name}: {detail}")
        elif not passed:
            self.warnings.append(f"{name}: {detail}")


def _load_items(processed_dir: Path, result: SemanticReadinessResult) -> dict[str, list[dict[str, Any]]]:
    items_by_split: dict[str, list[dict[str, Any]]] = {}
    for split in SPLITS:
        path = processed_dir / f"items_{split}.jsonl"
        if not path.exists():
            result.add_check(f"items_{split}", False, f"缺少 {path}")
            items_by_split[split] = []
            continue
        try:
            items_by_split[split] = read_jsonl(path)
        except Exception as exc:  # noqa: BLE001 - 审计聚合全部错误。
            result.add_check(f"items_{split}", False, f"读取失败: {exc}")
            items_by_split[split] = []
    return items_by_split


def _load_papers(processed_dir: Path, result: SemanticReadinessResult) -> dict[str, list[dict[str, Any]]]:
    papers_by_split: dict[str, list[dict[str, Any]]] = {}
    for split in SPLITS:
        path = processed_dir / f"papers_{split}.jsonl"
        if not path.exists():
            result.add_check(f"papers_{split}", False, f"缺少 {path}")
            papers_by_split[split] = []
            continue
        try:
            papers_by_split[split] = read_jsonl(path)
        except Exception as exc:  # noqa: BLE001
            result.add_check(f"papers_{split}", False, f"读取失败: {exc}")
            papers_by_split[split] = []
    return papers_by_split


def _find_key_paths(value: Any, banned: set[str], *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in banned:
                findings.append(child_path)
            findings.extend(_find_key_paths(child, banned, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_find_key_paths(child, banned, path=f"{path}[{index}]"))
    return findings


def _artifact_hashes(processed_dir: Path, names: list[str]) -> dict[str, str]:
    return {name: file_sha256(processed_dir / name) for name in names if (processed_dir / name).exists()}


def _audit_build_manifest(
    processed_dir: Path,
    all_items: list[dict[str, Any]],
    result: SemanticReadinessResult,
    *,
    config_path: Path | None,
) -> dict[str, Any]:
    path = processed_dir / "dataset_build_manifest.json"
    if not path.exists():
        result.add_check("dataset_build_manifest", False, f"缺少 {path}")
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        result.add_check("dataset_build_manifest", False, f"JSON 读取失败: {exc}")
        return {}
    result.add_check(
        "dataset_build_manifest_schema",
        manifest.get("schema_version") == "dataset_build_manifest_v2",
        f"schema_version={manifest.get('schema_version')!r}",
    )
    result.add_check(
        "build_manifest_item_count",
        int(manifest.get("accepted_item_count", -1)) == len(all_items),
        f"manifest={manifest.get('accepted_item_count')} actual={len(all_items)}",
    )
    safety = manifest.get("safety_counters", {})
    required_safety = {
        "online_agent_calls",
        "model_downloads",
        "dependency_installs",
        "raw_data_writes",
        "training_material_anchor_reads",
        "model_specific_preprocessing_records",
    }
    safety_ok = required_safety <= set(safety) and all(int(safety.get(key, -1)) == 0 for key in required_safety)
    result.add_check("data_build_safety_counters", safety_ok, json.dumps(safety, ensure_ascii=False, sort_keys=True))
    if config_path is not None and config_path.exists():
        expected_hash = str(manifest.get("config", {}).get("sha256", ""))
        actual_hash = file_sha256(config_path)
        result.add_check("dataset_config_hash", expected_hash == actual_hash, f"manifest={expected_hash} actual={actual_hash}")
    artifact_errors: list[str] = []
    for name, record in manifest.get("artifacts", {}).items():
        relative = str(record.get("relative_path", ""))
        artifact_path = processed_dir / relative
        if not relative or not artifact_path.exists():
            artifact_errors.append(f"{name}:missing:{relative}")
            continue
        actual = file_sha256(artifact_path)
        if actual != str(record.get("sha256", "")):
            artifact_errors.append(f"{name}:hash_mismatch")
    result.add_check("build_artifact_hashes", not artifact_errors, "; ".join(artifact_errors) or "全部匹配")
    return manifest


def _audit_assets(
    processed_dir: Path,
    all_items: list[dict[str, Any]],
    result: SemanticReadinessResult,
    *,
    required_essay_sets: list[str],
) -> None:
    resource_manifest_path = processed_dir / "resource_manifest.json"
    catalog_path = processed_dir / "resources" / "asap_sas" / "resource_catalog.json"
    if not resource_manifest_path.exists():
        result.add_check("resource_manifest", False, f"缺少 {resource_manifest_path}")
        return
    if not catalog_path.exists():
        result.add_check("asap_resource_catalog", False, f"缺少 {catalog_path}")
        return
    try:
        resource_manifest = json.loads(resource_manifest_path.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        result.add_check("resource_catalog_json", False, f"读取失败: {exc}")
        return
    catalog_sets = catalog.get("essay_sets", {})
    missing_sets = sorted(set(required_essay_sets) - set(catalog_sets), key=lambda value: int(value))
    result.add_check("asap_required_essay_sets", not missing_sets, f"missing={missing_sets}")
    catalog_assets = {
        str(asset.get("asset_id")): asset
        for record in catalog_sets.values()
        for asset in record.get("source_assets", [])
    }
    manifest_assets = {str(asset.get("asset_id")): asset for asset in resource_manifest.get("resources", [])}
    asset_errors: list[str] = []
    for asset_id, asset in manifest_assets.items():
        relative = str(asset.get("relative_path", ""))
        path = (processed_dir / relative).resolve()
        try:
            path.relative_to(processed_dir.resolve())
        except ValueError:
            asset_errors.append(f"{asset_id}:path_escape")
            continue
        if not path.exists():
            asset_errors.append(f"{asset_id}:missing")
        elif file_sha256(path) != str(asset.get("sha256", "")):
            asset_errors.append(f"{asset_id}:hash_mismatch")
        if not str(asset.get("mime_type", "")).startswith("image/"):
            asset_errors.append(f"{asset_id}:invalid_mime")
    if set(catalog_assets) != set(manifest_assets):
        asset_errors.append("catalog_manifest_asset_id_mismatch")
    asap_items_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in all_items:
        if item.get("dataset") == "asap_sas":
            asap_items_by_set[str(item.get("metadata", {}).get("essay_set", ""))].append(item)
    for essay_set, items in asap_items_by_set.items():
        expected_ids = {str(asset.get("asset_id")) for asset in catalog_sets.get(essay_set, {}).get("source_assets", [])}
        for item in items:
            actual_ids = {str(asset.get("asset_id")) for asset in item.get("source_assets", [])}
            if actual_ids != expected_ids:
                asset_errors.append(f"{item.get('item_id')}:asset_set_mismatch")
                break
    result.add_check("source_asset_integrity", not asset_errors, "; ".join(asset_errors[:20]) or "全部图片原字节与哈希匹配")
    result.add_check(
        "model_independent_resource_manifest",
        resource_manifest.get("model_independent") is True
        and int(resource_manifest.get("model_specific_preprocessing_count", -1)) == 0,
        json.dumps(
            {
                "model_independent": resource_manifest.get("model_independent"),
                "model_specific_preprocessing_count": resource_manifest.get("model_specific_preprocessing_count"),
            },
            ensure_ascii=False,
        ),
    )


def _audit_items_semantics(
    all_items: list[dict[str, Any]],
    result: SemanticReadinessResult,
    *,
    required_essay_sets: list[str],
) -> None:
    errors: list[str] = []
    placeholder_items: list[str] = []
    model_specific_items: list[str] = []
    visible_gold_leaks: list[str] = []
    dataset_counts = Counter(str(item.get("dataset", "")) for item in all_items)
    asap_sets: set[str] = set()
    for item in all_items:
        item_id = str(item.get("item_id", ""))
        try:
            validate_item(item)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{item_id}:schema:{exc}")
            continue
        if item.get("schema_version") != "item_semantic_v2":
            errors.append(f"{item_id}:schema_version={item.get('schema_version')!r}")
        text = f"{item.get('prompt', '')}\n{item.get('rubric', '')}"
        if any(pattern.search(text) for pattern in PLACEHOLDER_PATTERNS):
            placeholder_items.append(item_id)
        model_specific = _find_key_paths(item, MODEL_SPECIFIC_KEYS)
        if model_specific:
            model_specific_items.append(f"{item_id}:{model_specific[:3]}")
        visible = project_model_visible_item(item)
        banned = find_banned_keys(visible)
        if banned:
            visible_gold_leaks.append(f"{item_id}:{banned[:3]}")
        metadata = item.get("metadata", {})
        if metadata.get("formal_eligible") is not True:
            errors.append(f"{item_id}:formal_eligible!=true")
        if metadata.get("anchor_mode") != "none":
            errors.append(f"{item_id}:anchor_mode={metadata.get('anchor_mode')!r}")

        dataset = str(item.get("dataset", ""))
        if dataset == "asap_sas":
            essay_set = str(metadata.get("essay_set", ""))
            asap_sets.add(essay_set)
            score1 = metadata.get("score1")
            if metadata.get("gold_source") != "Score1" or score1 is None or abs(float(item["gold_score"]) - float(score1)) > 1e-9:
                errors.append(f"ASAP-SAS {item_id}: gold_score 必须严格等于 Score1")
            expected_range = ASAP_SCORE_RANGES.get(essay_set)
            if expected_range is None or (float(item["score_min"]), float(item["score_max"])) != tuple(map(float, expected_range)):
                errors.append(f"ASAP-SAS {item_id}: 非法 EssaySet/score range")
            if metadata.get("training_materials_used") is not False:
                errors.append(f"ASAP-SAS {item_id}: Training_Materials Anchor 不得进入模型输入")
        elif dataset == "dress":
            dimensions = metadata.get("gold_dimensions")
            if not isinstance(dimensions, dict) or set(dimensions) != {"content", "organization", "language"}:
                errors.append(f"DREsS {item_id}: 缺少三维 Gold")
            else:
                derived = sum(float(dimensions[key]) for key in ("content", "organization", "language"))
                if abs(float(item["gold_score"]) - derived) > 1e-9:
                    errors.append(f"DREsS {item_id}: gold_score 不等于三维之和")
            if float(item["score_min"]) != 0.0 or float(item["score_max"]) != 15.0:
                errors.append(f"DREsS {item_id}: score range 必须为0..15")
        elif dataset == "sas_bench":
            manual_label = metadata.get("manual_label")
            source_total = metadata.get("source_total")
            if metadata.get("gold_source") != "manual_label" or manual_label is None:
                errors.append(f"SAS-Bench {item_id}: Gold 必须来自 manual_label")
            elif abs(float(item["gold_score"]) - float(manual_label)) > 1e-9:
                errors.append(f"SAS-Bench {item_id}: gold_score 不等于 manual_label")
            if source_total is None or abs(float(item["score_max"]) - float(source_total)) > 1e-9:
                errors.append(f"SAS-Bench {item_id}: score_max 不等于 total")
            if item.get("scoring_unit") != "whole_response" or metadata.get("scoring_unit") != "whole_response":
                errors.append(f"SAS-Bench {item_id}: scoring_unit 必须为 whole_response")
            if not isinstance(metadata.get("hidden_step_labels"), list):
                errors.append(f"SAS-Bench {item_id}: 缺少隐藏 Step labels")
        else:
            errors.append(f"{item_id}: 未批准数据集 {dataset!r}")

    missing_asap_sets = sorted(set(required_essay_sets) - asap_sets, key=lambda value: int(value))
    if missing_asap_sets:
        errors.append(f"ASAP-SAS 缺少 EssaySet: {missing_asap_sets}")
    result.add_check("item_semantic_contract", not errors, "; ".join(errors[:30]) or "三个数据集语义契约均通过")
    result.add_check("placeholder_text_count", not placeholder_items, f"count={len(placeholder_items)} examples={placeholder_items[:10]}")
    result.add_check("model_specific_preprocessing_count", not model_specific_items, f"count={len(model_specific_items)} examples={model_specific_items[:10]}")
    result.add_check("model_visible_gold_leak_count", not visible_gold_leaks, f"count={len(visible_gold_leaks)} examples={visible_gold_leaks[:10]}")
    result.summary["dataset_item_counts"] = dict(sorted(dataset_counts.items()))


def _audit_split_and_papers(
    processed_dir: Path,
    items_by_split: dict[str, list[dict[str, Any]]],
    papers_by_split: dict[str, list[dict[str, Any]]],
    result: SemanticReadinessResult,
    *,
    target_items: int,
    strict_quotas: list[dict[str, int]],
) -> None:
    all_items = [item for rows in items_by_split.values() for item in rows]
    try:
        validate_no_split_leakage(all_items)
    except Exception as exc:  # noqa: BLE001
        result.add_check("split_leakage", False, str(exc))
    else:
        result.add_check("split_leakage", True, "item、prompt、exact answer、source lineage 与 component 均无跨 split 泄漏")

    paper_errors: list[str] = []
    used_items: set[str] = set()
    paper_ids: set[str] = set()
    paper_by_item: dict[str, str] = {}
    for split, papers in papers_by_split.items():
        split_items = {str(item["item_id"]): item for item in items_by_split.get(split, [])}
        for paper in papers:
            paper_id = str(paper.get("paper_id", ""))
            if paper_id in paper_ids:
                paper_errors.append(f"duplicate_paper_id:{paper_id}")
            paper_ids.add(paper_id)
            try:
                validate_paper(paper, split_items)
            except Exception as exc:  # noqa: BLE001
                paper_errors.append(f"{paper_id}:{exc}")
                continue
            if len(paper.get("items", [])) != target_items:
                paper_errors.append(f"{paper_id}:item_count={len(paper.get('items', []))}")
            counts = Counter(str(split_items[item_id]["dataset"]) for item_id in paper.get("items", []) if item_id in split_items)
            if strict_quotas and not any(all(counts.get(dataset, 0) == count for dataset, count in quota.items()) and sum(counts.values()) == sum(quota.values()) for quota in strict_quotas):
                paper_errors.append(f"{paper_id}:strict_mix={dict(counts)}")
            if str(paper.get("metadata", {}).get("split", "")) != split:
                paper_errors.append(f"{paper_id}:metadata_split_mismatch")
            for item_id in paper.get("items", []):
                if item_id in used_items:
                    paper_errors.append(f"duplicate_item_reference:{item_id}")
                used_items.add(item_id)
                paper_by_item[item_id] = paper_id

    leftover_path = processed_dir / "external_leftover_items.csv"
    leftover_rows = read_csv(leftover_path) if leftover_path.exists() else []
    leftover_ids = {str(row.get("item_id", "")) for row in leftover_rows}
    all_item_ids = {str(item["item_id"]) for item in all_items}
    if used_items & leftover_ids:
        paper_errors.append(f"used_leftover_overlap={len(used_items & leftover_ids)}")
    if used_items | leftover_ids != all_item_ids:
        paper_errors.append(
            f"item_accounting_mismatch missing={len(all_item_ids - used_items - leftover_ids)} extra={len((used_items | leftover_ids) - all_item_ids)}"
        )
    split_manifest_path = processed_dir / "split_manifest.csv"
    if split_manifest_path.exists():
        for row in read_csv(split_manifest_path):
            item_id = str(row.get("item_id", ""))
            if str(row.get("paper_id", "")) != paper_by_item.get(item_id, ""):
                paper_errors.append(f"split_manifest_paper_id_mismatch:{item_id}")
                if len(paper_errors) >= 30:
                    break
    result.add_check("strict_paper_and_leftover_accounting", not paper_errors, "; ".join(paper_errors[:30]) or "所有 Item 恰好进入一个 strict Paper 或 leftover")
    result.summary["paper_count"] = len(paper_ids)
    result.summary["paper_used_item_count"] = len(used_items)
    result.summary["external_leftover_item_count"] = len(leftover_ids)


def _write_markdown(path: Path, result: SemanticReadinessResult) -> Path:
    lines = [
        "# Dataset Semantic V2 Semantic Readiness 报告",
        "",
        f"- run_id: `{result.run_id}`",
        f"- 状态: **{'PASS' if result.passed else 'FAIL'}**",
        f"- 阻塞错误数: {len(result.errors)}",
        f"- 警告数: {len(result.warnings)}",
        "",
        "## 门禁检查",
        "",
        "| 检查项 | 阻塞 | 状态 | 说明 |",
        "|---|---:|---:|---|",
    ]
    for check in result.checks:
        detail = str(check["detail"]).replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{check['name']}` | {'是' if check['blocking'] else '否'} | {'PASS' if check['passed'] else 'FAIL'} | {detail} |"
        )
    lines.extend(["", "## 错误", ""])
    lines.extend(f"- {error}" for error in result.errors) if result.errors else lines.append("- 无")
    lines.extend(["", "## 警告", ""])
    lines.extend(f"- {warning}" for warning in result.warnings) if result.warnings else lines.append("- 无")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def audit_semantic_readiness(
    processed_dir: str | Path,
    run_id: str,
    *,
    config_path: str | Path | None = None,
    output_root: str | Path = "outputs/runs",
    overwrite: bool = False,
) -> SemanticReadinessResult:
    processed = Path(processed_dir)
    result = SemanticReadinessResult(processed, run_id)
    config_file = Path(config_path) if config_path is not None else None
    config = read_yaml(config_file) if config_file is not None and config_file.exists() else {}
    paper_config = config.get("paper", {})
    target_items = int(paper_config.get("target_items", 5))
    strict_quotas = [
        {str(key): int(value) for key, value in quota.items()}
        for quota in paper_config.get(
            "strict_quotas",
            [{"asap_sas": 2, "sas_bench": 2, "dress": 1}, {"asap_sas": 3, "sas_bench": 1, "dress": 1}],
        )
    ]
    asap_config = next((row for row in config.get("datasets", []) if row.get("name") == "asap_sas"), {})
    required_essay_sets = [str(value) for value in asap_config.get("required_essay_sets", [str(index) for index in range(1, 11)])]

    required_files = [
        *(f"items_{split}.jsonl" for split in SPLITS),
        *(f"papers_{split}.jsonl" for split in SPLITS),
        "split_manifest.csv",
        "paper_manifest.csv",
        "external_leftover_items.csv",
        "quarantine_manifest.csv",
        "resource_manifest.json",
        "dataset_build_manifest.json",
    ]
    missing = [name for name in required_files if not (processed / name).exists()]
    result.add_check("required_artifacts", not missing, f"missing={missing}")

    items_by_split = _load_items(processed, result)
    papers_by_split = _load_papers(processed, result)
    all_items = [item for rows in items_by_split.values() for item in rows]
    build_manifest = _audit_build_manifest(processed, all_items, result, config_path=config_file)
    _audit_items_semantics(all_items, result, required_essay_sets=required_essay_sets)
    _audit_assets(processed, all_items, result, required_essay_sets=required_essay_sets)
    _audit_split_and_papers(
        processed,
        items_by_split,
        papers_by_split,
        result,
        target_items=target_items,
        strict_quotas=strict_quotas,
    )

    quarantine_path = processed / "quarantine_manifest.csv"
    quarantine_rows = read_csv(quarantine_path) if quarantine_path.exists() else []
    quarantine_errors = [index for index, row in enumerate(quarantine_rows, start=2) if not str(row.get("reason", "")).strip()]
    manifest_quarantine = int(build_manifest.get("quarantine_count", -1)) if build_manifest else -1
    result.add_check(
        "quarantine_manifest",
        not quarantine_errors and manifest_quarantine == len(quarantine_rows),
        f"rows={len(quarantine_rows)} manifest={manifest_quarantine} invalid_reason_rows={quarantine_errors[:10]}",
    )

    if all((processed / f"items_{split}.jsonl").exists() and (processed / f"papers_{split}.jsonl").exists() for split in SPLITS):
        prepared_audit = audit_prepared_data(
            processed,
            run_id,
            output_root=output_root,
            min_paper_items=target_items,
            max_paper_items=target_items,
            write_reports=False,
        )
        result.add_check(
            "legacy_prepared_audit_compatibility",
            prepared_audit.passed,
            "; ".join(prepared_audit.errors[:20]) or "兼容 prepared data 通用审计",
        )

    result.summary.update(
        {
            "status": "PASS" if result.passed else "FAIL",
            "item_count": len(all_items),
            "split_item_counts": {split: len(rows) for split, rows in items_by_split.items()},
            "quarantine_count": len(quarantine_rows),
            "resource_count": int(build_manifest.get("resource_count", 0)) if build_manifest else 0,
            "blocking_error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "online_agent_calls": 0,
            "model_downloads": 0,
            "dependency_installs": 0,
        }
    )
    manifest_payload = {
        "schema_version": "semantic_readiness_manifest_v2",
        "run_id": run_id,
        "status": "PASS" if result.passed else "FAIL",
        "summary": result.summary,
        "checks": result.checks,
        "errors": result.errors,
        "warnings": result.warnings,
        "audited_artifact_hashes": _artifact_hashes(processed, required_files),
    }
    result.manifest_path = write_json(
        processed / "semantic_readiness_manifest.json",
        manifest_payload,
        overwrite=overwrite,
    )
    report_dir = ensure_dir(Path(output_root) / run_id / "reports")
    result.json_report_path = write_json(
        report_dir / "semantic_readiness.json",
        manifest_payload,
        overwrite=overwrite,
    )
    report_path = report_dir / "semantic_readiness.md"
    if report_path.exists() and not overwrite:
        raise FileExistsError(f"输出已存在，若需覆盖请显式传入 overwrite: {report_path}")
    result.report_path = _write_markdown(report_path, result)
    return result