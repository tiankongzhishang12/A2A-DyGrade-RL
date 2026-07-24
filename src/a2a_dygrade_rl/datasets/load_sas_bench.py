from __future__ import annotations

import json
from pathlib import Path

from a2a_dygrade_rl.datasets.normalize import normalize_record


def _question_type_from_name(path: Path) -> str:
    name = path.stem.lower()
    if "choice" in name:
        return "choice"
    if "gapfilling" in name:
        return "gap_filling"
    return "short_answer"


def _subject_from_name(path: Path) -> str:
    parts = path.stem.split("_")
    return parts[1] if len(parts) > 1 else ""


def load_sas_bench(dataset_config):
    root = Path(dataset_config["raw_path"])
    pattern = dataset_config.get("pattern", "*.jsonl")
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob(pattern)):
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict) or not {"id", "question", "steps"} <= set(record):
                    continue
                question_id = str(record["id"])
                for step_index, step in enumerate(record.get("steps", [])):
                    response = str(step.get("response", "")).strip()
                    if not response:
                        continue
                    label = float(step.get("label", 0))
                    score_max = max(
                        float(record.get("total") or 0),
                        label,
                        float(dataset_config.get("score_max", 5)),
                    )
                    rows.append(
                        normalize_record(
                            {
                                "id": f"{Path(path).stem}_{question_id}_step_{step_index}",
                                "prompt_id": question_id,
                                "prompt": record.get("question", ""),
                                "answer": response,
                                "reference": record.get("reference", ""),
                                "rubric": record.get("analysis", "") or "SAS-Bench step-wise scoring annotation.",
                                "score": label,
                                "score_min": 0,
                                "score_max": score_max,
                                "question_type": _question_type_from_name(path),
                                "subject": _subject_from_name(path),
                            },
                            dataset_config,
                        )
                    )
                    rows[-1]["metadata"].update(
                        {
                            "source_file": path.name,
                            "question_id": question_id,
                            "step_index": step_index,
                            "errors": step.get("errors", []),
                            "manual_label": record.get("manual_label"),
                            "total_score": record.get("total"),
                        }
                    )
    return rows
