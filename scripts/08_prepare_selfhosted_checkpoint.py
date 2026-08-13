from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.selfhosted_checkpoint import build_selfhosted_checkpoint_sample


def main() -> None:
    parser = argparse.ArgumentParser(description="构建自托管Ministral 3固定5题checkpoint样本")
    parser.add_argument("--papers-path", default="data/processed/semantic_v2/papers_train_fit.jsonl")
    parser.add_argument("--items-path", default="data/processed/semantic_v2/items_train.jsonl")
    parser.add_argument("--internal-item-manifest", default="data/processed/semantic_v2/internal_item_split_manifest.csv")
    parser.add_argument("--semantic-readiness-manifest", default="data/processed/semantic_v2/semantic_readiness_manifest.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--output-root", default="outputs/runs")
    args = parser.parse_args()
    result = build_selfhosted_checkpoint_sample(
        papers_path=args.papers_path,
        items_path=args.items_path,
        internal_manifest_path=args.internal_item_manifest,
        semantic_readiness_manifest_path=args.semantic_readiness_manifest,
        run_id=args.run_id,
        seed=args.seed,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
