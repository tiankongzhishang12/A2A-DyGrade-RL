from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.selfhosted_validation import validate_selfhosted_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="验证自托管Ministral 3五题checkpoint")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--items-path", required=True)
    parser.add_argument("--transport-kind", choices=("fake", "urllib"), required=True)
    args = parser.parse_args()
    report = validate_selfhosted_checkpoint(
        run_dir=args.run_dir,
        items_path=args.items_path,
        transport_kind=args.transport_kind,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
