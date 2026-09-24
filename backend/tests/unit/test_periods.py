"""Calendarization / period normalization tests (data.md normalization scope)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.data_engine.contracts import Frequency, PeriodFinancials
from backend.data_engine.normalize.periods import (
    aggregate_chunk,
    chunk_by_step,
    find_gaps,
    infer_frequency,
    sort_periods,
    to_frequency,
    trailing_window,
)


def month_period(year: int, month: int, revenue: float, cash: float = 10.0) -> PeriodFinancials:
    end_year = year + (month - 1) // 12
    end_month = (month - 1) % 12 + 1
    end = date(end_year, end_month, 28)
    return PeriodFinancials(
        period_start=date(end.year, end.month, 1),
        period_end=end,
        frequency="monthly",
        source="synthetic",
        revenue=revenue,
        cogs=revenue * 0.6,
        gross_profit=revenue * 0.4,
        cash=cash,
        receivables=revenue * 0.15,
        inventory=revenue * 0.1,
        payables=revenue * 0.12,
        current_assets=cash + revenue * 0.25,
        current_liabilities=revenue * 0.2,
        total_assets=cash + revenue,
        total_liabilities=revenue * 0.5,
        equity=cash + revenue * 0.5,
        interest_expense=1.0,
        ocf=revenue * 0.1,
        capex=revenue * 0.02,
    )


def twelve_months_2023() -> list[PeriodFinancials]:
    return [month_period(2022, m + 1, 100.0 * (m + 1)) for m in range(12)]


def test_sort_periods() -> None:
    months = twelve_months_2023()
    shuffled = list(reversed(months))
    ordered = sort_periods(shuffled)
    ends = [p.period_end for p in ordered]
    assert ends == sorted(ends)


def test_infer_frequency() -> None:
    monthly = twelve_months_2023()
    assert infer_frequency(monthly) is Frequency.MONTHLY
    quarterly = monthly[::3]
    assert infer_frequency(quarterly) is Frequency.QUARTERLY
    two_years = twelve_months_2023() + [
        month_period(2023, m + 1, 100.0 * (m + 1)) for m in range(12)
    ]
    assert infer_frequency(two_years[::12]) is Frequency.ANNUAL
    assert infer_frequency(monthly[:1]) is None


def test_find_gaps() -> None:
    months = twelve_months_2023()
    assert find_gaps(months) == []
    with_hole = months[:5] + months[7:]
    gaps = find_gaps(with_hole)
    assert len(gaps) == 1
    assert gaps[0][0].month == 5  # after May


def test_chunk_by_step() -> None:
    months = twelve_months_2023()
    chunks = chunk_by_step(months, 3)
    assert len(chunks) == 4
    assert all(len(c) == 3 for c in chunks)
    partial = chunk_by_step(months[:7], 3)
    assert len(partial) == 3 and len(partial[-1]) == 1


def test_aggregate_chunk_sums_flows_keeps_stocks() -> None:
    def val(x: float | None) -> float:
        assert x is not None
        return x

    months = twelve_months_2023()
    quarter = aggregate_chunk(months[:3], Frequency.QUARTERLY)
    assert quarter.frequency is Frequency.QUARTERLY
    assert quarter.quarter == 1
    assert quarter.revenue == pytest.approx(100.0 + 200.0 + 300.0)
    assert val(quarter.gross_profit) == pytest.approx(val(quarter.revenue) - val(quarter.cogs))
    # stocks come from the last month of the chunk
    assert quarter.cash == months[2].cash
    assert quarter.total_assets == months[2].total_assets


def test_to_frequency_annual() -> None:
    months = twelve_months_2023()
    annual, notes = to_frequency(months, Frequency.ANNUAL)
    assert notes == []
    assert len(annual) == 1
    assert annual[0].frequency is Frequency.ANNUAL
    assert annual[0].fiscal_year == months[-1].period_end.year
    assert annual[0].quarter is None
    assert annual[0].revenue == pytest.approx(sum(p.revenue for p in months))


def test_to_frequency_trailing_partial_dropped() -> None:
    months = twelve_months_2023()[:10]  # 10 months -> 3 full quarters + 1 stray
    quarterly, notes = to_frequency(months, Frequency.QUARTERLY)
    assert len(quarterly) == 3
    assert any("trailing partial" in n for n in notes)


def test_to_frequency_passthrough_and_non_monthly() -> None:
    months = twelve_months_2023()
    monthly, notes = to_frequency(months, Frequency.MONTHLY)
    assert notes == [] and len(monthly) == 12
    annual_input = [m.model_copy(update={"frequency": "annual"}) for m in months[::12]]
    result, notes = to_frequency(annual_input, Frequency.ANNUAL)
    assert any("only monthly input is aggregated" in n for n in notes)
    assert len(result) == 1


def test_trailing_window() -> None:
    months = twelve_months_2023()
    window = trailing_window(months, 6)
    assert len(window) == 6
    assert window[-1].period_end == months[-1].period_end
    assert window[0].period_end == months[6].period_end
