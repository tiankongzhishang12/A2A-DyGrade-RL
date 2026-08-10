"""评分质量指标；正式 QWK 固定使用0..10共11档。"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class QWKComputation:
    qwk: float | None
    weighted_observed_disagreement: float
    expected_weighted_disagreement: float
    labels: tuple[int, ...]


def _paired_values(y_true: Sequence[float], y_pred: Sequence[float]) -> tuple[Sequence[float], Sequence[float]]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true 与 y_pred 长度必须一致")
    if not y_true:
        raise ValueError("指标至少需要一个样本")
    return y_true, y_pred


def mae(y_true: list[float], y_pred: list[float]) -> float:
    _paired_values(y_true, y_pred)
    return sum(abs(a - b) for a, b in zip(y_true, y_pred)) / len(y_true)


def rmse(y_true: list[float], y_pred: list[float]) -> float:
    _paired_values(y_true, y_pred)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / len(y_true))


def within_1_accuracy(y_true: list[float], y_pred: list[float]) -> float:
    _paired_values(y_true, y_pred)
    return sum(abs(a - b) <= 1 for a, b in zip(y_true, y_pred)) / len(y_true)


def quadratic_weighted_kappa_details(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    *,
    labels: Iterable[int] = range(11),
) -> QWKComputation:
    _paired_values(y_true, y_pred)
    fixed_labels = tuple(int(label) for label in labels)
    if len(fixed_labels) < 2 or len(set(fixed_labels)) != len(fixed_labels):
        raise ValueError("QWK labels 必须包含至少两个不重复标签")
    index = {label: position for position, label in enumerate(fixed_labels)}
    unknown = sorted((set(y_true) | set(y_pred)) - set(fixed_labels))
    if unknown:
        raise ValueError(f"QWK 输入存在固定 labels 之外的值: {unknown}")

    true_hist = Counter(int(value) for value in y_true)
    pred_hist = Counter(int(value) for value in y_pred)
    observed = Counter((int(truth), int(pred)) for truth, pred in zip(y_true, y_pred))
    total = float(len(y_true))
    denominator = float((len(fixed_labels) - 1) ** 2)
    weighted_observed = 0.0
    weighted_expected = 0.0
    for true_label in fixed_labels:
        true_index = index[true_label]
        for pred_label in fixed_labels:
            pred_index = index[pred_label]
            weight = ((true_index - pred_index) ** 2) / denominator
            weighted_observed += weight * observed[(true_label, pred_label)] / total
            weighted_expected += weight * (true_hist[true_label] * pred_hist[pred_label]) / (total * total)
    qwk = None if weighted_expected <= 0.0 else 1.0 - (weighted_observed / weighted_expected)
    return QWKComputation(
        qwk=qwk,
        weighted_observed_disagreement=weighted_observed,
        expected_weighted_disagreement=weighted_expected,
        labels=fixed_labels,
    )


def quadratic_weighted_kappa(
    y_true: list[int],
    y_pred: list[int],
    *,
    labels: Iterable[int] = range(11),
) -> float:
    """正式 QWK；默认固定 label set 为0..10，不再按样本标签 union 缩放。"""

    result = quadratic_weighted_kappa_details(y_true, y_pred, labels=labels)
    if result.qwk is None:
        raise ValueError("QWK expected weighted disagreement 必须大于0")
    return result.qwk
