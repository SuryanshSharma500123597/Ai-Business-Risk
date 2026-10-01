"""Property-based Tests for Risk Engine (Spec §10, §30).

Uses randomized property generation to verify numerical invariants, score monotonicity,
clamping boundaries, piecewise continuity, and exact additive contribution reconciliation.
"""

import random

import pytest

from backend.risk_engine.contracts import MetricResult, MetricStatus
from backend.risk_engine.registry import build_default_registry, interpolate_score
from backend.risk_engine.scoring import aggregate_composite, aggregate_dimension


def test_score_clamping_invariant():
    rng = random.Random(42)
    anchors = [(10.0, 90.0), (20.0, 65.0), (30.0, 45.0), (40.0, 25.0)]

    for _ in range(200):
        val = rng.uniform(-1000.0, 1000.0)
        score = interpolate_score(val, anchors)
        assert score is not None
        assert 0.0 <= score <= 100.0


def test_score_monotonicity():
    rng = random.Random(42)
    anchors = [(10.0, 90.0), (20.0, 65.0), (30.0, 45.0), (40.0, 25.0)]

    for _ in range(100):
        v1 = rng.uniform(10.0, 40.0)
        v2 = rng.uniform(10.0, 40.0)
        score1 = interpolate_score(v1, anchors)
        score2 = interpolate_score(v2, anchors)
        assert score1 is not None and score2 is not None

        # For gross margin: higher value -> lower risk score
        if v1 <= v2:
            assert score1 >= score2
        else:
            assert score1 <= score2


def test_dimension_additive_contribution_invariant():
    rng = random.Random(42)

    for _ in range(50):
        n = rng.randint(1, 10)
        scores = [rng.uniform(0.0, 100.0) for _ in range(n)]
        metrics = [
            MetricResult(
                metric_id=f"m_{i}",
                name=f"Metric {i}",
                dimension="financial_strength",
                value=10.0,
                score=s,
                status=MetricStatus.VALID,
            )
            for i, s in enumerate(scores)
        ]

        dim_res = aggregate_dimension("financial_strength", metrics)
        assert dim_res.score is not None

        metric_contrib_sum = sum(
            m.contribution_to_dimension for m in dim_res.metrics if m.score is not None
        )
        assert pytest.approx(metric_contrib_sum, abs=1e-5) == dim_res.score


def test_composite_additive_contribution_invariant():
    rng = random.Random(42)

    for _ in range(50):
        scores_dict = {
            "d1": rng.uniform(0.0, 100.0),
            "d2": rng.uniform(0.0, 100.0),
            "d3": rng.uniform(0.0, 100.0),
        }
        dim_results = {}
        for dim_id, score in scores_dict.items():
            metrics = [
                MetricResult(
                    metric_id=f"{dim_id}_m1",
                    name="Test Metric",
                    dimension=dim_id,
                    value=10.0,
                    score=score,
                    status=MetricStatus.VALID,
                )
            ]
            dim_results[dim_id] = aggregate_dimension(dim_id, metrics)

        comp = aggregate_composite(dim_results)
        assert pytest.approx(comp.total_contributions, abs=1e-5) == comp.score


def test_property_interpolation_is_continuous_at_every_registered_anchor():
    """risk-engine.md §10.2: continuity at anchors, checked for every registry formula."""
    checked = 0
    for definition in build_default_registry().list_metrics():
        anchors = definition.anchors
        for value, expected in anchors:
            checked += 1
            assert interpolate_score(value, anchors) == pytest.approx(expected, abs=1e-12)

            # The mapping must approach the anchor score from both sides.
            step = max(1e-6, abs(value) * 1e-6)
            left = interpolate_score(value - step, anchors)
            right = interpolate_score(value + step, anchors)
            assert left is not None and right is not None
            assert left == pytest.approx(expected, abs=1e-3)
            assert right == pytest.approx(expected, abs=1e-3)
    assert checked > 0


def test_property_pure_ratios_are_scale_invariant():
    """risk-engine.md §10.2: scale invariance for pure ratios (currency cancels)."""
    rng = random.Random(2026)
    factor = 1000.0
    checked = 0
    for definition in build_default_registry().list_metrics():
        anchors = definition.anchors
        scaled_anchors = [(x * factor, y) for x, y in anchors]
        low, high = anchors[0][0], anchors[-1][0]
        for _ in range(20):
            value = rng.uniform(low, high)
            unscaled = interpolate_score(value, anchors)
            rescaled = interpolate_score(value * factor, scaled_anchors)
            assert unscaled is not None and rescaled is not None
            assert unscaled == pytest.approx(rescaled, abs=1e-9)
            checked += 1
    assert checked > 0


def test_property_monotonic_metrics_respond_in_the_band_direction():
    """risk-engine.md §10.2: monotonicity — a worse value must not lower the score."""
    rng = random.Random(11)
    checked = 0
    for definition in build_default_registry().list_metrics():
        anchors = definition.anchors
        scores = [score for _, score in anchors]
        increasing = all(a <= b for a, b in zip(scores, scores[1:], strict=False))
        decreasing = all(a >= b for a, b in zip(scores, scores[1:], strict=False))
        if not increasing and not decreasing:
            continue
        checked += 1
        xs = [x for x, _ in anchors]
        for _ in range(25):
            v1 = rng.uniform(xs[0], xs[-1])
            v2 = rng.uniform(xs[0], xs[-1])
            s1 = interpolate_score(v1, anchors)
            s2 = interpolate_score(v2, anchors)
            assert s1 is not None and s2 is not None
            if v1 <= v2:
                assert s1 <= s2 if increasing else s1 >= s2
            else:
                assert s1 >= s2 if increasing else s1 <= s2
    assert checked > 0


def test_property_two_sided_metrics_are_not_monotone():
    """risk-engine.md §6: DPO is two-sided — both a low and a high value are risky."""
    definition = build_default_registry().get("dpo")
    assert definition is not None
    anchors = definition.anchors

    trough_low = interpolate_score(30.0, anchors)
    trough = interpolate_score(60.0, anchors)
    trough_high = interpolate_score(120.0, anchors)
    assert trough_low is not None and trough is not None and trough_high is not None

    # Risk falls to the 60-day trough, then rises again.
    assert trough_low > trough
    assert trough_high > trough
    # Outside the anchor range the score is clamped to the nearest end.
    assert interpolate_score(0.0, anchors) == 60.0
