from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.pilot import build_real_pilot_sample


def main() -> None:
    parser = argparse.ArgumentParser(description="构建100 Item真实Agent Pilot固定样本")
    parser.add_argument("--papers-path", default="data/processed/papers_train_fit.jsonl")
    parser.add_argument("--items-path", default="data/processed/items_train.jsonl")
    parser.add_argument("--internal-item-manifest", default="data/processed/internal_item_split_manifest.csv")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--paper-count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-root", default="outputs/runs")
    args = parser.parse_args()
    result = build_real_pilot_sample(
        papers_path=args.papers_path,
        items_path=args.items_path,
        internal_manifest_path=args.internal_item_manifest,
        run_id=args.run_id,
        paper_count=args.paper_count,
        seed=args.seed,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
