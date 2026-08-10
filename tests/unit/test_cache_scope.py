from __future__ import annotations

from pathlib import Path

import pytest

from a2a_dygrade_rl.agents.cache import (
    build_context_support_catalog,
    resolve_cache_scope,
)
from a2a_dygrade_rl.utils.io import write_csv


def _items() -> list[dict]:
    return [
        {"item_id": "train_a", "metadata": {"split": "train"}},
        {"item_id": "train_b", "metadata": {"split": "train"}},
        {"item_id": "dev_a", "metadata": {"split": "dev"}},
        {"item_id": "test_a", "metadata": {"split": "test"}},
    ]


def test_internal_cache_scope_must_come_from_internal_item_manifest(tmp_path: Path):
    manifest = tmp_path / "internal_item_split_manifest.csv"
    write_csv(
        manifest,
        [
            {"item_id": "train_a", "source_split": "train", "internal_split": "train_fit"},
            {"item_id": "train_b", "source_split": "train", "internal_split": "train_calibration"},
        ],
        ["item_id", "source_split", "internal_split"],
    )
    scope = resolve_cache_scope(
        _items(),
        split="train_fit",
        execution_mode="formal_experiment",
        internal_item_manifest_path=manifest,
    )
    assert scope.item_ids == ("train_a",)
    assert scope.scope_source == "internal_item_split_manifest"
    assert len(scope.scope_fingerprint) == 64
    assert scope.formal_eligible is True

    with pytest.raises(ValueError, match="internal_item_split_manifest"):
        resolve_cache_scope(_items(), split="train_fit", execution_mode="formal_experiment")


def test_formal_dev_scope_requires_external_manifest_and_rejects_legacy_paper(tmp_path: Path):
    external = tmp_path / "split_manifest.csv"
    write_csv(external, [{"item_id": "dev_a", "split": "dev"}], ["item_id", "split"])
    scope = resolve_cache_scope(
        _items(),
        split="dev",
        execution_mode="formal_experiment",
        external_split_manifest_path=external,
    )
    assert scope.item_ids == ("dev_a",)
    assert scope.scope_source == "external_split_manifest"

    with pytest.raises(ValueError, match="external split manifest"):
        resolve_cache_scope(_items(), split="dev", execution_mode="formal_experiment")

    legacy = tmp_path / "paper_train_0001.jsonl"
    legacy.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="旧 Paper"):
        resolve_cache_scope(
            _items(),
            split="train_fit",
            execution_mode="formal_experiment",
            internal_item_manifest_path=legacy,
        )


def test_context_support_catalog_is_finite_deterministic_and_fixture_marked():
    config = {
        "arbitrator_contexts": [
            ["CheapAgent", "StrongAgent"],
            ["CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent"],
        ]
    }
    first = build_context_support_catalog(
        config,
        selected_agent_ids=["StrongAgent", "CheapAgent", "MidAgent", "EvidenceAgent", "ArbitratorAgent"],
        execution_mode="fixture_smoke",
        scope_source="internal_item_split_manifest",
        scope_fingerprint="a" * 64,
    )
    second = build_context_support_catalog(
        config,
        selected_agent_ids=["ArbitratorAgent", "EvidenceAgent", "MidAgent", "CheapAgent", "StrongAgent"],
        execution_mode="fixture_smoke",
        scope_source="internal_item_split_manifest",
        scope_fingerprint="a" * 64,
    )
    assert first == second
    assert first["formal_eligible"] is False
    assert first["online_agent_calls"] == 0
    assert len(first["catalog_hash"]) == 64
    assert first["arbitrator_contexts"] == [
        ["CheapAgent", "MidAgent", "StrongAgent", "EvidenceAgent"],
        ["CheapAgent", "StrongAgent"],
    ]


def test_formal_cache_scope_rejects_fixture_marked_items_and_manifests(tmp_path: Path):
    items = [{"item_id": "fixture_a", "metadata": {"split": "train", "fixture": True, "formal_eligible": False}}]
    manifest = tmp_path / "internal_item_split_manifest.csv"
    write_csv(
        manifest,
        [{"item_id": "fixture_a", "source_split": "train", "internal_split": "train_fit", "formal_eligible": False}],
        ["item_id", "source_split", "internal_split", "formal_eligible"],
    )
    with pytest.raises(ValueError, match="Fixture"):
        resolve_cache_scope(
            items,
            split="train_fit",
            execution_mode="formal_experiment",
            internal_item_manifest_path=manifest,
        )

    normal_items = [{"item_id": "manifest_fixture", "metadata": {"split": "train"}}]
    manifest_only = tmp_path / "internal_item_split_manifest_only.csv"
    write_csv(
        manifest_only,
        [{"item_id": "manifest_fixture", "source_split": "train", "internal_split": "train_fit", "formal_eligible": False}],
        ["item_id", "source_split", "internal_split", "formal_eligible"],
    )
    with pytest.raises(ValueError, match="Fixture"):
        resolve_cache_scope(
            normal_items,
            split="train_fit",
            execution_mode="formal_experiment",
            internal_item_manifest_path=manifest_only,
        )



def test_context_support_catalog_allows_base_agent_only_cache_without_arbitrator_contexts():
    catalog = build_context_support_catalog(
        {},
        selected_agent_ids=["CheapAgent"],
        execution_mode="fixture_smoke",
        scope_source="item_metadata_fixture_compat",
        scope_fingerprint="a" * 64,
    )
    assert catalog["agent_ids"] == ["CheapAgent"]
    assert catalog["arbitrator_contexts"] == []

    with pytest.raises(ValueError):
        build_context_support_catalog(
            {},
            selected_agent_ids=[],
            execution_mode="fixture_smoke",
            scope_source="item_metadata_fixture_compat",
            scope_fingerprint="a" * 64,
        )
