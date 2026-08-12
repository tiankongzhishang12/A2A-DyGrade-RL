from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.semantic_readiness import audit_semantic_readiness
from a2a_dygrade_rl.utils.cli import add_common_args, resolve_run_id
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = add_common_args(argparse.ArgumentParser(description="执行 Dataset Semantic V2 fail-closed Semantic Readiness 审计"))
    parser.add_argument("--processed-dir", default="data/processed/semantic_v2")
    parser.add_argument("--output-root", default="outputs/runs")
    args = parser.parse_args()
    if args.sample_size is not None:
        raise ValueError("Semantic Readiness 不接受任意 sample_size；smoke 请使用独立 fixture 目录")
    run_id = resolve_run_id(args.run_id)
    logger = configure_run_logger("semantic_readiness", run_id, args.output_root)
    result = audit_semantic_readiness(
        args.processed_dir,
        run_id,
        config_path=args.config,
        output_root=args.output_root,
        overwrite=args.overwrite,
    )
    logger.info("Semantic Readiness: %s", "PASS" if result.passed else "FAIL")
    logger.info("manifest: %s", result.manifest_path)
    logger.info("report: %s", result.report_path)
    for warning in result.warnings[:20]:
        logger.warning(warning)
    if result.errors:
        for error in result.errors[:20]:
            logger.error(error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()