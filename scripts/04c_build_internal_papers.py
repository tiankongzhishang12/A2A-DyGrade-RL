from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.datasets.audit_internal_split import audit_internal_split_artifacts, write_internal_split_audit
from a2a_dygrade_rl.datasets.build_internal_papers import build_internal_paper_artifacts
from a2a_dygrade_rl.utils.cli import add_common_args, resolve_run_id
from a2a_dygrade_rl.utils.io import read_yaml
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = add_common_args(argparse.ArgumentParser(description="分别重建并审计 train_fit/train_calibration strict Paper"))
    parser.add_argument("--items", default="data/processed/semantic_v2/items_train.jsonl", help="外部 train Item JSONL")
    parser.add_argument("--internal-item-manifest", default="data/processed/semantic_v2/internal_item_split_manifest.csv")
    parser.add_argument("--external-paper-manifest", default="data/processed/semantic_v2/paper_manifest.csv")
    parser.add_argument("--output-dir", default="data/processed/semantic_v2", help="数据型产物目录")
    parser.add_argument("--output-root", default="outputs/runs", help="run 产物根目录")
    args = parser.parse_args()
    if args.sample_size is not None:
        raise ValueError("正式 strict Paper rebuild 不允许任意截断 Item；fixture smoke 请运行 pytest fixture")
    run_id = resolve_run_id(args.run_id)
    logger = configure_run_logger("build_internal_papers", run_id, output_root=args.output_root)
    result, paths = build_internal_paper_artifacts(
        args.config,
        args.items,
        args.internal_item_manifest,
        args.output_dir,
        run_id,
        seed=args.seed,
        overwrite=args.overwrite,
        output_root=args.output_root,
    )
    config = read_yaml(args.config)
    audit = audit_internal_split_artifacts(
        items_path=args.items,
        item_manifest_path=args.internal_item_manifest,
        papers_train_fit_path=paths["train_fit"],
        papers_train_calibration_path=paths["train_calibration"],
        paper_manifest_path=paths["paper_manifest"],
        leftover_path=paths["leftovers"],
        strict_quotas=config.get("paper", {}).get("strict_quotas", []),
        external_paper_manifest_path=args.external_paper_manifest,
    )
    report_paths = write_internal_split_audit(audit, run_id, output_root=args.output_root, overwrite=args.overwrite)
    logger.info("internal Paper build summary: %s", result.summary)
    logger.info("internal split audit: %s", audit.summary)
    logger.info("audit reports: %s", {key: str(value) for key, value in report_paths.items()})
    if not audit.passed:
        raise SystemExit("内部 split/Paper 阻塞性审计失败；详见 run reports")


if __name__ == "__main__":
    main()
