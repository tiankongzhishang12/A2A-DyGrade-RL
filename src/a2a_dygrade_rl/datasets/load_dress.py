from __future__ import annotations

import csv
from pathlib import Path

from a2a_dygrade_rl.datasets.load_common import load_dataset
from a2a_dygrade_rl.datasets.normalize import normalize_record


MAIN_FILES = ("DREsS_Std.tsv", "DREsS_New.tsv")


def _is_number(value: str | None) -> bool:
    if value is None or not str(value).strip():
        return False
    try:
        float(value)
    except ValueError:
        return False
    return True


def _valid_main_row(row: dict[str, str]) -> bool:
    required_text = ("id", "prompt", "essay")
    required_scores = ("content", "organization", "language", "total")
    if any(not (row.get(field) or "").strip() for field in required_text):
        return False
    if any(not _is_number(row.get(field)) for field in required_scores):
        return False
    dimensions = float(row["content"]) + float(row["organization"]) + float(row["language"])
    return abs(dimensions - float(row["total"])) <= 1e-6


def load_dress(dataset_config):
    root = Path(dataset_config["raw_path"])
    if not root.exists():
        return []
    if not any((root / filename).exists() for filename in MAIN_FILES):
        return load_dataset(dataset_config)
    rows = []
    for filename in MAIN_FILES:
        path = root / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if not _valid_main_row(row):
                    continue
                source = row.get("source") or path.stem
                item = normalize_record(
                    {
                        "id": f"{path.stem}_{row['id']}",
                        "prompt_id": f"dress_{source}_{row['prompt'][:80]}",
                        "prompt": row["prompt"],
                        "answer": row["essay"],
                        "rubric": "DREsS analytic essay scoring with content, organization, and language dimensions.",
                        "score": float(row["total"]),
                        "score_min": dataset_config.get("score_min", 0),
                        "score_max": dataset_config.get("score_max", 15),
                        "question_type": dataset_config.get("question_type", "essay"),
                        "subject": "writing",
                    },
                    dataset_config,
                )
                item["metadata"].update(
                    {
                        "source_file": path.name,
                        "source": source,
                        "content_score": float(row["content"]),
                        "organization_score": float(row["organization"]),
                        "language_score": float(row["language"]),
                        "total_score": float(row["total"]),
                    }
                )
                rows.append(item)
    return rows
