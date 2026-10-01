"""Deterministic seeded property tests for the Phase 5 ML engine."""

from __future__ import annotations

import random

import pandas as pd

from backend.data_engine.contracts import (
    AnomalyInjection,
    AnomalyType,
    SyntheticCompanyConfig,
)
from backend.data_engine.ingest.synthetic import generate_company
from backend.ml_engine.baseline import rolling_rule_baseline
from backend.ml_engine.features import build_feature_frame
from backend.ml_engine.models import fit_isolation_forest


def _frame_with_magnitude(seed: int, magnitude: float) -> pd.DataFrame:
    config = SyntheticCompanyConfig(
        seed=seed,
        periods=24,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.MARGIN_COLLAPSE,
                start_month=18,
                duration_months=4,
                magnitude=magnitude,
            )
        ],
    )
    return build_feature_frame(generate_company(config).periods)


def test_larger_injection_ranks_more_anomalous() -> None:
    rng = random.Random(42)
    wins = 0
    trials = 5
    for _ in range(trials):
        seed = rng.randint(5000, 9000)
        mild = _frame_with_magnitude(seed, 0.2)
        severe = _frame_with_magnitude(seed, 0.8)
        mild_mean = sum(fit_isolation_forest(mild).anomaly_scores(mild)[17:21]) / 4
        severe_mean = sum(fit_isolation_forest(severe).anomaly_scores(severe)[17:21]) / 4
        if severe_mean >= mild_mean:
            wins += 1
    # Rank-CDF scores saturate; severe injections must win the majority.
    assert wins >= 3


def test_threshold_flag_consistency() -> None:
    from backend.ml_engine.models import threshold_from_expected_rate

    rng = random.Random(42)
    for _ in range(5):
        seed = rng.randint(5000, 9000)
        frame = _frame_with_magnitude(seed, 0.6)
        fitted = fit_isolation_forest(frame)
        threshold = threshold_from_expected_rate(fitted.train_decision, 0.1)
        decisions = fitted.decision_values(frame)
        flags = [(-v) >= threshold for v in decisions]
        scores = fitted.anomaly_scores(frame)
        # Flagged rows must score at least as high as unflagged rows.
        if any(flags) and not all(flags):
            assert min(s for s, f in zip(scores, flags, strict=True) if f) >= max(
                s for s, f in zip(scores, flags, strict=True) if not f
            )


def test_rule_baseline_monotone_in_magnitude() -> None:
    rng = random.Random(42)
    for _ in range(5):
        seed = rng.randint(5000, 9000)
        mild = sum(rolling_rule_baseline(_frame_with_magnitude(seed, 0.2)).scores[17:21])
        severe = sum(rolling_rule_baseline(_frame_with_magnitude(seed, 0.8)).scores[17:21])
        assert severe >= mild
