from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.build_papers import build_papers
from a2a_dygrade_rl.utils.cli import add_common_args, resolve_run_id
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = add_common_args(argparse.ArgumentParser(description="构建 paper-level 样本"))
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    run_id = resolve_run_id(args.run_id)
    logger = configure_run_logger("build_papers", run_id)
    paths = build_papers(args.config, args.input_dir, args.output_dir, run_id, args.seed, args.overwrite)
    logger.info("已生成 paper split: %s", {key: str(value) for key, value in paths.items()})


if __name__ == "__main__":
    main()
