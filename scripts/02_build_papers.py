from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.build_papers import build_papers
from a2a_dygrade_rl.utils.cli import add_common_args, resolve_run_id
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = add_common_args(argparse.ArgumentParser(description="构建 Dataset Semantic V2 外部 strict Paper"))
    parser.add_argument("--input-dir", default="data/processed/semantic_v2")
    parser.add_argument("--output-dir", default="data/processed/semantic_v2")
    parser.add_argument("--output-root", default="outputs/runs")
    args = parser.parse_args()
    run_id = resolve_run_id(args.run_id)
    logger = configure_run_logger("build_papers", run_id, args.output_root)
    paths = build_papers(
        args.config,
        args.input_dir,
        args.output_dir,
        run_id,
        args.seed,
        args.overwrite,
        output_root=args.output_root,
    )
    logger.info("已生成 Semantic V2 Paper/leftover: %s", {key: str(value) for key, value in paths.items()})


if __name__ == "__main__":
    main()