from a2a_dygrade_rl.evaluation.metrics_quality import mae, quadratic_weighted_kappa, rmse, within_1_accuracy


def test_quality_metrics():
    y_true = [0, 1, 2, 3]
    y_pred = [0, 2, 2, 3]
    assert mae(y_true, y_pred) == 0.25
    assert round(rmse(y_true, y_pred), 4) == 0.5
    assert within_1_accuracy(y_true, y_pred) == 1.0
    assert 0.0 <= quadratic_weighted_kappa(y_true, y_pred) <= 1.0
