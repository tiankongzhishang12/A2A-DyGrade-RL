from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.selfhosted_runtime import run_selfhosted_checkpoint_cache


def main() -> None:
    parser = argparse.ArgumentParser(description="运行自托管Ministral 3五题checkpoint cache")
    parser.add_argument("--config", default="configs/experiments/selfhosted_ministral3_checkpoint.yaml")
    parser.add_argument("--items-path", required=True)
    parser.add_argument("--internal-item-manifest", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--transport", choices=("fake", "urllib"), default="fake")
    parser.add_argument("--fixture", action="store_true", help="使用fake transport时必须显式确认")
    parser.add_argument("--server-approved", action="store_true", help="真实urllib服务器阶段必须显式确认")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--agents", nargs="+", choices=("CheapAgent", "MidAgent", "StrongAgent"))
    parser.add_argument("--output-root", default="outputs/runs")
    args = parser.parse_args()
    if args.fixture != (args.transport == "fake"):
        parser.error("--fixture 必须且只能与 --transport=fake 同时使用")
    if args.transport == "urllib" and not args.server_approved:
        parser.error("真实urllib运行必须显式传入 --server-approved")
    result = run_selfhosted_checkpoint_cache(
        config_path=args.config,
        items_path=args.items_path,
        internal_item_manifest_path=args.internal_item_manifest,
        run_id=args.run_id,
        transport_kind=args.transport,
        resume=args.resume,
        output_root=args.output_root,
        server_approved=args.server_approved,
        agents=args.agents,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, ensure_ascii=False, sort_keys=True, indent=2))
    if int(result.get("failures", 0)) > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
