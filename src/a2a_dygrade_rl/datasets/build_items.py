"""Dataset Semantic V2 Item 构建编排。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.dataset_result import DatasetLoadResult, QUARANTINE_FIELDS
from a2a_dygrade_rl.datasets.load_asap_sas import load_asap_sas_result
from a2a_dygrade_rl.datasets.load_dress import load_dress_result
from a2a_dygrade_rl.datasets.load_sas_bench import load_sas_bench_result
from a2a_dygrade_rl.datasets.split import assign_prompt_splits, write_split_items
from a2a_dygrade_rl.utils.io import (
    copy_config_snapshot,
    file_sha256,
    read_yaml,
    write_csv,
    write_json,
)


RESULT_LOADERS = {
    "dress": load_dress_result,
    "asap_sas": load_asap_sas_result,
    "sas_bench": load_sas_bench_result,
}


def _preflight_output(output: Path, *, overwrite: bool) -> None:
    if overwrite:
        return
    candidates = [
        output / "items_train.jsonl",
        output / "items_dev.jsonl",
        output / "items_test.jsonl",
        output / "split_manifest.csv",
        output / "quarantine_manifest.csv",
        output / "resource_manifest.json",
        output / "dataset_build_manifest.json",
    ]
    existing = [str(path) for path in candidates if path.exists()]
    resources = output / "resources"
    if resources.exists() and any(path.is_file() for path in resources.rglob("*")):
        existing.append(str(resources))
    if existing:
        raise FileExistsError(f"Semantic V2 输出已存在，若需覆盖请显式传入 overwrite: {existing[:10]}")


def _load_dataset_result(
    dataset_config: dict[str, Any],
    *,
    resources_root: Path,
    overwrite: bool,
) -> DatasetLoadResult:
    name = str(dataset_config["name"])
    loader = RESULT_LOADERS.get(name)
    if loader is None:
        raise ValueError(f"未注册数据集 loader: {name}")
    if name == "asap_sas":
        return load_asap_sas_result(dataset_config, resources_root=resources_root, overwrite=overwrite)
    return loader(dataset_config)


def _artifact_record(path: Path, output: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(output).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": file_sha256(path),
    }


def build_items(
    config_path: str | Path,
    output_dir: str | Path,
    run_id: str,
    sample_size: int | None = None,
    seed: int | None = None,
    overwrite: bool = False,
    output_root: str | Path = "outputs/runs",
) -> dict[str, Path]:
    config_path = Path(config_path)
    output = Path(output_dir)
    _preflight_output(output, overwrite=overwrite)
    config = read_yaml(config_path)
    effective_seed = int(seed if seed is not None else config.get("run", {}).get("seed", 42))
    rule_version = str(config.get("run", {}).get("rule_version", "dataset_semantic_v2"))
    resources_root = output / "resources"

    results: list[DatasetLoadResult] = []
    items: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    resources: list[dict[str, Any]] = []
    for dataset_config in config.get("datasets", []):
        if dataset_config.get("enabled", True) is False:
            continue
        result = _load_dataset_result(dataset_config, resources_root=resources_root, overwrite=overwrite)
        results.append(result)
        items.extend(result.items)
        quarantine.extend(result.quarantine)
        resources.extend(result.resources)

    if sample_size is not None:
        if sample_size <= 0:
            raise ValueError("sample_size 必须为正整数")
        items = items[:sample_size]
    if not items:
        raise ValueError("没有找到可构建的 raw item。请先准备本地数据，或使用 tests fixtures 做 smoke。")

    duplicate_item_ids = sorted(item_id for item_id, count in Counter(str(item["item_id"]) for item in items).items() if count > 1)
    if duplicate_item_ids:
        raise ValueError(f"构建前发现重复 item_id: {duplicate_item_ids[:20]}")

    split_items = assign_prompt_splits(items, config.get("splits", {}), effective_seed, rule_version)
    paths = write_split_items(split_items, output, overwrite=overwrite)
    paths["quarantine_manifest"] = write_csv(
        output / "quarantine_manifest.csv",
        sorted(
            quarantine,
            key=lambda row: (
                str(row.get("dataset", "")),
                str(row.get("source_file", "")),
                str(row.get("source_record_id", "")),
                str(row.get("reason", "")),
            ),
        ),
        QUARANTINE_FIELDS,
        overwrite=overwrite,
    )
    unique_resources = {
        str(resource.get("asset_id")): dict(resource)
        for resource in resources
        if str(resource.get("asset_id", ""))
    }
    resource_manifest = {
        "schema_version": "source_asset_manifest_v2",
        "model_independent": True,
        "model_specific_preprocessing_count": 0,
        "resource_count": len(unique_resources),
        "resources": [unique_resources[key] for key in sorted(unique_resources)],
    }
    paths["resource_manifest"] = write_json(
        output / "resource_manifest.json",
        resource_manifest,
        overwrite=overwrite,
    )

    split_counts = Counter(str(item["metadata"]["split"]) for item in split_items)
    split_dataset_counts: dict[str, dict[str, int]] = {}
    for split in ("train", "dev", "test"):
        counts = Counter(str(item["dataset"]) for item in split_items if item["metadata"]["split"] == split)
        split_dataset_counts[split] = dict(sorted(counts.items()))
    quarantine_counts = Counter(str(row.get("dataset", "")) for row in quarantine)
    source_files = []
    for result in results:
        source_files.extend({"dataset": result.dataset, **record} for record in result.source_files)

    artifacts = {
        key: _artifact_record(path, output)
        for key, path in paths.items()
        if key != "dataset_build_manifest"
    }
    build_manifest = {
        "schema_version": "dataset_build_manifest_v2",
        "run_id": run_id,
        "execution_mode": "data_preparation",
        "formal_eligible": sample_size is None,
        "sample_size": sample_size,
        "item_schema_version": "item_semantic_v2",
        "split_rule_version": rule_version,
        "seed": effective_seed,
        "config": {
            "path": config_path.as_posix(),
            "sha256": file_sha256(config_path),
        },
        "dataset_results": [result.manifest_entry() for result in results],
        "source_files": source_files,
        "accepted_item_count": len(split_items),
        "accepted_by_dataset": dict(sorted(Counter(str(item["dataset"]) for item in split_items).items())),
        "split_counts": dict(sorted(split_counts.items())),
        "split_dataset_counts": split_dataset_counts,
        "quarantine_count": len(quarantine),
        "quarantine_by_dataset": dict(sorted(quarantine_counts.items())),
        "resource_count": len(unique_resources),
        "artifacts": artifacts,
        "safety_counters": {
            "online_agent_calls": 0,
            "model_downloads": 0,
            "dependency_installs": 0,
            "raw_data_writes": 0,
            "training_material_anchor_reads": 0,
            "model_specific_preprocessing_records": 0,
        },
    }
    paths["dataset_build_manifest"] = write_json(
        output / "dataset_build_manifest.json",
        build_manifest,
        overwrite=overwrite,
    )
    copy_config_snapshot(config_path, run_id, output_root=output_root)
    return paths