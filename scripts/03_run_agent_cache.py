from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.cache import run_agent_cache
from a2a_dygrade_rl.utils.logging import configure_run_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate auditable Agent cache records")
    parser.add_argument("--config", required=True, help="Agent YAML configuration")
    parser.add_argument("--items-path", required=True, help="Prepared items JSONL")
    parser.add_argument("--split", required=True, choices=("train", "train_fit", "train_calibration", "dev", "test"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--execution-mode",
        required=True,
        choices=("fixture_smoke", "real_pilot", "formal_experiment"),
    )
    parser.add_argument("--fixture", action="store_true", help="Required acknowledgement for fixture_smoke")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--final-evaluation", action="store_true")
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--agents", nargs="+", default=None)
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--internal-item-manifest", default=None, help="train_fit/train_calibration 必需")
    parser.add_argument("--external-split-manifest", default=None, help="Formal dev/test 必需")
    parser.add_argument("--checkpoint-item-limit", type=int, default=None, help="在固定样本范围内仅执行前N个Item")
    parser.add_argument("--concurrency", type=int, default=None, help="Item级并发；默认读取provider.concurrency")
    parser.add_argument("--max-total-calls-override", type=int, default=None, help="real_pilot recovery runtime call cap; cache identity unchanged")
    args = parser.parse_args()

    expected_fixture = args.execution_mode == "fixture_smoke"
    if args.fixture != expected_fixture:
        parser.error("--fixture must be set exactly when --execution-mode=fixture_smoke")
    result = run_agent_cache(
        config_path=args.config,
        items_path=args.items_path,
        split=args.split,
        run_id=args.run_id,
        execution_mode=args.execution_mode,
        seed=args.seed,
        sample_size=args.sample_size,
        agents=args.agents,
        resume=args.resume,
        final_evaluation=args.final_evaluation,
        output_root=args.output_root,
        internal_item_manifest_path=args.internal_item_manifest,
        external_split_manifest_path=args.external_split_manifest,
        checkpoint_item_limit=args.checkpoint_item_limit,
        concurrency=args.concurrency,
        max_total_calls_override=args.max_total_calls_override,
    )
    logger = configure_run_logger("run_agent_cache", args.run_id, args.output_root)
    logger.info(
        "Agent cache complete: split=%s items=%s generated=%s reused=%s failures=%s",
        args.split,
        result["item_count"],
        result["generated"],
        result["reused"],
        result["failures"],
    )


if __name__ == "__main__":
    main()
