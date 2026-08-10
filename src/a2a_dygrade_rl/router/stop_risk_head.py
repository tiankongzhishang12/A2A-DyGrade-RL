"""Router 内部 Stop-Risk Head 的 train_fit-only 轻量确定性接口。"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable


MODEL_VERSION = "stop_risk_logistic_v1"


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def fit_stop_risk_head(
    rows: Iterable[dict[str, Any]],
    *,
    feature_names: Iterable[str],
    seed: int,
    epochs: int = 200,
    learning_rate: float = 0.1,
    l2: float = 1e-4,
) -> dict[str, Any]:
    training_rows = [dict(row) for row in rows]
    names = tuple(str(name) for name in feature_names)
    if not training_rows or not names:
        raise ValueError("Stop-Risk Head 需要非空 train_fit rows 和 features")
    if {str(row.get("split", "")) for row in training_rows} != {"train_fit"}:
        raise ValueError("Stop-Risk Head 参数只能使用 train_fit")
    matrix: list[list[float]] = []
    targets: list[float] = []
    for row in training_rows:
        features = row.get("features", {})
        vector: list[float] = []
        for name in names:
            try:
                value = float(features[name])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Stop-Risk feature 缺失或非法: {name}") from exc
            if not math.isfinite(value):
                raise ValueError(f"Stop-Risk feature 非有限: {name}")
            vector.append(value)
        try:
            gate_error = float(row["gate_error"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Stop-Risk gate_error 缺失或非法") from exc
        if not math.isfinite(gate_error) or not 0.0 <= gate_error <= 1.0:
            raise ValueError("Stop-Risk gate_error 必须位于 [0,1] 且为有限数值")
        matrix.append(vector)
        targets.append(float(gate_error > 0.25))

    means = [sum(row[index] for row in matrix) / len(matrix) for index in range(len(names))]
    scales = []
    standardized: list[list[float]] = []
    for index in range(len(names)):
        variance = sum((row[index] - means[index]) ** 2 for row in matrix) / len(matrix)
        scales.append(math.sqrt(variance) if variance > 1e-12 else 1.0)
    for row in matrix:
        standardized.append([(row[index] - means[index]) / scales[index] for index in range(len(names))])

    prevalence = (sum(targets) + 0.5) / (len(targets) + 1.0)
    prevalence = min(1.0 - 1e-6, max(1e-6, prevalence))
    bias = math.log(prevalence / (1.0 - prevalence))
    weights = [0.0 for _ in names]
    for _ in range(int(epochs)):
        grad_w = [0.0 for _ in names]
        grad_b = 0.0
        for vector, target in zip(standardized, targets):
            probability = _sigmoid(bias + sum(weight * value for weight, value in zip(weights, vector)))
            error = probability - target
            grad_b += error
            for index, value in enumerate(vector):
                grad_w[index] += error * value
        n = float(len(standardized))
        bias -= float(learning_rate) * grad_b / n
        for index in range(len(weights)):
            weights[index] -= float(learning_rate) * (grad_w[index] / n + float(l2) * weights[index])

    model = {
        "model_version": MODEL_VERSION,
        "training_split": "train_fit",
        "target": "gate_error_gt_0.25",
        "feature_names": list(names),
        "means": means,
        "scales": scales,
        "weights": weights,
        "bias": bias,
        "seed": int(seed),
        "epochs": int(epochs),
        "learning_rate": float(learning_rate),
        "l2": float(l2),
        "training_row_count": len(training_rows),
        "positive_count": int(sum(targets)),
        "calibration_data_read_count": 0,
        "dev_test_read_count": 0,
    }
    model["model_hash"] = _stable_hash(model)
    return model


def predict_stop_risk(model: dict[str, Any], rows: Iterable[dict[str, Any]]) -> list[float]:
    names = tuple(str(name) for name in model["feature_names"])
    means = [float(value) for value in model["means"]]
    scales = [float(value) for value in model["scales"]]
    weights = [float(value) for value in model["weights"]]
    bias = float(model["bias"])
    predictions: list[float] = []
    for row in rows:
        features = row.get("features", {})
        standardized = [
            (float(features[name]) - means[index]) / scales[index]
            for index, name in enumerate(names)
        ]
        predictions.append(_sigmoid(bias + sum(weight * value for weight, value in zip(weights, standardized))))
    return predictions
