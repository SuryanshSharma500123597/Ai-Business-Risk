"""Property-style tests for the Scenario Engine (Phase 7).

Plain deterministic seeded randomization (``random.Random(42)``) — no
Hypothesis (testing.md records it is not installed). No twin execution.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from backend.core.errors import AppError, ErrorCode
from backend.simulation import scenarios as sc
from backend.simulation.scenarios import (
    CLAMP_TOLERANCE,
    FIELD_BOUNDS,
    PRESET_PARAMS,
    ScenarioOrigin,
)

SEED = 42
SAMPLES = 300


def _rng() -> random.Random:
    return random.Random(SEED)


def test_clamp_band_sweep_behaves_per_spec() -> None:
    """For every bounded field: inside ok, band clamps, beyond rejects."""
    rng = _rng()
    checked = 0
    for field, (lower, upper) in FIELD_BOUNDS.items():
        if upper is None:
            continue
        span = upper - lower
        for _ in range(SAMPLES // len(FIELD_BOUNDS)):
            value = rng.uniform(lower - span, upper + span)
            raw: dict[str, Any] = {"name": "sweep", field: value}
            lower_limit = lower * CLAMP_TOLERANCE if lower < 0 else lower / CLAMP_TOLERANCE
            upper_limit = upper * CLAMP_TOLERANCE if upper > 0 else upper / CLAMP_TOLERANCE
            if lower_limit == 0.0 and upper_limit == 0.0:
                continue
            if lower <= value <= upper:
                v = sc.validate_params(raw, origin=ScenarioOrigin.FORM)
                assert v.clamped == []
                assert getattr(v.params, field) == value
            elif lower_limit <= value < lower or upper < value <= upper_limit:
                v = sc.validate_params(raw, origin=ScenarioOrigin.FORM)
                assert field in v.clamped
            else:
                with pytest.raises(AppError) as exc:
                    sc.validate_params(raw, origin=ScenarioOrigin.FORM)
                assert exc.value.code == ErrorCode.SCENARIO_OUT_OF_BOUNDS
            checked += 1
    assert checked > 100


def test_round_trip_determinism() -> None:
    """Same input -> identical ValidatedScenario, twice, seeded fuzz."""
    rng = _rng()
    fields = list(FIELD_BOUNDS)
    for i in range(SAMPLES):
        raw: dict[str, Any] = {"name": f"fuzz-{i}"}
        for field in rng.sample(fields, 3):
            lower, upper = FIELD_BOUNDS[field]
            hi = upper if upper is not None else lower + 1000.0
            raw[field] = rng.uniform(lower, hi)
        a = sc.validate_params(raw, origin=ScenarioOrigin.FORM)
        b = sc.validate_params(raw, origin=ScenarioOrigin.FORM)
        assert a == b
        assert a.provenance.validated_params_hash == b.provenance.validated_params_hash


def test_all_presets_pass_validation() -> None:
    for preset_id in PRESET_PARAMS:
        v = sc.get_preset(preset_id)
        assert v.clamped == []
        for field in PRESET_PARAMS[preset_id]:
            lower, upper = FIELD_BOUNDS[field]
            value = getattr(v.params, field)
            assert value >= lower
            if upper is not None:
                assert value <= upper


def test_fraction_normalization_matches_twin_convention() -> None:
    """0.02 == 2pp and -0.15 == -15%: the D-6 contract with the twin."""
    v = sc.validate_params(
        {"name": "x", "interest_rate_change_pp": 2.0, "revenue_change_pct": -15.0},
        origin=ScenarioOrigin.FORM,
    )
    o = sc.to_overrides(v)
    assert o.rate_change == pytest.approx(0.02)
    assert o.revenue_change == pytest.approx(-0.15)
