from __future__ import annotations

from collections import defaultdict

import pytest

from a2a_dygrade_rl.datasets.internal_split import allocate_internal_item_splits


def _item(
    item_id: str,
    dataset: str,
    prompt_group: str,
    *,
    prompt: str | None = None,
    answer: str | None = None,
    leakage_id: str | None = None,
    split: str = "train",
) -> dict:
    return {
        "item_id": item_id,
        "dataset": dataset,
        "prompt": prompt or f"prompt-{prompt_group}",
        "student_answer": answer or f"answer-{item_id}",
        "metadata": {
            "prompt_group": prompt_group,
            "leakage_component_id": leakage_id or f"legacy-{item_id}",
            "split": split,
        },
    }


def _strict_fixture_items() -> list[dict]:
    items: list[dict] = []
    # 20份可完全利用的 strict paper：ASAP-SAS 50、SAS-Bench 30、DREsS 20。
    for index in range(50):
        items.append(_item(f"a{index}", "asap_sas", f"a-pg-{index}"))
    for index in range(30):
        items.append(_item(f"s{index}", "sas_bench", f"s-pg-{index}"))
    for index in range(20):
        items.append(_item(f"d{index}", "dress", f"d-pg-{index}"))
    # 构造传递关系：a0--a1 共享题目组，a1--a2 共享 legacy leakage id。
    items[0]["metadata"]["prompt_group"] = "transitive-pg"
    items[1]["metadata"]["prompt_group"] = "transitive-pg"
    items[1]["metadata"]["leakage_component_id"] = "transitive-leak"
    items[2]["metadata"]["leakage_component_id"] = "transitive-leak"
    # exact prompt-answer 跨不同 prompt_group 也必须合并。
    items[3]["prompt"] = "same exact prompt"
    items[3]["student_answer"] = "same exact answer"
    items[4]["prompt"] = "same exact prompt"
    items[4]["student_answer"] = "same exact answer"
    return items


def test_internal_split_is_component_atomic_deterministic_and_roughly_targeted():
    items = _strict_fixture_items()
    first = allocate_internal_item_splits(
        items,
        train_fit_ratio=0.8,
        seed=20260729,
        rule_version="internal_split_v14",
    )
    second = allocate_internal_item_splits(
        list(reversed(items)),
        train_fit_ratio=0.8,
        seed=20260729,
        rule_version="internal_split_v14",
    )

    assert first.manifest_rows == second.manifest_rows
    assert first.summary["assignment_unit"] == "item_component"
    assert first.summary["legacy_paper_assignment_count"] == 0
    assert first.summary["source_item_count"] == 100
    assert abs(first.summary["train_fit_ratio"] - 0.8) <= 0.05

    split_by_item = {row["item_id"]: row["internal_split"] for row in first.manifest_rows}
    assert len({split_by_item[item_id] for item_id in ("a0", "a1", "a2")}) == 1
    assert split_by_item["a3"] == split_by_item["a4"]

    components_by_split: dict[str, set[str]] = defaultdict(set)
    prompt_groups_by_split: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in first.manifest_rows:
        components_by_split[row["internal_split"]].add(row["component_id"])
        prompt_groups_by_split[row["internal_split"]].add((row["dataset"], row["prompt_group"]))
        assert row["source_split"] == "train"
        assert row["assignment_unit"] == "item_component"
        assert row["stable_hash"]
        assert row["component_size"] >= 1

    assert components_by_split["train_fit"].isdisjoint(components_by_split["train_calibration"])
    assert prompt_groups_by_split["train_fit"].isdisjoint(prompt_groups_by_split["train_calibration"])
    for split in ("train_fit", "train_calibration"):
        assert {row["dataset"] for row in first.manifest_rows if row["internal_split"] == split} == {
            "asap_sas",
            "sas_bench",
            "dress",
        }


def test_internal_split_rejects_dev_test_and_legacy_paper_assignment():
    items = _strict_fixture_items()
    items[0]["metadata"]["split"] = "dev"
    with pytest.raises(ValueError, match="仅允许外部 train"):
        allocate_internal_item_splits(items, train_fit_ratio=0.8, seed=7, rule_version="test")

    with pytest.raises(ValueError, match="禁止直接拆分旧 Paper"):
        allocate_internal_item_splits(
            _strict_fixture_items(),
            train_fit_ratio=0.8,
            seed=7,
            rule_version="test",
            assignment_unit="legacy_paper",
        )


def test_component_integrity_and_maximum_paper_count_outrank_exact_ratio():
    items = []
    # ASAP-SAS 只能按两个6-Item component 分配；精确20%不可达，但两个 split 仍可共构造5份 Paper。
    for component_index in range(2):
        for item_index in range(6):
            items.append(
                _item(
                    f"a_{component_index}_{item_index}",
                    "asap_sas",
                    f"a_component_{component_index}",
                )
            )
    for index in range(8):
        items.append(_item(f"s_{index}", "sas_bench", f"s_{index}"))
    for index in range(5):
        items.append(_item(f"d_{index}", "dress", f"d_{index}"))

    result = allocate_internal_item_splits(
        items,
        train_fit_ratio=0.8,
        seed=20260729,
        rule_version="test",
    )
    assert sum(result.summary["strict_paper_potential"].values()) == 5
    assert result.summary["absolute_ratio_deviation"] > 0
    split_by_component = {}
    for row in result.manifest_rows:
        split_by_component.setdefault(row["component_id"], row["internal_split"])
        assert split_by_component[row["component_id"]] == row["internal_split"]
