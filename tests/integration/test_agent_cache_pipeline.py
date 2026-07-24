import csv
import json
from pathlib import Path

import pytest

import a2a_dygrade_rl.agents.cache as cache_module
import a2a_dygrade_rl.router.difficulty as difficulty_module
from a2a_dygrade_rl.agents.cache import run_agent_cache
from a2a_dygrade_rl.agents.capability import build_capability_profiles
from a2a_dygrade_rl.router.difficulty import (
    DEFAULT_DIFFICULTY_WEIGHTS,
    build_inference_features,
    build_train_difficulty_supervision,
    create_diagnostic_difficulty_predictor,
    create_difficulty_predictor,
    resolve_primary_difficulty_model_kind,
)
from a2a_dygrade_rl.utils.io import read_jsonl, write_jsonl, write_yaml


def make_items() -> list[dict]:
    rows = []
    datasets = ["asap_sas", "sas_bench", "dress"]
    for index in range(12):
        score_max = float(2 + (index % 4))
        rows.append(
            {
                "item_id": f"train_{index}",
                "dataset": datasets[index % len(datasets)],
                "question_type": "essay" if index % 3 == 2 else "short_answer",
                "subject": "mixed",
                "prompt": "Explain the evidence " + ("carefully " * index),
                "student_answer": "answer " * (index + 1),
                "reference_answer": "reference answer" if index % 2 else "",
                "rubric": "rubric point " * (1 + index % 3),
                "gold_score": float(index % (int(score_max) + 1)),
                "score_min": 0.0,
                "score_max": score_max,
                "metadata": {"split": "train", "prompt_group": f"pg_{index}"},
            }
        )
    return rows


def agent_config() -> dict:
    common = {"mode": "fixture", "model_revision": "fixture-r1", "prompt_version": "v1"}
    return {
        "cache_schema_version": "1.0",
        "arbitrator_contexts": [
            ["CheapAgent", "MidAgent"],
            ["CheapAgent", "StrongAgent"],
            ["MidAgent", "StrongAgent"],
            ["CheapAgent", "MidAgent", "StrongAgent"],
            ["CheapAgent", "MidAgent", "EvidenceAgent"],
            ["CheapAgent", "StrongAgent", "EvidenceAgent"],
            ["MidAgent", "StrongAgent", "EvidenceAgent"],
            ["CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent"],
        ],
        "agents": {
            "cheap": {**common, "agent_id": "CheapAgent", "model_id": "fixture-cheap-v1", "prompt_path": "prompts/cheap_scorer.txt", "cost": 0.001, "latency": 0.1},
            "mid": {**common, "agent_id": "MidAgent", "model_id": "fixture-mid-v1", "prompt_path": "prompts/mid_scorer.txt", "cost": 0.005, "latency": 0.2},
            "strong": {**common, "agent_id": "StrongAgent", "model_id": "fixture-strong-v1", "prompt_path": "prompts/strong_scorer.txt", "cost": 0.02, "latency": 0.3},
            "evidence": {**common, "agent_id": "EvidenceAgent", "model_id": "fixture-evidence-v1", "prompt_path": "prompts/evidence_agent.txt", "cost": 0.01, "latency": 0.2},
            "arbitrator": {**common, "agent_id": "ArbitratorAgent", "model_id": "fixture-arbitrator-v1", "prompt_path": "prompts/arbitrator_agent.txt", "cost": 0.03, "latency": 0.4},
        },
    }


def test_fixture_cache_difficulty_and_capability_pipeline(tmp_path):
    items = make_items()
    items_path = tmp_path / "items_train.jsonl"
    config_path = tmp_path / "agents.yaml"
    write_jsonl(items_path, items)
    write_yaml(config_path, agent_config())
    output_root = tmp_path / "outputs" / "runs"

    first = run_agent_cache(
        config_path=config_path,
        items_path=items_path,
        split="train",
        run_id="fixture_smoke_001",
        execution_mode="fixture_smoke",
        seed=17,
        output_root=output_root,
    )
    assert first["generated"] == 12 * 12
    assert first["reused"] == 0
    second = run_agent_cache(
        config_path=config_path,
        items_path=items_path,
        split="train",
        run_id="fixture_smoke_001",
        execution_mode="fixture_smoke",
        seed=17,
        output_root=output_root,
        resume=True,
    )
    assert second["generated"] == 0
    assert second["reused"] == first["generated"]
    assert first["records"] == second["records"]

    supervision, thresholds = build_train_difficulty_supervision(items, first["records"])
    assert len(supervision) == len(items)
    assert {row["difficulty_label"] for row in supervision} == {"Easy", "Medium", "Hard"}
    row = supervision[0]
    signals = row["signals"]
    weights = DEFAULT_DIFFICULTY_WEIGHTS
    expected = (
        weights["alpha"] * signals["err_cheap"]
        + weights["beta"] * signals["err_mid"]
        + weights["gamma"] * signals["disagreement"]
        + weights["delta"] * signals["complexity"]
    )
    assert row["difficulty_score"] == pytest.approx(expected)
    assert thresholds["source_split"] == "train"

    profiles = build_capability_profiles(items, first["records"], supervision, low_support_threshold=2)
    assert profiles
    required = {"agent_id", "dataset", "question_type", "difficulty_label", "qwk", "mae", "normalized_mae", "cost", "latency", "calibration", "sample_count", "capability_vector"}
    assert required.issubset(profiles[0])
    assert all(profile["source_split"] == "train" for profile in profiles)


def test_difficulty_and_capability_reject_test_split():
    item = make_items()[0]
    item["metadata"]["split"] = "test"

    with pytest.raises(ValueError, match="train items"):
        build_train_difficulty_supervision([item], [])
    with pytest.raises(ValueError, match="train items"):
        build_capability_profiles(
            [item],
            [{"split": "test"}],
            [{"source_split": "test"}],
        )


def test_difficulty_features_use_only_visible_information():
    item = make_items()[0]
    features = build_inference_features(item)
    changed_gold = {**item, "gold_score": item["gold_score"] + 100.0}
    assert build_inference_features(changed_gold) == features

    observed = [
        {
            "agent_id": "CheapAgent",
            "status": "success",
            "pred_score": 1.0,
            "confidence": 0.75,
        }
    ]
    visible = build_inference_features(item, observed, {"CheapAgent"})
    assert visible["observed_agent_count"] == 1.0
    with pytest.raises(ValueError, match="not visible"):
        build_inference_features(item, observed, {"MidAgent"})


def test_fixture_and_formal_difficulty_predictors_are_isolated():
    predictor = create_difficulty_predictor("fixture_smoke", "fixture")
    assert predictor.predictor_kind == "fixture_linear_v1"
    with pytest.raises(ValueError, match="must use"):
        create_difficulty_predictor("fixture_smoke", "hist_gradient_boosting")
    with pytest.raises(ValueError, match="must use"):
        create_difficulty_predictor("formal_experiment", "fixture")
    with pytest.raises(ValueError, match="diagnostic-only"):
        create_difficulty_predictor("formal_experiment", "ridge")
    with pytest.raises(ValueError, match="cannot train"):
        create_difficulty_predictor("real_pilot", "fixture")


class StubSklearnDifficultyPredictor:
    def __init__(self, model_kind, parameters=None, *, predictor_role):
        self.model_kind = model_kind
        self.parameters = parameters or {}
        self.predictor_role = predictor_role


def test_formal_primary_and_ridge_diagnostic_roles_are_isolated(monkeypatch):
    monkeypatch.setattr(difficulty_module, "SklearnDifficultyPredictor", StubSklearnDifficultyPredictor)

    primary = create_difficulty_predictor("formal_experiment", "hist_gradient_boosting", {"max_iter": 10})
    assert primary.model_kind == "hist_gradient_boosting"
    assert primary.predictor_role == "primary"

    diagnostic = create_diagnostic_difficulty_predictor("formal_experiment", "ridge", {"alpha": 1.0})
    assert diagnostic.model_kind == "ridge"
    assert diagnostic.predictor_role == "diagnostic"

    with pytest.raises(ValueError, match="must use ridge"):
        create_diagnostic_difficulty_predictor("formal_experiment", "hist_gradient_boosting")
    with pytest.raises(ValueError, match="isolated"):
        create_diagnostic_difficulty_predictor("fixture_smoke", "ridge")


def test_primary_model_config_cannot_promote_ridge():
    assert resolve_primary_difficulty_model_kind("fixture_smoke", {"model_kind": "ridge"}) == "fixture"
    assert resolve_primary_difficulty_model_kind("formal_experiment", {}) == "hist_gradient_boosting"
    with pytest.raises(ValueError, match="diagnostic-only"):
        resolve_primary_difficulty_model_kind("formal_experiment", {"model_kind": "ridge"})


def test_cache_manifest_supports_multiple_splits_and_safe_resume(tmp_path):
    train_items = make_items()[:3]
    dev_items = []
    for item in make_items()[3:6]:
        dev_item = {**item, "item_id": item["item_id"].replace("train_", "dev_")}
        dev_item["metadata"] = {**item["metadata"], "split": "dev"}
        dev_items.append(dev_item)

    train_path = tmp_path / "items_train.jsonl"
    dev_path = tmp_path / "items_dev.jsonl"
    config_path = tmp_path / "agents.yaml"
    write_jsonl(train_path, train_items)
    write_jsonl(dev_path, dev_items)
    write_yaml(config_path, agent_config())
    output_root = tmp_path / "outputs" / "runs"
    common = {
        "config_path": config_path,
        "run_id": "fixture_smoke_multi_split",
        "execution_mode": "fixture_smoke",
        "seed": 23,
        "output_root": output_root,
    }

    run_agent_cache(items_path=train_path, split="train", **common)
    run_agent_cache(items_path=dev_path, split="dev", **common)
    manifest_path = output_root / common["run_id"] / "configs" / "agent_cache_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["splits"]) == {"train", "dev"}
    assert manifest["splits"]["train"]["item_count"] == 3
    assert manifest["splits"]["dev"]["item_count"] == 3

    with pytest.raises(FileExistsError, match="use resume"):
        run_agent_cache(items_path=dev_path, split="dev", **common)

    changed_dev_path = tmp_path / "items_dev_changed.jsonl"
    write_jsonl(changed_dev_path, dev_items[:2])
    with pytest.raises(ValueError, match="cross-data"):
        run_agent_cache(items_path=changed_dev_path, split="dev", resume=True, **common)

    content_changed_items = [{**item, "student_answer": item["student_answer"] + " changed"} for item in dev_items]
    content_changed_path = tmp_path / "items_dev_content_changed.jsonl"
    write_jsonl(content_changed_path, content_changed_items)
    with pytest.raises(ValueError, match="cross-data"):
        run_agent_cache(items_path=content_changed_path, split="dev", resume=True, **common)

    changed_config = agent_config()
    changed_config["agents"]["cheap"]["cost"] = 99.0
    changed_config_path = tmp_path / "agents_changed.yaml"
    write_yaml(changed_config_path, changed_config)
    with pytest.raises(ValueError, match="cross-mode or cross-config"):
        run_agent_cache(
            config_path=changed_config_path,
            items_path=train_path,
            split="train",
            run_id=common["run_id"],
            execution_mode="fixture_smoke",
            seed=23,
            output_root=output_root,
            resume=True,
        )


def test_resume_retries_failed_cache_and_rebuilds_failure_artifacts(tmp_path, monkeypatch):
    items_path = tmp_path / "items_train.jsonl"
    config_path = tmp_path / "agents.yaml"
    output_root = tmp_path / "outputs" / "runs"
    write_jsonl(items_path, make_items()[:1])
    write_yaml(config_path, agent_config())

    attempts = {"count": 0}
    original_build_registry = cache_module.build_agent_registry

    def build_registry_with_transient_failure(config, execution_mode, seed):
        registry = original_build_registry(config, execution_mode, seed)
        cheap_agent = registry["CheapAgent"]
        original_predict = cheap_agent.predict

        def flaky_predict(item, context=None):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise TimeoutError("transient test failure")
            return original_predict(item, context)

        cheap_agent.predict = flaky_predict
        return registry

    monkeypatch.setattr(cache_module, "build_agent_registry", build_registry_with_transient_failure)
    common = {
        "config_path": config_path,
        "items_path": items_path,
        "split": "train",
        "run_id": "fixture_smoke_resume_failure",
        "execution_mode": "fixture_smoke",
        "output_root": output_root,
    }

    first = run_agent_cache(**common)
    run_dir = output_root / common["run_id"]
    failures_path = run_dir / "logs" / "failures.train.jsonl"
    assert first["generated"] == 12
    assert first["reused"] == 0
    assert first["failures"] == 7
    assert sum(record["status"] == "failed" for record in first["records"]) == 7
    assert failures_path.exists()

    resumed = run_agent_cache(**common, resume=True)
    assert attempts["count"] == 2
    assert resumed["generated"] == 7
    assert resumed["reused"] == 5
    assert resumed["failures"] == 0
    assert len(resumed["records"]) == 12
    assert all(record["status"] == "success" for record in resumed["records"])
    assert not failures_path.exists()

    audit = (run_dir / "reports" / "agent_cache_audit.train.md").read_text(encoding="utf-8")
    assert "- failures: 0" in audit
    with (run_dir / "reports" / "agent_cache_coverage.train.csv").open(encoding="utf-8", newline="") as handle:
        coverage = list(csv.DictReader(handle))
    assert {row["agent_id"] for row in coverage} == {
        "CheapAgent",
        "MidAgent",
        "StrongAgent",
        "EvidenceAgent",
        "ArbitratorAgent",
    }
    assert all(row["failure"] == "0" and row["coverage"] == "1.0" for row in coverage)

    final_resume = run_agent_cache(**common, resume=True)
    assert attempts["count"] == 2
    assert final_resume["generated"] == 0
    assert final_resume["reused"] == 12
    assert final_resume["failures"] == 0


@pytest.mark.parametrize(
    ("field", "value"),
    [("pred_score", None), ("run_id", "fixture_smoke_other_run")],
)
def test_resume_rebuilds_invalid_success_cache_record(tmp_path, field, value):
    items_path = tmp_path / "items_train.jsonl"
    config_path = tmp_path / "agents.yaml"
    output_root = tmp_path / "outputs" / "runs"
    write_jsonl(items_path, make_items()[:1])
    write_yaml(config_path, agent_config())
    common = {
        "config_path": config_path,
        "items_path": items_path,
        "split": "train",
        "run_id": "fixture_smoke_invalid_success",
        "execution_mode": "fixture_smoke",
        "output_root": output_root,
    }

    first = run_agent_cache(**common)
    assert first["generated"] == 12

    cheap_path = output_root / common["run_id"] / "predictions" / "agent_cache" / "train" / "CheapAgent.jsonl"
    cheap_records = read_jsonl(cheap_path)
    cheap_records[0][field] = value
    write_jsonl(cheap_path, cheap_records, overwrite=True)

    resumed = run_agent_cache(**common, resume=True)
    assert resumed["generated"] == 1
    assert resumed["reused"] == 11
    assert resumed["failures"] == 0
    repaired = [record for record in resumed["records"] if record["agent_id"] == "CheapAgent"]
    assert len(repaired) == 1
    assert repaired[0]["status"] == "success"
    assert repaired[0]["run_id"] == common["run_id"]
    assert repaired[0]["pred_score"] is not None
    assert repaired[0]["justification"]


def test_test_cache_requires_final_evaluation(tmp_path):
    item = make_items()[0]
    item["item_id"] = "test_0"
    item["metadata"]["split"] = "test"
    items_path = tmp_path / "items_test.jsonl"
    config_path = tmp_path / "agents.yaml"
    write_jsonl(items_path, [item])
    write_yaml(config_path, agent_config())

    with pytest.raises(ValueError, match="final_evaluation"):
        run_agent_cache(
            config_path=config_path,
            items_path=items_path,
            split="test",
            run_id="fixture_smoke_test_gate",
            execution_mode="fixture_smoke",
            output_root=tmp_path / "outputs" / "runs",
        )
