from __future__ import annotations

import pytest

from a2a_dygrade_rl.evaluation.paired_bootstrap import paired_cluster_bootstrap
from a2a_dygrade_rl.evaluation.statistical_gate import evaluate_bootstrap_gate
from a2a_dygrade_rl.utils.schemas import QualityMetricProtocol


def _protocol() -> QualityMetricProtocol:
    return QualityMetricProtocol.formal_v13(
        datasets=("asap_sas", "sas_bench", "dress"),
        qwk_min_valid_completed=1,
        bootstrap_replicates=5000,
    )


def _records(offset: float = 0.0) -> list[dict]:
    rows: list[dict] = []
    for paper_index in range(6):
        for dataset in ("asap_sas", "sas_bench", "dress"):
            # 每个 Paper 的每个 dataset 都包含两个 gold bin，避免小样本重采样退化。
            for gold_bin in (0, 1):
                gold = float(gold_bin)
                rows.append(
                    {
                        "paper_id": f"paper_{paper_index}",
                        "item_id": f"{paper_index}_{dataset}_{gold_bin}",
                        "dataset": dataset,
                        "gold_score": gold,
                        "pred_score": min(1.0, max(0.0, gold + offset)),
                        "score_min": 0.0,
                        "score_max": 1.0,
                        "status": "completed",
                        "terminal_action": "STOP",
                        "active_cache_valid": True,
                    }
                )
    return rows


def test_paired_paper_bootstrap_runs_5000_replicates_and_is_reproducible():
    first = paired_cluster_bootstrap(_records(), _records(), protocol=_protocol())
    second = paired_cluster_bootstrap(_records(), _records(), protocol=_protocol())
    assert first.replicates == 5000
    assert first.unit == "paper"
    assert first.paired is True
    assert first.status == "quality_noninferiority_pass"
    assert first.resample_index_digest == second.resample_index_digest
    assert first.to_dict() == second.to_dict()


def test_confidence_boundary_crossing_zero_is_inconclusive():
    samples = {
        "max_dataset_delta_severe": [-0.1, 0.1] * 2500,
        "max_dataset_delta_unsafe_stop": [0.0] * 5000,
        "delta_macro_nmae": [0.0] * 5000,
        "delta_macro_qwk": [0.0] * 5000,
    }
    result = evaluate_bootstrap_gate(
        point_deltas={name: 0.0 for name in samples},
        replicate_deltas=samples,
        protocol=_protocol(),
        candidate_id="candidate",
        comparator_id="reference",
        budget_id="Medium",
        comparison_kind="fixed_reference",
        resample_index_digest="8" * 64,
    )
    assert result.status == "quality_noninferiority_inconclusive"
    assert result.quality_feasible is False
    assert result.pass_max_dataset_delta_severe is False


def test_paired_bootstrap_rejects_different_paper_item_sets():
    candidate = _records()
    comparator = _records()[:-1]
    with pytest.raises(ValueError, match="Paper/Item/Dataset"):
        paired_cluster_bootstrap(candidate, comparator, protocol=_protocol())



def test_paired_bootstrap_rejects_duplicate_keys_and_changed_gold_metadata():
    candidate = _records()
    duplicate = candidate + [dict(candidate[0])]
    with pytest.raises(ValueError, match="重复"):
        paired_cluster_bootstrap(duplicate, _records(), protocol=_protocol())

    comparator = _records()
    comparator[0]["gold_score"] = 1.0 - comparator[0]["gold_score"]
    with pytest.raises(ValueError, match="gold_score"):
        paired_cluster_bootstrap(candidate, comparator, protocol=_protocol())

