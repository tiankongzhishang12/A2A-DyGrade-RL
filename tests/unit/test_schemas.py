from a2a_dygrade_rl.datasets.normalize import normalize_record
from a2a_dygrade_rl.utils.validation import validate_item


def test_normalize_record_accepts_alias_fields():
    item = normalize_record(
        {
            "id": "1",
            "question": "解释水循环。",
            "answer": "水蒸发后形成云。",
            "reference": "水通过蒸发、凝结、降水和径流循环。",
            "score": 4,
            "prompt_id": "p1",
        },
        {"name": "smoke", "question_type": "short_answer", "score_min": 0, "score_max": 5},
    )
    validate_item(item)
    assert item["item_id"] == "smoke_1"
    assert item["metadata"]["prompt_group"] == "p1"


def test_v14_manifest_schemas_encode_frozen_responsibilities():
    from a2a_dygrade_rl.utils.schemas import (
        BudgetCalibrationManifest,
        PolicyFreezeManifest,
        QualityChampionManifest,
        QualityProtectionManifest,
        QualityReferenceManifest,
    )

    h = "a" * 64
    reference = QualityReferenceManifest(
        manifest_version="v1",
        split="train_calibration",
        budget_to_reference_policy={"Tight": "Always-Strong"},
        candidates=[],
        quality_protocol_hash=h,
        internal_manifest_hash=h,
        cache_hash=h,
        seed=20260729,
    ).to_dict()
    budget = BudgetCalibrationManifest(
        manifest_version="v1",
        split="train_calibration",
        budgets={"Tight": {"max_cost": 1.0}},
        quantiles={"Tight": 0.25},
        policy_ids=("Always-Strong",),
        internal_manifest_hash=h,
        cache_hash=h,
        config_hash=h,
        seed=20260729,
    ).to_dict()
    champion = QualityChampionManifest(
        manifest_version="v1",
        split="dev",
        package_id="pkg",
        checkpoint_id="ckpt",
        quality_key=(0.0, 0.0, 0.0, -1.0, "pkg"),
        quality_champion_no_resource=True,
        manual_override_count=0,
        quality_protocol_hash=h,
    ).to_dict()
    protection = QualityProtectionManifest(
        manifest_version="v1",
        split="dev",
        champion_package_id="pkg",
        feasible_package_ids=("pkg",),
        candidate_to_champion_gate=True,
        gate_results=[],
        quality_protocol_hash=h,
    ).to_dict()
    freeze = PolicyFreezeManifest(
        manifest_version="v1",
        selected_package_id="pkg",
        selected_checkpoint_id="ckpt",
        quality_champion_package_id="pkg",
        budget_ids=("Tight", "Medium", "Loose"),
        stop_boundary=0.1,
        package_hash=h,
        quality_protocol_hash=h,
        internal_manifest_hash=h,
        quality_reference_manifest_hash=h,
        budget_manifest_hash=h,
        support_manifest_hash=h,
        dev_boundary_update_count=0,
        quality_champion_manual_override_count=0,
        selection_rule_version="v1.4",
    ).to_dict()
    assert reference["split"] == budget["split"] == "train_calibration"
    assert champion["quality_champion_no_resource"] is True
    assert protection["candidate_to_champion_gate"] is True
    assert freeze["dev_boundary_update_count"] == 0
