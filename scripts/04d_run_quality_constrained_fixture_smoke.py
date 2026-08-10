from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.rl.fixture_smoke import run_quality_constrained_fixture_smoke


def main() -> None:
    parser = argparse.ArgumentParser(description="运行隔离的完整质量约束 Fixture Smoke")
    parser.add_argument("--config", default="configs/experiments/fixture_smoke.yaml")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", default="outputs/runs")
    args = parser.parse_args()
    result = run_quality_constrained_fixture_smoke(
        config_path=args.config,
        run_id=args.run_id,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
