"""公开评分数据集的通用本地文件 loader。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from a2a_dygrade_rl.datasets.normalize import normalize_record


def read_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        with path.open("r", encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("items", "records", "data"):
                if isinstance(data.get(key), list):
                    return data[key]
        raise ValueError(f"无法识别 JSON 数据结构: {path}")
    if path.suffix.lower() in {".csv", ".tsv"}:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle, delimiter=delimiter))
    raise ValueError(f"不支持的数据文件类型: {path}")


def load_dataset(dataset_config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(dataset_config["raw_path"])
    pattern = dataset_config.get("pattern", "*.jsonl")
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob(pattern)):
        for record in read_records(path):
            rows.append(normalize_record(record, dataset_config))
    return rows
