from __future__ import annotations

import csv
from pathlib import Path

from a2a_dygrade_rl.datasets.normalize import normalize_record


ASAP_SCORE_RANGES = {
    "1": (0, 3),
    "2": (0, 3),
    "3": (0, 2),
    "4": (0, 2),
    "5": (0, 3),
    "6": (0, 3),
    "7": (0, 2),
    "8": (0, 2),
    "9": (0, 2),
    "10": (0, 2),
}


def load_asap_sas(dataset_config):
    root = Path(dataset_config["raw_path"])
    if not root.exists():
        return []
    rows = []
    train_files = [root / "train_rel_2.tsv"] if (root / "train_rel_2.tsv").exists() else [root / "train.tsv"]
    for path in train_files:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for record in csv.DictReader(handle, delimiter="\t"):
                if not {"Id", "EssaySet", "Score1", "Score2", "EssayText"} <= set(record):
                    continue
                essay_set = str(record["EssaySet"]).strip()
                score_min, score_max = ASAP_SCORE_RANGES.get(
                    essay_set,
                    (dataset_config.get("score_min", 0), dataset_config.get("score_max", 3)),
                )
                score1 = float(record["Score1"])
                score2 = float(record["Score2"])
                rows.append(
                    normalize_record(
                        {
                            "id": f"{Path(path).stem}_{record['Id']}",
                            "prompt_id": f"asap_sas_set_{essay_set}",
                            "prompt": f"ASAP-SAS EssaySet {essay_set} prompt. See Data_Set_Descriptions.zip for the official prompt text.",
                            "answer": record["EssayText"],
                            "rubric": f"ASAP-SAS EssaySet {essay_set} scoring rubric. See Training_Materials.zip anchor papers and Data_Set_Descriptions.zip.",
                            "score": (score1 + score2) / 2.0,
                            "score_min": score_min,
                            "score_max": score_max,
                            "question_type": dataset_config.get("question_type", "short_answer"),
                            "subject": "science",
                            "source_file": path.name,
                            "score1": score1,
                            "score2": score2,
                        },
                        dataset_config,
                    )
                )
    return rows
