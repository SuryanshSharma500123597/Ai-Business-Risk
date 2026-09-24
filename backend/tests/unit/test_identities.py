"""Accounting identity tests (frozen data.md §3 rule 2, 0.5% tolerance)."""

from __future__ import annotations

from datetime import date

from backend.data_engine.contracts import PeriodFinancials, ShareEntry, SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.data_engine.validate.identities import (
    balance_sheet_identity,
    bucket_sums_to_one,
    check_all_periods,
    check_period,
    current_assets_composition,
    current_assets_floor,
    debt_composition,
    gross_profit_identity,
)


def period(**overrides: object) -> PeriodFinancials:
    values: dict[str, object] = {
        "period_start": date(2024, 1, 1),
        "period_end": date(2024, 1, 31),
        "frequency": "monthly",
        "source": "synthetic",
        "revenue": 1000.0,
        "cogs": 600.0,
        "gross_profit": 400.0,
        "cash": 100.0,
        "receivables": 150.0,
        "inventory": 90.0,
        "current_assets": 340.0,
        "current_liabilities": 200.0,
        "total_assets": 900.0,
        "total_liabilities": 500.0,
        "equity": 400.0,
        "interest_expense": 5.0,
    }
    values.update(overrides)
    return PeriodFinancials(**values)  # pyright: ignore[reportCallIssue]


def test_valid_period_has_no_violations() -> None:
    assert check_period(period()) == []


def test_balance_sheet_identity_tolerance() -> None:
    assert balance_sheet_identity(period())
    # 0.3% drift is inside the frozen 0.5% tolerance
    assert balance_sheet_identity(period(total_assets=902.7))
    # 2% drift violates
    assert not balance_sheet_identity(period(total_assets=918.0))
    assert not balance_sheet_identity(period(equity=None))


def test_gross_profit_identity() -> None:
    assert gross_profit_identity(period())
    assert not gross_profit_identity(period(gross_profit=500.0))
    assert not gross_profit_identity(period(revenue=None))


def test_current_assets_composition_and_floor() -> None:
    assert current_assets_composition(period())
    assert not current_assets_composition(period(current_assets=350.0))
    assert current_assets_floor(period())
    assert not current_assets_floor(period(cash=400.0))
    assert not current_assets_floor(period(receivables=400.0))


def test_debt_composition_optional() -> None:
    assert debt_composition(period())  # None components -> trivially ok
    assert debt_composition(period(total_debt=300.0, st_debt=120.0, lt_debt=180.0))
    assert not debt_composition(period(total_debt=300.0, st_debt=100.0, lt_debt=100.0))


def test_bucket_share_sum() -> None:
    ok = [ShareEntry(name="a", share=0.7), ShareEntry(name="b", share=0.3)]
    bad = [ShareEntry(name="a", share=0.7), ShareEntry(name="b", share=0.2)]
    assert bucket_sums_to_one(ok)
    assert not bucket_sums_to_one(bad)
    assert bucket_sums_to_one(None)  # absence is a coverage issue, not identity


def test_check_all_periods_map() -> None:
    good = period()
    bad = period(total_assets=9999.0)
    result = check_all_periods([good, bad])
    assert list(result) == [1]
    assert "assets != liabilities + equity" in result[1]


def test_generator_output_identity_clean() -> None:
    for seed in (1001, 1002, 1003, 1004, 1005):
        company = generate_company(SyntheticCompanyConfig(seed=seed))
        violations = check_all_periods(company.periods)
        assert violations == {}, f"seed {seed}: {violations}"
