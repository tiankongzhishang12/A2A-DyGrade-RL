from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.capability import build_formal_capability_profiles, calibrate_capability_support
from a2a_dygrade_rl.utils.io import read_jsonl, write_jsonl


def _read_jsonl_file_or_directory(value: str) -> list[dict]:
    path = Path(value)
    if path.is_file():
        return read_jsonl(path)
    if path.is_dir():
        rows = []
        for child in sorted(path.glob("*.jsonl")):
            rows.extend(read_jsonl(child))
        if rows:
            return rows
    raise ValueError(f"未找到可读取的 JSONL 文件或目录: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建 train_fit 正式能力画像并在 train_calibration 校准支持度边界")
    parser.add_argument("--train-fit-items", required=True)
    parser.add_argument("--train-fit-cache", required=True)
    parser.add_argument("--train-fit-difficulty", required=True)
    parser.add_argument("--train-calibration-items", required=True)
    parser.add_argument("--train-calibration-cache", required=True)
    parser.add_argument("--train-calibration-difficulty", required=True)
    parser.add_argument("--internal-manifest-hash", required=True)
    parser.add_argument("--cache-hash", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--support-quantile", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=20260729)
    args = parser.parse_args()

    output_dir = Path(args.output_root) / args.run_id / "reports"
    profiles = build_formal_capability_profiles(
        read_jsonl(args.train_fit_items),
        _read_jsonl_file_or_directory(args.train_fit_cache),
        read_jsonl(args.train_fit_difficulty),
    )
    write_jsonl(output_dir / "agent_capability_profiles.jsonl", profiles, overwrite=True)
    calibrate_capability_support(
        profiles,
        read_jsonl(args.train_calibration_items),
        _read_jsonl_file_or_directory(args.train_calibration_cache),
        read_jsonl(args.train_calibration_difficulty),
        support_quantile=args.support_quantile,
        internal_manifest_hash=args.internal_manifest_hash,
        cache_hash=args.cache_hash,
        seed=args.seed,
        output_path=output_dir / "agent_capability_manifest.json",
    )


if __name__ == "__main__":
    main()
