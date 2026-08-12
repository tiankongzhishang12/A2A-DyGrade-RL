from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.internal_split import build_internal_split
from a2a_dygrade_rl.utils.cli import add_common_args, resolve_run_id
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = add_common_args(argparse.ArgumentParser(description="构建 V1.4 train_fit/train_calibration Item component 拆分"))
    parser.add_argument("--items", default="data/processed/semantic_v2/items_train.jsonl", help="外部 train Item JSONL")
    parser.add_argument("--paper-manifest", default="data/processed/semantic_v2/paper_manifest.csv", help="外部 Paper manifest")
    parser.add_argument("--output-dir", default="data/processed/semantic_v2", help="数据型产物目录")
    parser.add_argument("--output-root", default="outputs/runs", help="run 产物根目录")
    args = parser.parse_args()
    if args.sample_size is not None:
        raise ValueError("正式 internal split 不允许任意截断 Item；fixture smoke 请运行 pytest fixture")
    run_id = resolve_run_id(args.run_id)
    logger = configure_run_logger("build_internal_split", run_id, output_root=args.output_root)
    outputs = build_internal_split(
        args.config,
        args.items,
        args.paper_manifest,
        args.output_dir,
        run_id,
        seed=args.seed,
        overwrite=args.overwrite,
        output_root=args.output_root,
    )
    logger.info("internal item manifest: %s", outputs["manifest"])
    logger.info("internal split summary: %s", outputs["result"].summary)


if __name__ == "__main__":
    main()
