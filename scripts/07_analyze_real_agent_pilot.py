from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.pilot_analysis import analyze_pilot


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the completed real Agent Pilot")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--split", default="train_fit")
    parser.add_argument("--pricing-manifest", default=None)
    args = parser.parse_args()
    result = analyze_pilot(
        args.run_dir,
        split=args.split,
        pricing_manifest_path=args.pricing_manifest,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
