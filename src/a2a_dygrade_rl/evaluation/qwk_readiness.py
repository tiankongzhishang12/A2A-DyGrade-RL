"""固定11档 QWK 的 half-up 映射与 readiness。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from a2a_dygrade_rl.evaluation.metrics_quality import quadratic_weighted_kappa_details
from a2a_dygrade_rl.utils.schemas import QWKReadinessRecord


FIXED_LABELS = tuple(range(11))


def score_to_fixed_bin(score: float, score_min: float, score_max: float) -> int:
    try:
        value = Decimal(str(score))
        minimum = Decimal(str(score_min))
        maximum = Decimal(str(score_max))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("QWK 分档输入必须为合法数值") from exc
    if not all(number.is_finite() for number in (value, minimum, maximum)):
        raise ValueError("QWK 分档输入必须为有限数值")
    if maximum <= minimum:
        raise ValueError("score_max 必须大于 score_min")
    if not minimum <= value <= maximum:
        raise ValueError("QWK 分档分数越界")
    normalized = (value - minimum) / (maximum - minimum)
    mapped = int((normalized * Decimal(10)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return min(10, max(0, mapped))


def evaluate_qwk_readiness(
    dataset: str,
    gold_bins: Iterable[int],
    pred_bins: Iterable[int],
    *,
    min_valid_completed: int = 100,
    min_gold_nonempty_bins: int = 2,
) -> QWKReadinessRecord:
    gold = [int(value) for value in gold_bins]
    pred = [int(value) for value in pred_bins]
    if len(gold) != len(pred):
        raise ValueError("QWK gold/pred bins 长度必须一致")
    computation = (
        quadratic_weighted_kappa_details(gold, pred, labels=FIXED_LABELS)
        if gold
        else None
    )
    valid_n = len(gold)
    gold_bin_count = len(set(gold))
    expected = computation.expected_weighted_disagreement if computation is not None else 0.0
    reasons: list[str] = []
    if valid_n < min_valid_completed:
        reasons.append(f"valid_completed_n<{min_valid_completed}")
    if gold_bin_count < min_gold_nonempty_bins:
        reasons.append(f"gold_nonempty_bin_count<{min_gold_nonempty_bins}")
    if expected <= 0.0:
        reasons.append("expected_weighted_disagreement<=0")
    qwk_defined = not reasons and computation is not None and computation.qwk is not None
    return QWKReadinessRecord(
        dataset=dataset,
        valid_completed_n=valid_n,
        gold_nonempty_bin_count=gold_bin_count,
        expected_weighted_disagreement=expected,
        fixed_labels=FIXED_LABELS,
        qwk_defined=qwk_defined,
        qwk=computation.qwk if qwk_defined and computation is not None else None,
        readiness_failure_reason=";".join(reasons),
    )
