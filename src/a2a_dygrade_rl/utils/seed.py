"""确定性随机种子工具。"""

from __future__ import annotations

import os
import random


def set_seed(seed: int) -> random.Random:
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    return random.Random(seed)
