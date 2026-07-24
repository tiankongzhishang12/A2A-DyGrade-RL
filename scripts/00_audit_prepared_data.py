from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.audit import audit_prepared_data
from a2a_dygrade_rl.utils.cli import add_common_args, resolve_run_id
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = add_common_args(argparse.ArgumentParser(description="审计 prepared data 产物"))
    parser.add_argument("--processed-dir", required=True, help="data/processed 目录")
    parser.add_argument("--output-root", default="outputs/runs", help="run 输出根目录")
    parser.add_argument("--min-paper-items", type=int, default=5)
    parser.add_argument("--max-paper-items", type=int, default=8)
    args = parser.parse_args()

    run_id = resolve_run_id(args.run_id)
    logger = configure_run_logger("audit_prepared_data", run_id, args.output_root)
    result = audit_prepared_data(
        args.processed_dir,
        run_id,
        output_root=args.output_root,
        min_paper_items=args.min_paper_items,
        max_paper_items=args.max_paper_items,
        overwrite=args.overwrite,
    )
    logger.info("数据审计状态: %s", "PASS" if result.passed else "FAIL")
    logger.info("审计报告: %s", result.report_path)
    logger.info("分布统计: %s", result.distribution_path)
    if result.errors:
        for error in result.errors[:20]:
            logger.error(error)
        raise SystemExit(1)
    for warning in result.warnings[:20]:
        logger.warning(warning)


if __name__ == "__main__":
    main()
