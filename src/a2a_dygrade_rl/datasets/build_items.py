"""item 构建编排。"""

from __future__ import annotations

from pathlib import Path

from a2a_dygrade_rl.datasets.load_asap_sas import load_asap_sas
from a2a_dygrade_rl.datasets.load_dress import load_dress
from a2a_dygrade_rl.datasets.load_sas_bench import load_sas_bench
from a2a_dygrade_rl.datasets.split import assign_prompt_splits, write_split_items
from a2a_dygrade_rl.utils.io import copy_config_snapshot, read_yaml

LOADERS = {
    "dress": load_dress,
    "asap_sas": load_asap_sas,
    "sas_bench": load_sas_bench,
}


def build_items(config_path: str | Path, output_dir: str | Path, run_id: str, sample_size: int | None = None, seed: int | None = None, overwrite: bool = False) -> dict[str, Path]:
    config = read_yaml(config_path)
    effective_seed = int(seed if seed is not None else config.get("run", {}).get("seed", 42))
    rule_version = str(config.get("run", {}).get("rule_version", "v1"))
    items: list[dict] = []
    for dataset_config in config.get("datasets", []):
        if dataset_config.get("enabled", True) is False:
            continue
        loader = LOADERS.get(str(dataset_config["name"]))
        if loader is None:
            raise ValueError(f"未注册数据集 loader: {dataset_config['name']}")
        items.extend(loader(dataset_config))
    if sample_size is not None:
        items = items[:sample_size]
    if not items:
        raise ValueError("没有找到可构建的 raw item。请先把公开数据放入 data/raw/<dataset>/，或使用 tests fixtures 做 smoke。")
    split_items = assign_prompt_splits(items, config.get("splits", {}), effective_seed, rule_version)
    paths = write_split_items(split_items, output_dir, overwrite=overwrite)
    copy_config_snapshot(config_path, run_id)
    return paths
