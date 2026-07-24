from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from a2a_dygrade_rl.agents.cache import read_cache_records, validate_run_identity
from a2a_dygrade_rl.agents.capability import build_capability_profiles
from a2a_dygrade_rl.router.difficulty import (
    DEFAULT_DIFFICULTY_WEIGHTS,
    FEATURE_SCHEMA_VERSION,
    build_inference_features,
    build_train_difficulty_supervision,
    create_difficulty_predictor,
    label_difficulty,
    resolve_primary_difficulty_model_kind,
)
from a2a_dygrade_rl.utils.io import ensure_dir, read_jsonl, read_yaml, write_csv, write_jsonl, write_yaml
from a2a_dygrade_rl.utils.logging import configure_run_logger


def _load_manifest(run_dir: Path, run_id: str, execution_mode: str) -> dict:
    path = run_dir / "configs" / "agent_cache_manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Agent cache manifest not found: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    validate_run_identity(run_id, execution_mode, execution_mode == "fixture_smoke")
    expected = {
        "run_id": run_id,
        "execution_mode": execution_mode,
        "is_fixture": execution_mode == "fixture_smoke",
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Difficulty pipeline mode does not match the Agent cache manifest")
    if "train" not in manifest.get("splits", {}):
        raise ValueError("Difficulty and capability fitting requires train cache")
    return manifest


def _difficulty_distribution(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        grouped.setdefault(str(row["difficulty_label"]), []).append(float(row["difficulty_score"]))
    return [
        {
            "difficulty_label": label,
            "sample_count": len(values),
            "min_score": min(values),
            "mean_score": statistics.fmean(values),
            "max_score": max(values),
        }
        for label, values in sorted(grouped.items())
    ]


def _require_outputs_available(paths: list[Path], overwrite: bool) -> None:
    if overwrite:
        return
    existing = [str(path) for path in paths if path.exists()]
    if existing:
        raise FileExistsError(f"Difficulty/capability outputs already exist; use --overwrite: {existing}")


def _select_manifest_items(items: list[dict], manifest: dict) -> list[dict]:
    split_manifest = manifest.get("splits", {}).get("train", {})
    item_ids = split_manifest.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids:
        raise ValueError("Train cache manifest must contain the sampled item_ids")
    if int(split_manifest.get("item_count", -1)) != len(item_ids):
        raise ValueError("Train cache manifest item_count does not match item_ids")
    items_by_id = {str(item["item_id"]): item for item in items}
    if len(items_by_id) != len(items):
        raise ValueError("Prepared train input contains duplicate item_id values")
    missing = [str(item_id) for item_id in item_ids if str(item_id) not in items_by_id]
    if missing:
        raise ValueError(f"Prepared train input is missing cache-manifest items: {missing[:10]}")
    selected = [items_by_id[str(item_id)] for item_id in item_ids]
    if any(item.get("metadata", {}).get("split") != "train" for item in selected):
        raise ValueError("Cache-manifest items must all belong to the train split")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description="Build train difficulty and Agent capability artifacts")
    parser.add_argument("--items-path", required=True, help="Prepared train items JSONL")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--execution-mode",
        required=True,
        choices=("fixture_smoke", "real_pilot", "formal_experiment"),
    )
    parser.add_argument("--router-config", default="configs/router.yaml")
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--low-support-threshold", type=int, default=30)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.output_root) / args.run_id
    manifest = _load_manifest(run_dir, args.run_id, args.execution_mode)
    items = _select_manifest_items(read_jsonl(args.items_path), manifest)
    records = read_cache_records(run_dir / "predictions" / "agent_cache", "train")
    supervision, thresholds = build_train_difficulty_supervision(items, records)

    router_config = read_yaml(args.router_config)
    predictor_config = router_config.get("difficulty_predictor", {})
    model_kind = resolve_primary_difficulty_model_kind(args.execution_mode, predictor_config)
    predictor_role = "fixture" if args.execution_mode == "fixture_smoke" else "primary"
    parameters = predictor_config.get("parameters", {})
    predictor = create_difficulty_predictor(args.execution_mode, model_kind, parameters)
    features = [build_inference_features(item) for item in items]
    supervision_by_id = {str(row["item_id"]): row for row in supervision}
    targets = [float(supervision_by_id[str(item["item_id"])]["difficulty_score"]) for item in items]
    predictions = predictor.fit(features, targets).predict(features)

    difficulty_dir = run_dir / "predictions" / "difficulty"
    checkpoint_name = "model.fixture.json" if args.execution_mode == "fixture_smoke" else "model.joblib"
    checkpoint_path = run_dir / "checkpoints" / "difficulty_predictor" / checkpoint_name
    predicted_rows = [
        {
            "item_id": item["item_id"],
            "source_split": "train",
            "predicted_difficulty_score": prediction,
            "predicted_difficulty_label": label_difficulty(prediction, thresholds),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "execution_mode": args.execution_mode,
            "is_fixture": args.execution_mode == "fixture_smoke",
        }
        for item, prediction in zip(items, predictions)
    ]
    profiles = build_capability_profiles(
        items,
        records,
        supervision,
        low_support_threshold=args.low_support_threshold,
    )

    if not profiles:
        raise ValueError("Capability profile construction produced no rows")
    output_paths = [
        checkpoint_path,
        difficulty_dir / "train_supervision.jsonl",
        difficulty_dir / "train_predicted.jsonl",
        run_dir / "configs" / "difficulty_predictor.resolved.yaml",
        run_dir / "reports" / "difficulty_distribution.csv",
        run_dir / "reports" / "difficulty_model_metrics.csv",
        run_dir / "reports" / "agent_capability_table.csv",
        run_dir / "reports" / "difficulty_audit.md",
        run_dir / "reports" / "agent_capability_audit.md",
    ]
    _require_outputs_available(output_paths, args.overwrite)
    reports_dir = ensure_dir(run_dir / "reports")
    predictor.save(checkpoint_path)
    write_jsonl(difficulty_dir / "train_supervision.jsonl", supervision, overwrite=args.overwrite)
    write_jsonl(difficulty_dir / "train_predicted.jsonl", predicted_rows, overwrite=args.overwrite)
    write_yaml(
        run_dir / "configs" / "difficulty_predictor.resolved.yaml",
        {
            "run_id": args.run_id,
            "execution_mode": args.execution_mode,
            "is_fixture": args.execution_mode == "fixture_smoke",
            "model_kind": model_kind,
            "predictor_role": predictor_role,
            "parameters": parameters,
            "weights": DEFAULT_DIFFICULTY_WEIGHTS,
            "thresholds": thresholds,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "agent_cache_config_fingerprint": manifest["config_fingerprint"],
            "checkpoint": str(checkpoint_path),
        },
        overwrite=args.overwrite,
    )
    write_csv(
        reports_dir / "difficulty_distribution.csv",
        _difficulty_distribution(supervision),
        ["difficulty_label", "sample_count", "min_score", "mean_score", "max_score"],
        overwrite=args.overwrite,
    )
    prediction_mae = statistics.fmean(abs(prediction - target) for prediction, target in zip(predictions, targets))
    write_csv(
        reports_dir / "difficulty_model_metrics.csv",
        [{
            "split": "train",
            "mae": prediction_mae,
            "sample_count": len(targets),
            "model_kind": model_kind,
            "predictor_role": predictor_role,
        }],
        ["split", "mae", "sample_count", "model_kind", "predictor_role"],
        overwrite=args.overwrite,
    )
    capability_rows = [
        {**profile, "capability_vector": json.dumps(profile["capability_vector"]), "capability_vector_fields": json.dumps(profile["capability_vector_fields"])}
        for profile in profiles
    ]
    write_csv(
        reports_dir / "agent_capability_table.csv",
        capability_rows,
        list(capability_rows[0]),
        overwrite=args.overwrite,
    )

    label_counts = Counter(row["difficulty_label"] for row in supervision)
    (reports_dir / "difficulty_audit.md").write_text(
        "# Difficulty Audit\n\n"
        f"- run_id: `{args.run_id}`\n"
        f"- execution_mode: `{args.execution_mode}`\n"
        f"- predictor_role: `{predictor_role}`\n"
        f"- model_kind: `{model_kind}`\n"
        f"- source_split: `train`\n"
        f"- item_count: {len(supervision)}\n"
        f"- labels: {dict(label_counts)}\n"
        f"- train_prediction_mae: {prediction_mae:.8f}\n"
        "- dev_or_test_gold_used: 0\n",
        encoding="utf-8",
    )
    low_support = sum(bool(profile["low_support"]) for profile in profiles)
    (reports_dir / "agent_capability_audit.md").write_text(
        "# Agent Capability Audit\n\n"
        f"- run_id: `{args.run_id}`\n"
        "- source_split: `train`\n"
        f"- profile_count: {len(profiles)}\n"
        f"- low_support_profiles: {low_support}\n"
        "- dev_or_test_records_used: 0\n",
        encoding="utf-8",
    )
    logger = configure_run_logger("build_difficulty_labels", args.run_id, args.output_root)
    logger.info(
        "Difficulty/capability complete: items=%s profiles=%s train_mae=%.8f",
        len(supervision),
        len(profiles),
        prediction_mae,
    )


if __name__ == "__main__":
    main()
