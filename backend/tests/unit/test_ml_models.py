"""Unit tests for IF wrapper semantics, thresholding, and the rule baseline."""

from __future__ import annotations

import pandas as pd

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.ml_engine.baseline import rolling_rule_baseline
from backend.ml_engine.features import build_feature_frame
from backend.ml_engine.models import (
    fit_isolation_forest,
    threshold_from_expected_rate,
)


def _frame(seed: int = 2001) -> pd.DataFrame:
    company = generate_company(SyntheticCompanyConfig(seed=seed, periods=24))
    return build_feature_frame(company.periods)


def test_anomaly_scores_bounded_and_rank_consistent() -> None:
    fitted = fit_isolation_forest(_frame())
    frame = _frame()
    scores = fitted.anomaly_scores(frame)
    decisions = fitted.decision_values(frame)
    assert all(0.0 <= s <= 1.0 for s in scores)
    # Lower decision_function (more anomalous) must rank higher in score.
    order_score = sorted(range(len(scores)), key=lambda i: scores[i])
    order_neg_decision = sorted(range(len(decisions)), key=lambda i: -decisions[i])
    assert order_score == order_neg_decision


def test_threshold_flags_expected_share() -> None:
    fitted = fit_isolation_forest(_frame())
    threshold = threshold_from_expected_rate(fitted.train_decision, 0.1)
    flags = [(-v) >= threshold for v in fitted.train_decision]
    assert 1 <= sum(flags) <= 4


def test_repeat_fit_is_deterministic() -> None:
    first = fit_isolation_forest(_frame())
    second = fit_isolation_forest(_frame())
    assert first.decision_values(_frame()) == second.decision_values(_frame())
    assert first.anomaly_scores(_frame()) == second.anomaly_scores(_frame())


def test_empty_training_frame_rejected() -> None:
    import pandas as pd

    try:
        fit_isolation_forest(pd.DataFrame({"a": []}))
    except ValueError as exc:
        assert "no complete feature rows" in str(exc)
    else:  # pragma: no cover - must raise
        raise AssertionError("expected ValueError")


def test_rule_baseline_trailing_only_and_deterministic() -> None:
    frame = _frame()
    first = rolling_rule_baseline(frame)
    second = rolling_rule_baseline(frame)
    assert first.flags == second.flags
    assert first.scores == second.scores
    # Early periods lack trailing history, so no flags are possible.
    assert first.flags[0] is False
    assert all(isinstance(b, list) for b in first.breached_features)


def test_rule_baseline_detects_injected_window() -> None:
    from backend.data_engine.contracts import AnomalyInjection, AnomalyType

    config = SyntheticCompanyConfig(
        seed=2001,
        periods=24,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.MARGIN_COLLAPSE,
                start_month=18,
                duration_months=4,
                magnitude=0.6,
            )
        ],
    )
    company = generate_company(config)
    frame = build_feature_frame(company.periods)
    result = rolling_rule_baseline(frame)
    # At least one injected period (months 18-21, 0-based rows 17-20) flags.
    assert any(result.flags[17:21])


def test_rule_baseline_skips_non_numeric_cells() -> None:
    import pandas as pd

    frame = pd.DataFrame({"x": [None] * 24})
    result = rolling_rule_baseline(frame)
    assert len(result.flags) == 24
    assert not any(result.flags)


def test_robust_params_fallback_for_empty_column() -> None:
    import pandas as pd

    from backend.ml_engine.models import _robust_params

    medians, iqrs = _robust_params(pd.DataFrame({"a": [float("nan")]}))
    assert medians["a"] == 0.0
    assert iqrs["a"] == 1.0


def test_threshold_rejects_out_of_range_rate() -> None:
    import pytest

    with pytest.raises(ValueError, match="expected_rate"):
        threshold_from_expected_rate([0.0, -1.0], 0.0)
    with pytest.raises(ValueError, match="expected_rate"):
        threshold_from_expected_rate([0.0, -1.0], 1.0)
