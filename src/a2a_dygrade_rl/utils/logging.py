"""运行日志工具。"""

from __future__ import annotations

import logging
from pathlib import Path

from a2a_dygrade_rl.utils.io import ensure_dir


def configure_run_logger(name: str, run_id: str, output_root: str | Path = "outputs/runs") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    log_dir = ensure_dir(Path(output_root) / run_id / "logs")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_dir / f"{name}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger
