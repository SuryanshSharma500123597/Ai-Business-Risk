"""Stage 5 adapter unit tests (log returns, CPI/FEDFUNDS scalars, builder)."""

from __future__ import annotations

import math

import pytest

from backend.data_engine.macro_inputs import (
    cpi_change_24m,
    fedfunds_current_and_median,
    gross_margin_change_24m,
)
from backend.data_engine.market_inputs import (
    align_beta_legs,
    aligned_returns_from_closes,
)
from backend.data_engine.risk_inputs import build_market_inputs
from backend.tests.unit.stage5_helpers import geometric_closes, macro_series, market_series


def test_stage5_adapter_log_returns_match_hand_computation() -> None:
    closes = [100.0, 110.0, 99.0]
    leg = aligned_returns_from_closes(market_series("EQ", closes))
    assert leg.returns == pytest.approx([math.log(1.1), math.log(99.0 / 110.0)])
    assert leg.dates[0].isoformat() == "2026-01-02"


def test_stage5_adapter_rejects_non_positive_close() -> None:
    with pytest.raises(ValueError, match="non-positive"):
        aligned_returns_from_closes(market_series("EQ", [100.0, 0.0]))


def test_stage5_adapter_beta_inner_join_returns_shared_dates() -> None:
    from datetime import date

    asset = market_series("E", geometric_closes(130, 0.01))
    benchmark = market_series("I", geometric_closes(130, 0.005), start=date(2026, 1, 6))
    asset_leg, bench_leg, joined = align_beta_legs(asset, benchmark)
    assert joined == 125
    assert asset_leg.dates == bench_leg.dates
    assert len(asset_leg.returns) == 124


def test_stage5_adapter_cpi_and_margin_helpers() -> None:
    cpi = macro_series("CPIAUCSL", [300.0 + i for i in range(24)])
    assert cpi_change_24m(cpi) == pytest.approx(23.0 / 300.0 * 100.0)
    assert cpi_change_24m(macro_series("CPIAUCSL", [300.0] * 23)) is None

    periods: list[dict[str, object]] = [
        {"revenue": 1000.0, "gross_profit": 400.0 - i} for i in range(24)
    ]
    assert gross_margin_change_24m(periods) == pytest.approx(-2.3)


def test_stage5_adapter_fedfunds_median_and_floor() -> None:
    fed = macro_series("FEDFUNDS", [2.0 + 0.05 * i for i in range(60)])
    current, median = fedfunds_current_and_median(fed)
    assert current == pytest.approx(4.95)
    assert median == pytest.approx(3.475)
    assert fedfunds_current_and_median(macro_series("F", [3.0] * 59)) == (None, None)


def test_stage5_builder_provenance_keys() -> None:
    inputs = build_market_inputs(
        equity=market_series("EQ", geometric_closes(40, 0.01)),
        fx=market_series("DEXINUS", geometric_closes(40, 0.002)),
        cpi=macro_series("CPIAUCSL", [300.0] * 24),
    )
    assert set(inputs.provenance) == {"equity_returns", "fx_returns", "cpi"}
    assert inputs.provenance["equity_returns"].observation_count == 40
