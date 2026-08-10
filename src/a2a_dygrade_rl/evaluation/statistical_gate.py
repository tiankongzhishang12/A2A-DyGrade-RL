"""单侧零边界质量非劣效统计门。"""

from __future__ import annotations

import math
from typing import Any

from a2a_dygrade_rl.evaluation.quality_protocol import protocol_fingerprint
from a2a_dygrade_rl.utils.schemas import PairedBootstrapGateResult, QualityMetricProtocol


METRIC_KEYS = (
    "max_dataset_delta_severe",
    "max_dataset_delta_unsafe_stop",
    "delta_macro_nmae",
    "delta_macro_qwk",
)


def _conservative_quantile(values: list[float], probability: float, *, lower: bool) -> float:
    if not values:
        raise ValueError("Bootstrap quantile 缺少样本")
    ordered = sorted(float(value) for value in values)
    n = len(ordered)
    if lower:
        index = max(0, math.floor(probability * n) - 1)
    else:
        index = min(n - 1, math.ceil(probability * n) - 1)
    return ordered[index]


def evaluate_bootstrap_gate(
    *,
    point_deltas: dict[str, float | None],
    replicate_deltas: dict[str, list[float]],
    protocol: QualityMetricProtocol,
    candidate_id: str,
    comparator_id: str,
    budget_id: str,
    comparison_kind: str,
    resample_index_digest: str,
    reconstruction: dict[str, Any] | None = None,
) -> PairedBootstrapGateResult:
    confidence = float(protocol.bootstrap_confidence_level)
    lower_probability = 1.0 - confidence
    upper_probability = confidence
    bounds: dict[str, float | None] = {key: None for key in METRIC_KEYS}
    missing: list[str] = []

    for key in METRIC_KEYS:
        point = point_deltas.get(key)
        samples = replicate_deltas.get(key, [])
        if point is None or not samples:
            missing.append(key)
            continue
        if len(samples) != protocol.bootstrap_replicates:
            raise ValueError(
                f"Bootstrap {key} replicate 数与协议不一致: "
                f"{len(samples)} != {protocol.bootstrap_replicates}"
            )
        if any(not math.isfinite(float(value)) for value in samples) or not math.isfinite(float(point)):
            missing.append(key)
            continue
        if key == "delta_macro_qwk":
            bounds[key] = _conservative_quantile(samples, lower_probability, lower=True)
        else:
            bounds[key] = _conservative_quantile(samples, upper_probability, lower=False)

    margin = float(protocol.noninferiority_margin)
    pass_severe = bounds["max_dataset_delta_severe"] is not None and bounds["max_dataset_delta_severe"] <= margin
    pass_unsafe = bounds["max_dataset_delta_unsafe_stop"] is not None and bounds["max_dataset_delta_unsafe_stop"] <= margin
    pass_nmae = bounds["delta_macro_nmae"] is not None and bounds["delta_macro_nmae"] <= margin
    pass_qwk = bounds["delta_macro_qwk"] is not None and bounds["delta_macro_qwk"] >= -margin
    feasible = bool(pass_severe and pass_unsafe and pass_nmae and pass_qwk)

    reasons: list[str] = []
    if missing:
        reasons.append("undefined_metrics:" + ",".join(missing))
    for key, passed in (
        ("max_dataset_delta_severe", pass_severe),
        ("max_dataset_delta_unsafe_stop", pass_unsafe),
        ("delta_macro_nmae", pass_nmae),
        ("delta_macro_qwk", pass_qwk),
    ):
        if not passed and key not in missing:
            reasons.append(f"{key}_noninferiority_failed")

    if feasible:
        status = "quality_noninferiority_pass"
    elif missing:
        status = "quality_noninferiority_inconclusive"
    else:
        wholly_inferior = any(
            min(replicate_deltas[key]) > margin
            for key in ("max_dataset_delta_severe", "max_dataset_delta_unsafe_stop", "delta_macro_nmae")
        ) or max(replicate_deltas["delta_macro_qwk"]) < -margin
        status = "quality_inferior" if wholly_inferior else "quality_noninferiority_inconclusive"

    return PairedBootstrapGateResult(
        candidate_id=candidate_id,
        comparator_id=comparator_id,
        budget_id=budget_id,
        comparison_kind=comparison_kind,
        unit=protocol.bootstrap_unit,
        paired=protocol.bootstrap_paired,
        replicates=protocol.bootstrap_replicates,
        confidence_level=protocol.bootstrap_confidence_level,
        noninferiority_margin=protocol.noninferiority_margin,
        seed=protocol.bootstrap_seed,
        point_max_dataset_delta_severe=point_deltas.get("max_dataset_delta_severe"),
        ucb95_max_dataset_delta_severe=bounds["max_dataset_delta_severe"],
        point_max_dataset_delta_unsafe_stop=point_deltas.get("max_dataset_delta_unsafe_stop"),
        ucb95_max_dataset_delta_unsafe_stop=bounds["max_dataset_delta_unsafe_stop"],
        point_delta_macro_nmae=point_deltas.get("delta_macro_nmae"),
        ucb95_delta_macro_nmae=bounds["delta_macro_nmae"],
        point_delta_macro_qwk=point_deltas.get("delta_macro_qwk"),
        lcb95_delta_macro_qwk=bounds["delta_macro_qwk"],
        pass_max_dataset_delta_severe=pass_severe,
        pass_max_dataset_delta_unsafe_stop=pass_unsafe,
        pass_delta_macro_nmae=pass_nmae,
        pass_delta_macro_qwk=pass_qwk,
        quality_feasible=feasible,
        status=status,
        failure_reason=";".join(reasons),
        quality_protocol_hash=protocol_fingerprint(protocol),
        resample_index_digest=resample_index_digest,
        reconstruction=reconstruction or {},
    )
