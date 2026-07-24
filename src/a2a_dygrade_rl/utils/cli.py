"""通用 CLI 参数。"""

from __future__ import annotations

import argparse
from datetime import datetime


def add_common_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--config", required=True, help="配置文件路径")
    parser.add_argument("--run-id", default=None, help="唯一运行标识")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    parser.add_argument("--sample-size", type=int, default=None, help="smoke 小样本数量")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖已有输出")
    return parser


def resolve_run_id(run_id: str | None) -> str:
    if run_id:
        return run_id
    return "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
