"""Train-only difficulty supervision and leakage-safe predictor interfaces."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable


DEFAULT_DIFFICULTY_WEIGHTS = {"alpha": 0.30, "beta": 0.30, "gamma": 0.25, "delta": 0.15}
DIFFICULTY_FORMULA_VERSION = "normalized_error_v1"
FEATURE_SCHEMA_VERSION = "difficulty_features_v1"
BASE_DIFFICULTY_AGENTS = ("CheapAgent", "MidAgent", "StrongAgent")
FORMAL_PRIMARY_MODEL_KIND = "hist_gradient_boosting"
DIAGNOSTIC_MODEL_KIND = "ridge"


def _split_of(item: dict[str, Any]) -> str:
    return str(item.get("metadata", {}).get("split", ""))


def _require_train_only(items: Iterable[dict[str, Any]], records: Iterable[dict[str, Any]]) -> None:
    item_splits = {_split_of(item) for item in items}
    record_splits = {str(record.get("split", "")) for record in records}
    if item_splits != {"train"}:
        raise ValueError(f"Difficulty supervision requires train items, got: {sorted(item_splits)}")
    if record_splits != {"train"}:
        raise ValueError(f"Difficulty supervision requires train cache, got: {sorted(record_splits)}")


def normalized_score_error(pred_score: float, gold_score: float, score_min: float, score_max: float) -> float:
    span = float(score_max) - float(score_min)
    if span <= 0:
        raise ValueError("Normalized score error requires score_max > score_min")
    return abs(float(pred_score) - float(gold_score)) / span


def _bounded_ratio(value: float, scale: float) -> float:
    return max(0.0, min(1.0, float(value) / scale))


def static_complexity(item: dict[str, Any]) -> float:
    """Return deterministic [0, 1] complexity from pre-routing fields."""
    prompt = str(item.get("prompt", ""))
    answer = str(item.get("student_answer", ""))
    rubric = str(item.get("rubric", ""))
    reference = str(item.get("reference_answer", ""))
    words = answer.split()
    diversity = len({word.lower() for word in words}) / max(1, len(words))
    structure = sum(marker in answer for marker in ("\n", "=", "{", "}", "```")) / 5.0
    essay_bonus = float(str(item.get("question_type", "")).lower() == "essay")
    value = (
        0.15 * _bounded_ratio(len(prompt), 600.0)
        + 0.35 * _bounded_ratio(len(answer), 1800.0)
        + 0.15 * _bounded_ratio(len(rubric), 900.0)
        + 0.10 * _bounded_ratio(len(reference), 900.0)
        + 0.10 * diversity
        + 0.05 * structure
        + 0.10 * essay_bonus
    )
    return round(max(0.0, min(1.0, value)), 12)


def _normalized_disagreement(scores: list[float], score_span: float) -> float:
    if score_span <= 0:
        raise ValueError("Agent disagreement requires a positive score span")
    return min(1.0, statistics.pstdev(scores) / score_span) if len(scores) > 1 else 0.0


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("Cannot compute thresholds from empty difficulty scores")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def label_difficulty(score: float, thresholds: dict[str, Any]) -> str:
    if float(score) <= float(thresholds["easy_max"]):
        return "Easy"
    if float(score) <= float(thresholds["medium_max"]):
        return "Medium"
    return "Hard"


def _successful_base_records(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = {}
    for record in records:
        agent_id = str(record.get("agent_id", ""))
        if agent_id not in BASE_DIFFICULTY_AGENTS or record.get("status") != "success":
            continue
        item_id = str(record["item_id"])
        if agent_id in indexed.setdefault(item_id, {}):
            raise ValueError(f"Duplicate active base Agent record for item: {item_id}/{agent_id}")
        indexed[item_id][agent_id] = record
    return indexed


def build_train_difficulty_supervision(
    items: list[dict[str, Any]],
    records: list[dict[str, Any]],
    weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _require_train_only(items, records)
    resolved = dict(DEFAULT_DIFFICULTY_WEIGHTS if weights is None else weights)
    if set(resolved) != set(DEFAULT_DIFFICULTY_WEIGHTS):
        raise ValueError("Difficulty weights must contain alpha, beta, gamma, and delta")
    if any(float(value) < 0 for value in resolved.values()) or not math.isclose(sum(resolved.values()), 1.0, abs_tol=1e-9):
        raise ValueError("Difficulty weights must be non-negative and sum to 1")

    indexed = _successful_base_records(records)
    rows: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda row: str(row["item_id"])):
        item_id = str(item["item_id"])
        available = indexed.get(item_id, {})
        missing = set(BASE_DIFFICULTY_AGENTS) - set(available)
        if missing:
            raise ValueError(f"Difficulty supervision is missing base Agent cache: {item_id} {sorted(missing)}")
        score_min, score_max = float(item["score_min"]), float(item["score_max"])
        gold = float(item["gold_score"])
        scores = [float(available[agent_id]["pred_score"]) for agent_id in BASE_DIFFICULTY_AGENTS]
        confidences = [float(available[agent_id]["confidence"]) for agent_id in BASE_DIFFICULTY_AGENTS]
        signals = {
            "err_cheap": normalized_score_error(available["CheapAgent"]["pred_score"], gold, score_min, score_max),
            "err_mid": normalized_score_error(available["MidAgent"]["pred_score"], gold, score_min, score_max),
            "disagreement": _normalized_disagreement(scores, score_max - score_min),
            "complexity": static_complexity(item),
            "confidence_variance": statistics.pvariance(confidences),
        }
        score = (
            resolved["alpha"] * signals["err_cheap"]
            + resolved["beta"] * signals["err_mid"]
            + resolved["gamma"] * signals["disagreement"]
            + resolved["delta"] * signals["complexity"]
        )
        rows.append({
            "item_id": item_id,
            "dataset": item.get("dataset"),
            "question_type": item.get("question_type"),
            "source_split": "train",
            "difficulty_score": round(score, 12),
            "difficulty_label": None,
            "signals": signals,
            "weights": resolved,
            "formula_version": DIFFICULTY_FORMULA_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
        })

    scores = [float(row["difficulty_score"]) for row in rows]
    thresholds = {
        "easy_max": _quantile(scores, 1.0 / 3.0),
        "medium_max": _quantile(scores, 2.0 / 3.0),
        "source_split": "train",
        "sample_count": len(scores),
        "method": "train_quantile_tertiles",
        "formula_version": DIFFICULTY_FORMULA_VERSION,
    }
    for row in rows:
        row["difficulty_label"] = label_difficulty(row["difficulty_score"], thresholds)
    return rows, thresholds


def _stable_unit(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def build_inference_features(
    item: dict[str, Any],
    observed_agent_records: list[dict[str, Any]] | None = None,
    visible_agent_ids: set[str] | None = None,
) -> dict[str, float]:
    """Build only features visible at the current route step; gold is never read."""
    observed = observed_agent_records or []
    if observed and visible_agent_ids is None:
        raise ValueError("visible_agent_ids is required when observed Agent records are provided")
    unexpected = {str(record.get("agent_id")) for record in observed} - (visible_agent_ids or set())
    if unexpected:
        raise ValueError(f"Difficulty features contain Agent outputs that are not visible: {sorted(unexpected)}")
    successful = [record for record in observed if record.get("status") == "success"]
    scores = [float(record["pred_score"]) for record in successful]
    confidences = [float(record["confidence"]) for record in successful]
    prompt = str(item.get("prompt", ""))
    answer = str(item.get("student_answer", ""))
    rubric = str(item.get("rubric", ""))
    reference = str(item.get("reference_answer", ""))
    words = answer.split()
    span = float(item["score_max"]) - float(item["score_min"])
    return {
        "prompt_length": float(len(prompt)),
        "answer_length": float(len(answer)),
        "rubric_length": float(len(rubric)),
        "reference_length": float(len(reference)),
        "answer_token_count": float(len(words)),
        "lexical_diversity": len({word.lower() for word in words}) / max(1, len(words)),
        "score_range": span,
        "is_essay": float(str(item.get("question_type", "")).lower() == "essay"),
        "has_reference": float(bool(reference.strip())),
        "has_rubric": float(bool(rubric.strip())),
        "dataset_hash": _stable_unit(str(item.get("dataset", ""))),
        "prompt_group_hash": _stable_unit(str(item.get("metadata", {}).get("prompt_group", ""))),
        "static_complexity": static_complexity(item),
        "observed_agent_count": float(len(scores)),
        "observed_score_disagreement": _normalized_disagreement(scores, span) if scores else 0.0,
        "observed_confidence_mean": statistics.fmean(confidences) if confidences else 0.0,
        "observed_confidence_variance": statistics.pvariance(confidences) if len(confidences) > 1 else 0.0,
    }


class FixtureDifficultyPredictor:
    """Deterministic lightweight predictor that can never become a formal checkpoint."""

    predictor_kind = "fixture_linear_v1"

    def __init__(self) -> None:
        self.feature_names: list[str] = []
        self.means: dict[str, float] = {}
        self.coefficients: dict[str, float] = {}
        self.target_mean = 0.0
        self.target_min = 0.0
        self.target_max = 1.0
        self.fitted = False

    def fit(self, features: list[dict[str, float]], targets: list[float]) -> "FixtureDifficultyPredictor":
        if not features or len(features) != len(targets):
            raise ValueError("Fixture predictor requires non-empty aligned features and targets")
        self.feature_names = sorted(features[0])
        if any(sorted(row) != self.feature_names for row in features):
            raise ValueError("Difficulty feature schema is inconsistent")
        self.target_mean = statistics.fmean(targets)
        self.target_min, self.target_max = min(targets), max(targets)
        for name in self.feature_names:
            values = [float(row[name]) for row in features]
            mean = statistics.fmean(values)
            variance = sum((value - mean) ** 2 for value in values)
            covariance = sum((value - mean) * (target - self.target_mean) for value, target in zip(values, targets))
            self.means[name] = mean
            self.coefficients[name] = covariance / variance / len(self.feature_names) if variance else 0.0
        self.fitted = True
        return self

    def predict(self, features: list[dict[str, float]]) -> list[float]:
        if not self.fitted:
            raise ValueError("Fixture predictor has not been fitted")
        predictions = []
        for row in features:
            if sorted(row) != self.feature_names:
                raise ValueError("Difficulty feature schema does not match the checkpoint")
            value = self.target_mean + sum(
                self.coefficients[name] * (float(row[name]) - self.means[name]) for name in self.feature_names
            )
            predictions.append(max(self.target_min, min(self.target_max, value)))
        return predictions

    def save(self, path: str | Path) -> Path:
        if not self.fitted:
            raise ValueError("Cannot save an unfitted Fixture predictor")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "predictor_kind": self.predictor_kind,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_names": self.feature_names,
            "means": self.means,
            "coefficients": self.coefficients,
            "target_mean": self.target_mean,
            "target_min": self.target_min,
            "target_max": self.target_max,
            "is_fixture": True,
        }, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        return target


class SklearnDifficultyPredictor:
    """Lazy sklearn wrapper with an explicit primary or diagnostic role."""

    def __init__(
        self,
        model_kind: str,
        parameters: dict[str, Any] | None = None,
        *,
        predictor_role: str,
    ):
        if predictor_role == "primary" and model_kind != FORMAL_PRIMARY_MODEL_KIND:
            raise ValueError("Formal primary difficulty predictor must use hist_gradient_boosting")
        if predictor_role == "diagnostic" and model_kind != DIAGNOSTIC_MODEL_KIND:
            raise ValueError("Diagnostic difficulty predictor must use ridge")
        if predictor_role not in {"primary", "diagnostic"}:
            raise ValueError(f"Unknown difficulty predictor role: {predictor_role}")
        try:
            from sklearn.ensemble import HistGradientBoostingRegressor
            from sklearn.linear_model import Ridge
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Formal difficulty predictor requires scikit-learn installed in D:\\A2A-DyGrade-RL\\.venv after explicit approval"
            ) from exc
        if model_kind == "hist_gradient_boosting":
            defaults = {"loss": "squared_error", "learning_rate": 0.08, "max_iter": 200, "max_leaf_nodes": 31, "min_samples_leaf": 20, "l2_regularization": 0.1, "early_stopping": True, "random_state": 42}
            self.model = HistGradientBoostingRegressor(**{**defaults, **(parameters or {})})
        elif model_kind == "ridge":
            self.model = Ridge(**(parameters or {}))
        else:
            raise ValueError(f"Unknown sklearn difficulty predictor: {model_kind}")
        self.model_kind = model_kind
        self.predictor_role = predictor_role
        self.feature_names: list[str] = []

    def fit(self, features: list[dict[str, float]], targets: list[float]) -> "SklearnDifficultyPredictor":
        self.feature_names = sorted(features[0])
        self.model.fit([[row[name] for name in self.feature_names] for row in features], targets)
        return self

    def predict(self, features: list[dict[str, float]]) -> list[float]:
        matrix = [[row[name] for name in self.feature_names] for row in features]
        return [float(value) for value in self.model.predict(matrix)]

    def save(self, path: str | Path) -> Path:
        import joblib
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model": self.model,
            "feature_names": self.feature_names,
            "model_kind": self.model_kind,
            "predictor_role": self.predictor_role,
        }, target)
        return target


def resolve_primary_difficulty_model_kind(execution_mode: str, predictor_config: dict[str, Any]) -> str:
    if execution_mode == "fixture_smoke":
        return "fixture"
    if execution_mode == "real_pilot":
        raise ValueError("real_pilot cache cannot train or promote a difficulty predictor")
    if execution_mode != "formal_experiment":
        raise ValueError(f"Unknown execution_mode: {execution_mode}")
    model_kind = str(predictor_config.get("model_kind", FORMAL_PRIMARY_MODEL_KIND))
    if model_kind != FORMAL_PRIMARY_MODEL_KIND:
        raise ValueError(
            "Formal primary difficulty predictor must use hist_gradient_boosting; "
            "ridge is diagnostic-only"
        )
    return model_kind


def create_difficulty_predictor(
    execution_mode: str,
    model_kind: str = "fixture",
    parameters: dict[str, Any] | None = None,
):
    if execution_mode == "fixture_smoke":
        if model_kind != "fixture":
            raise ValueError("fixture_smoke must use the isolated FixtureDifficultyPredictor")
        return FixtureDifficultyPredictor()
    if execution_mode == "real_pilot":
        raise ValueError("real_pilot cache cannot train or promote a difficulty predictor")
    if execution_mode != "formal_experiment":
        raise ValueError(f"Unknown execution_mode: {execution_mode}")
    if model_kind != FORMAL_PRIMARY_MODEL_KIND:
        raise ValueError(
            "Formal primary difficulty predictor must use hist_gradient_boosting; "
            "ridge is diagnostic-only"
        )
    return SklearnDifficultyPredictor(model_kind, parameters, predictor_role="primary")


def create_diagnostic_difficulty_predictor(
    execution_mode: str,
    model_kind: str = DIAGNOSTIC_MODEL_KIND,
    parameters: dict[str, Any] | None = None,
):
    if execution_mode != "formal_experiment":
        raise ValueError("Diagnostic difficulty predictors are isolated to formal_experiment train data")
    if model_kind != DIAGNOSTIC_MODEL_KIND:
        raise ValueError("Diagnostic difficulty predictor must use ridge")
    return SklearnDifficultyPredictor(model_kind, parameters, predictor_role="diagnostic")
