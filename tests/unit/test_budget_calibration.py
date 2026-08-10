from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from a2a_dygrade_rl.rl.budget_calibration import calibrate_budget_tiers


def _observations() -> list[dict]:
    rows = []
    for index, value in enumerate((1.0, 2.0, 3.0, 4.0), start=1):
        rows.append(
            {
                "paper_id": f"p{index}",
                "policy_id": "Fixture-Behavior",
                "split": "train_calibration",
                "cost": value,
                "elapsed_time": value * 10,
                "agent_calls": index,
                "a2a_exchanges": index - 1,
            }
        )
    return rows


def test_budget_tiers_use_preregistered_nearest_rank_and_formal_fields(tmp_path: Path):
    rows = _observations()
    before = deepcopy(rows)
    result = calibrate_budget_tiers(
        rows,
        quantiles={"Tight": 0.25, "Medium": 0.50, "Loose": 0.75},
        internal_manifest_hash="a" * 64,
        cache_hash="b" * 64,
        config={"quantile_method": "nearest_rank"},
        seed=20260729,
        output_path=tmp_path / "budget_calibration_manifest.json",
    )
    assert rows == before
    assert result["split"] == "train_calibration"
    assert result["budgets"]["Tight"] == {
        "max_cost": 1.0,
        "max_elapsed_time": 10.0,
        "max_agent_calls": 1,
        "max_a2a_exchanges": 0,
    }
    assert result["budgets"]["Medium"]["max_cost"] == 2.0
    assert result["budgets"]["Loose"]["max_cost"] == 3.0
    assert len(result["config_hash"]) == 64
    assert (tmp_path / "budget_calibration_manifest.json").exists()


def test_budget_calibration_rejects_dev_test_and_router_checkpoint_fields():
    for update, message in (
        ({"split": "dev"}, "train_calibration"),
        ({"checkpoint_id": "ckpt"}, "checkpoint"),
    ):
        rows = _observations()
        rows[0].update(update)
        with pytest.raises(ValueError, match=message):
            calibrate_budget_tiers(
                rows,
                quantiles={"Tight": 0.25, "Medium": 0.50, "Loose": 0.75},
                internal_manifest_hash="a" * 64,
                cache_hash="b" * 64,
                config={"quantile_method": "nearest_rank"},
                seed=20260729,
            )


def test_budget_calibration_rejects_non_preregistered_quantiles_method_and_duplicate_traces():
    common = {
        "internal_manifest_hash": "a" * 64,
        "cache_hash": "b" * 64,
        "seed": 20260729,
    }
    with pytest.raises(ValueError, match="0.25/0.50/0.75"):
        calibrate_budget_tiers(
            _observations(),
            quantiles={"Tight": 0.20, "Medium": 0.50, "Loose": 0.80},
            config={"quantile_method": "nearest_rank"},
            **common,
        )
    with pytest.raises(ValueError, match="nearest_rank"):
        calibrate_budget_tiers(
            _observations(),
            quantiles={"Tight": 0.25, "Medium": 0.50, "Loose": 0.75},
            config={"quantile_method": "linear"},
            **common,
        )
    duplicate = _observations()
    duplicate.append(dict(duplicate[0]))
    with pytest.raises(ValueError, match="duplicate"):
        calibrate_budget_tiers(
            duplicate,
            quantiles={"Tight": 0.25, "Medium": 0.50, "Loose": 0.75},
            config={"quantile_method": "nearest_rank"},
            **common,
        )
