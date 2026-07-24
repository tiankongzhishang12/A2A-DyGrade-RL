"""评分质量指标。"""

from __future__ import annotations

import math
from collections import Counter


def mae(y_true: list[float], y_pred: list[float]) -> float:
    return sum(abs(a - b) for a, b in zip(y_true, y_pred)) / len(y_true)


def rmse(y_true: list[float], y_pred: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / len(y_true))


def within_1_accuracy(y_true: list[float], y_pred: list[float]) -> float:
    return sum(abs(a - b) <= 1 for a, b in zip(y_true, y_pred)) / len(y_true)


def quadratic_weighted_kappa(y_true: list[int], y_pred: list[int]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    if not labels:
        raise ValueError("QWK 至少需要一个样本")
    if len(labels) == 1:
        return 1.0
    index = {label: i for i, label in enumerate(labels)}
    n = len(labels)
    observed = [[0.0 for _ in range(n)] for _ in range(n)]
    for truth, pred in zip(y_true, y_pred):
        observed[index[truth]][index[pred]] += 1.0
    true_hist = Counter(y_true)
    pred_hist = Counter(y_pred)
    total = float(len(y_true))
    weighted_observed = 0.0
    weighted_expected = 0.0
    for i, true_label in enumerate(labels):
        for j, pred_label in enumerate(labels):
            weight = ((i - j) ** 2) / ((n - 1) ** 2)
            weighted_observed += weight * observed[i][j] / total
            weighted_expected += weight * (true_hist[true_label] * pred_hist[pred_label]) / (total * total)
    if weighted_expected == 0:
        return 1.0
    return 1.0 - (weighted_observed / weighted_expected)
