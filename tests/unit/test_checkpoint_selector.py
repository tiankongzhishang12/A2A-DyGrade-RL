from __future__ import annotations

from copy import deepcopy
import json

import pytest

import a2a_dygrade_rl.rl.checkpoint_selector as selector_module
from a2a_dygrade_rl.rl.checkpoint_selector import select_policy_package
from a2a_dygrade_rl.evaluation.quality_protocol import protocol_fingerprint
from a2a_dygrade_rl.utils.schemas import PairedBootstrapGateResult, QualityMetricProtocol


BUDGETS = ("Tight", "Medium", "Loose")
PROTOCOL_HASH = protocol_fingerprint(QualityMetricProtocol.formal_v13())


def _package(package_id: str, role: str = "router_candidate") -> dict:
    return {
        "package_id": package_id,
        "checkpoint_id": package_id.replace("pkg", "ckpt"),
        "checkpoint_hash": "c" * 64,
        "calibration_package_hash": "d" * 64,
        "package_role": role,
        "calibration_status": "success",
        "stop_boundary": 0.1,
        "boundary_frozen": True,
        "dev_boundary_updates": 0,
        "quality_protocol_hash": PROTOCOL_HASH,
        "internal_manifest_hash": "b" * 64,
        "quality_reference_manifest_hash": "e" * 64,
        "budget_manifest_hash": "f" * 64,
        "support_manifest_hash": "9" * 64,
    }


def _evaluation(package_id: str, budget_id: str, *, severe: float, cost: float) -> dict:
    return {
        "package_id": package_id,
        "budget_id": budget_id,
        "dataset_severe": {"asap_sas": severe, "sas_bench": severe, "dress": severe},
        "dataset_unsafe_stop": {"asap_sas": severe, "sas_bench": severe, "dress": severe},
        "macro_nmae": severe,
        "macro_qwk": 1.0 - severe,
        "cost_per_paper": cost,
        "elapsed_time_per_paper": cost * 10,
        "agent_calls_per_paper": cost * 5,
        "a2a_exchanges_per_paper": cost * 2,
        "quality_metrics_defined": True,
        "stop_readiness": True,
        "qwk_ready": True,
        "budget_feasible": True,
    }


def _gate(candidate: str, comparator: str, budget: str, kind: str, passed: bool) -> dict:
    good = 0.0 if passed else 0.01
    return PairedBootstrapGateResult(
        candidate_id=candidate,
        comparator_id=comparator,
        budget_id=budget,
        comparison_kind=kind,
        unit="paper",
        paired=True,
        replicates=5000,
        confidence_level=0.95,
        noninferiority_margin=0.0,
        seed=20260729,
        point_max_dataset_delta_severe=good,
        ucb95_max_dataset_delta_severe=good,
        point_max_dataset_delta_unsafe_stop=0.0,
        ucb95_max_dataset_delta_unsafe_stop=0.0,
        point_delta_macro_nmae=0.0,
        ucb95_delta_macro_nmae=0.0,
        point_delta_macro_qwk=0.0,
        lcb95_delta_macro_qwk=0.0,
        pass_max_dataset_delta_severe=passed,
        pass_max_dataset_delta_unsafe_stop=True,
        pass_delta_macro_nmae=True,
        pass_delta_macro_qwk=True,
        quality_feasible=passed,
        status="quality_noninferiority_pass" if passed else "quality_inferior",
        failure_reason="" if passed else "severe_error_inferior",
        quality_protocol_hash=PROTOCOL_HASH,
        resample_index_digest="8" * 64,
    ).to_dict()


def test_dev_selector_protects_quality_before_resource_order_and_is_deterministic():
    packages = [_package("pkg_a"), _package("pkg_b"), _package("baseline", role="baseline")]
    evaluations = []
    gates = []
    for budget in BUDGETS:
        # A更省资源，但质量点估计比B差；两者都先通过固定参考准入。
        evaluations.extend(
            [
                _evaluation("pkg_a", budget, severe=0.02, cost=1.0),
                _evaluation("pkg_b", budget, severe=0.01, cost=2.0),
                _evaluation("baseline", budget, severe=0.0, cost=0.5),
            ]
        )
        gates.extend(
            [
                _gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", True),
                _gate("pkg_b", f"reference_{budget}", budget, "fixed_reference", True),
                _gate("pkg_a", "pkg_b", budget, "quality_champion", False),
            ]
        )

    protocol = QualityMetricProtocol.formal_v13()
    packages_before = deepcopy(packages)
    first = select_policy_package(packages, evaluations, gates, protocol=protocol, budget_ids=BUDGETS)
    second = select_policy_package(packages, evaluations, gates, protocol=protocol, budget_ids=BUDGETS)

    assert packages == packages_before  # Dev 不得移动 calibration 边界或修改 Package。
    assert first == second
    assert first.quality_champion_package_id == "pkg_b"
    assert first.selected_package_id == "pkg_b"
    assert first.selected_checkpoint_id == "ckpt_b"
    assert first.quality_protection_feasible_ids == ("pkg_b",)
    assert "baseline" not in first.reference_admission_feasible_ids
    assert first.dev_boundary_update_count == 0
    assert first.quality_champion_manual_override_count == 0


def test_any_budget_reference_failure_eliminates_whole_package():
    packages = [_package("pkg_a"), _package("pkg_b")]
    evaluations = [
        _evaluation(package_id, budget, severe=0.01 if package_id == "pkg_b" else 0.02, cost=1.0)
        for package_id in ("pkg_a", "pkg_b")
        for budget in BUDGETS
    ]
    gates = []
    for budget in BUDGETS:
        gates.append(_gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", budget != "Loose"))
        gates.append(_gate("pkg_b", f"reference_{budget}", budget, "fixed_reference", True))
    result = select_policy_package(
        packages,
        evaluations,
        gates,
        protocol=QualityMetricProtocol.formal_v13(),
        budget_ids=BUDGETS,
    )
    assert result.reference_admission_feasible_ids == ("pkg_b",)
    assert result.selected_package_id == "pkg_b"


def test_quality_equivalent_candidate_can_win_only_after_champion_protection(tmp_path):
    packages = [_package("pkg_b"), _package("pkg_c")]
    evaluations = []
    gates = []
    for budget in BUDGETS:
        evaluations.extend([
            _evaluation("pkg_b", budget, severe=0.01, cost=2.0),
            _evaluation("pkg_c", budget, severe=0.01, cost=1.0),
        ])
        gates.extend([
            _gate("pkg_b", f"reference_{budget}", budget, "fixed_reference", True),
            _gate("pkg_c", f"reference_{budget}", budget, "fixed_reference", True),
            _gate("pkg_c", "pkg_b", budget, "quality_champion", True),
        ])
    result = select_policy_package(
        packages,
        evaluations,
        gates,
        protocol=QualityMetricProtocol.formal_v13(),
        budget_ids=BUDGETS,
        output_dir=tmp_path,
    )
    assert result.quality_champion_package_id == "pkg_b"  # 质量完全并列时由 Package ID 决定冠军。
    assert result.quality_protection_feasible_ids == ("pkg_b", "pkg_c")
    assert result.selected_package_id == "pkg_c"
    assert (tmp_path / "checkpoint_selection.csv").exists()
    freeze = json.loads((tmp_path / "policy_freeze_manifest.json").read_text(encoding="utf-8"))
    assert freeze["selected_package_id"] == "pkg_c"
    assert freeze["quality_champion_package_id"] == "pkg_b"
    assert freeze["dev_boundary_update_count"] == 0


def test_selector_rejects_unfrozen_or_hash_incomplete_candidate():
    package = _package("pkg_a")
    package["boundary_frozen"] = False
    evaluations = [_evaluation("pkg_a", budget, severe=0.01, cost=1.0) for budget in BUDGETS]
    gates = [_gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", True) for budget in BUDGETS]
    with pytest.raises(ValueError, match="STOP"):
        select_policy_package(
            [package],
            evaluations,
            gates,
            protocol=QualityMetricProtocol.formal_v13(),
            budget_ids=BUDGETS,
        )

    package = _package("pkg_a")
    package["budget_manifest_hash"] = ""
    with pytest.raises(ValueError, match="hash"):
        select_policy_package(
            [package],
            evaluations,
            gates,
            protocol=QualityMetricProtocol.formal_v13(),
            budget_ids=BUDGETS,
        )



def test_no_reference_admission_keeps_failure_selection_table(tmp_path):
    packages = [_package("pkg_a")]
    evaluations = [_evaluation("pkg_a", budget, severe=0.02, cost=1.0) for budget in BUDGETS]
    gates = [_gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", False) for budget in BUDGETS]
    result = select_policy_package(
        packages,
        evaluations,
        gates,
        protocol=QualityMetricProtocol.formal_v13(),
        budget_ids=BUDGETS,
        output_dir=tmp_path,
    )
    assert result.status == "no_reference_admission_feasible_package"
    assert result.selected_package_id is None
    assert (tmp_path / "checkpoint_selection.csv").exists()
    assert not (tmp_path / "policy_freeze_manifest.json").exists()

def test_budget_infeasible_candidate_cannot_be_admitted_even_when_quality_gate_passes():
    packages = [_package("pkg_over_budget")]
    evaluations = [
        {
            **_evaluation("pkg_over_budget", budget, severe=0.0, cost=999.0),
            "budget_feasible": False,
        }
        for budget in BUDGETS
    ]
    gates = [
        _gate("pkg_over_budget", f"reference_{budget}", budget, "fixed_reference", True)
        for budget in BUDGETS
    ]

    result = select_policy_package(
        packages,
        evaluations,
        gates,
        protocol=QualityMetricProtocol.formal_v13(),
        budget_ids=BUDGETS,
    )

    assert result.status == "no_reference_admission_feasible_package"
    assert result.reference_admission_feasible_ids == ()
    assert result.selected_package_id is None
    assert all(
        "budget_infeasible" in row["rejection_reason"]
        for row in result.selection_rows
        if row["package_id"] == "pkg_over_budget"
    )




def test_quality_champion_stage_fails_closed_if_quality_key_reads_resource_fields(monkeypatch):
    packages = [_package("pkg_a"), _package("pkg_b")]
    evaluations = [
        _evaluation(package_id, budget, severe=0.01, cost=1.0 if package_id == "pkg_a" else 2.0)
        for package_id in ("pkg_a", "pkg_b")
        for budget in BUDGETS
    ]
    gates = [
        _gate(package_id, f"reference_{budget}", budget, "fixed_reference", True)
        for package_id in ("pkg_a", "pkg_b")
        for budget in BUDGETS
    ]
    original = selector_module._quality_key

    def resource_reading_quality_key(package_id, evaluation_index, budget_ids, datasets):
        _ = evaluation_index[(package_id, budget_ids[0])]["cost_per_paper"]
        return original(package_id, evaluation_index, budget_ids, datasets)

    monkeypatch.setattr(selector_module, "_quality_key", resource_reading_quality_key)
    with pytest.raises(ValueError, match="Quality Champion.*resource"):
        select_policy_package(
            packages,
            evaluations,
            gates,
            protocol=QualityMetricProtocol.formal_v13(),
            budget_ids=BUDGETS,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quality_metrics_defined", False),
        ("stop_readiness", False),
        ("qwk_ready", False),
        ("macro_nmae", -0.01),
        ("macro_qwk", 1.01),
        ("cost_per_paper", -0.01),
        ("elapsed_time_per_paper", -0.01),
        ("agent_calls_per_paper", -0.01),
        ("a2a_exchanges_per_paper", -0.01),
    ],
)
def test_dev_selector_rejects_undefined_or_out_of_range_evaluation(field, value):
    evaluations = [_evaluation("pkg_a", budget, severe=0.01, cost=1.0) for budget in BUDGETS]
    evaluations[0][field] = value
    gates = [_gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", True) for budget in BUDGETS]

    result = select_policy_package(
        [_package("pkg_a")],
        evaluations,
        gates,
        protocol=QualityMetricProtocol.formal_v13(),
        budget_ids=BUDGETS,
    )

    assert result.status == "no_reference_admission_feasible_package"
    assert "invalid_dev_evaluation:Tight" in result.selection_rows[0]["rejection_reason"]


def test_dev_selector_rejects_forged_gate_without_confidence_bound_evidence():
    evaluations = [_evaluation("pkg_a", budget, severe=0.01, cost=1.0) for budget in BUDGETS]
    gates = [_gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", True) for budget in BUDGETS]
    gates[0].pop("ucb95_max_dataset_delta_severe")

    with pytest.raises(ValueError, match="PairedBootstrapGateResult"):
        select_policy_package(
            [_package("pkg_a")],
            evaluations,
            gates,
            protocol=QualityMetricProtocol.formal_v13(),
            budget_ids=BUDGETS,
        )


def test_dev_selector_rejects_string_boolean_gate_flags():
    evaluations = [_evaluation("pkg_a", budget, severe=0.01, cost=1.0) for budget in BUDGETS]
    gates = [_gate("pkg_a", f"reference_{budget}", budget, "fixed_reference", True) for budget in BUDGETS]
    gates[0]["quality_feasible"] = "false"

    with pytest.raises(ValueError, match="显式布尔"):
        select_policy_package(
            [_package("pkg_a")],
            evaluations,
            gates,
            protocol=QualityMetricProtocol.formal_v13(),
            budget_ids=BUDGETS,
        )
