from a2a_dygrade_rl.evaluation.preliminary_validation import deterministic_partition


def test_deterministic_partition_is_stable_and_disjoint():
    item_ids = [f"item_{index}" for index in range(20)]
    calibration_a, evaluation_a = deterministic_partition(item_ids)
    calibration_b, evaluation_b = deterministic_partition(reversed(item_ids))
    assert calibration_a == calibration_b
    assert evaluation_a == evaluation_b
    assert len(calibration_a) == 10
    assert len(evaluation_a) == 10
    assert set(calibration_a).isdisjoint(evaluation_a)
    assert set(calibration_a) | set(evaluation_a) == set(item_ids)
