"""Currency / FX application tests (frozen data.md FD-1)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.data_engine.contracts import PeriodFinancials
from backend.data_engine.normalize.currency import (
    SUPPORTED_CURRENCIES,
    as_of_rate,
    convert_period,
    convert_series,
    validate_currency,
)


def usd_period(day: int, revenue: float = 1000.0) -> PeriodFinancials:
    return PeriodFinancials(
        period_start=date(2024, 6, 1),
        period_end=date(2024, 6, day),
        frequency="monthly",
        source="edgar",
        revenue=revenue,
        cogs=revenue * 0.6,
        gross_profit=revenue * 0.4,
        cash=100.0,
        total_assets=900.0,
        total_liabilities=500.0,
        equity=400.0,
        interest_expense=5.0,
        customers=[{"name_hash": "x", "share": 1.0}],
    )


FX = {date(2024, 6, 10): 83.0, date(2024, 6, 20): 84.0, date(2024, 6, 30): 85.0}


def test_validate_currency() -> None:
    assert validate_currency("inr") == "INR"
    assert validate_currency("USD") == "USD"
    with pytest.raises(ValueError, match="unsupported currency"):
        validate_currency("GBP")
    assert set(SUPPORTED_CURRENCIES) == {"INR", "USD", "EUR"}


def test_as_of_rate_previous_carry() -> None:
    assert as_of_rate(FX, date(2024, 6, 25)) == 84.0
    assert as_of_rate(FX, date(2024, 6, 30)) == 85.0
    assert as_of_rate(FX, date(2024, 5, 1)) == 83.0  # carry-back to earliest
    assert as_of_rate({}, date(2024, 6, 1)) is None


def test_convert_period_scales_money_not_shares() -> None:
    def val(x: float | None) -> float:
        assert x is not None
        return x

    p = usd_period(15)
    converted = convert_period(p, 84.0)
    assert val(converted.revenue) == pytest.approx(val(p.revenue) * 84.0)
    assert val(converted.cash) == pytest.approx(val(p.cash) * 84.0)
    assert val(converted.equity) == pytest.approx(val(p.equity) * 84.0)
    # gross profit identity recomputed exactly
    assert val(converted.gross_profit) == pytest.approx(
        val(converted.revenue) - val(converted.cogs)
    )
    # shares untouched
    assert converted.customers == p.customers
    with pytest.raises(ValueError, match="positive"):
        convert_period(p, 0.0)


def test_convert_series_notes_and_carry_back() -> None:
    def val(x: float | None) -> float:
        assert x is not None
        return x

    early = usd_period(5)  # before the earliest FX date -> carry-back note
    mid = usd_period(25)  # as-of Jun 20 rate = 84.0
    converted, notes = convert_series([early, mid], FX)
    assert val(converted[0].revenue) == pytest.approx(val(early.revenue) * 83.0)  # carry-back
    assert val(converted[1].revenue) == pytest.approx(val(mid.revenue) * 84.0)
    assert any("carry-back" in n for n in notes)


def test_convert_series_empty_series_noop() -> None:
    p = usd_period(15)
    converted, notes = convert_series([p], {})
    assert converted[0] == p
    assert any("no conversion" in n for n in notes)
