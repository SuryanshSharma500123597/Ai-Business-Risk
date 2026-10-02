"""Unit tests for the frozen §1 twin parameter derivation (Phase 6).

Covers every parameter in docs/01_architecture/simulation.md §1: the trailing
window rules, the clamps, the documented fallbacks, the OLS opex split and its
degenerate case, and the disclosure records that separate a measured input from
an assumed one.
"""

from __future__ import annotations

import inspect
import math
from datetime import date

import pytest
from pydantic import ValidationError

from backend.data_engine.contracts import (
    CommodityExposure,
    CompanyDataset,
    CompanyProfile,
    DebtScheduleEntry,
    Frequency,
    FxExposure,
    PeriodFinancials,
    RateExposure,
    Sector,
)
from backend.simulation.assumptions import (
    BASE_RATE_FALLBACK,
    FALLBACK_COMMODITY_SHARE,
    FALLBACK_FLOATING_SHARE,
    FALLBACK_FX_SHARE,
    OPEX_BUFFER_MULTIPLE,
    OPEX_REVOLVER_MULTIPLE,
    PASS_THROUGH,
    InsufficientHistoryError,
    derive_assumptions,
    derive_capex,
    derive_da,
    derive_growth,
    derive_opex_split,
    derive_tax_rate,
    derive_wc_days,
    has_effective_tax,
)
from backend.simulation.contracts import ParameterTag, SimulationAssumptions


def period(index: int, **overrides: object) -> PeriodFinancials:
    """One canonical monthly period with sane, non-degenerate defaults."""
    month = 1 + (index % 12)
    base: dict[str, object] = {
        "period_start": date(2024, month, 1),
        "period_end": date(2024, month, 28),
        "frequency": Frequency.MONTHLY,
        "source": "test",
        "revenue": 1000.0,
        "cogs": 600.0,
        "opex": 200.0,
        "da": 50.0,
        "ebit": 150.0,
        "interest_expense": 50.0,
        "tax": 25.0,
        "net_income": 75.0,
        "cash": 500.0,
        "receivables": 100.0,
        "inventory": 60.0,
        "payables": 30.0,
        "total_debt": 400.0,
        "capex": 40.0,
    }
    base.update(overrides)
    return PeriodFinancials(**base)


def dataset(periods: list[PeriodFinancials]) -> CompanyDataset:
    return CompanyDataset(
        profile=CompanyProfile(name="Twin Test Co", sector=Sector.MANUFACTURING, currency="INR"),
        periods=periods,
    )


def twelve(**last_overrides: object) -> list[PeriodFinancials]:
    return [period(i) for i in range(11)] + [period(11, **last_overrides)]


# --- growth ----------------------------------------------------------------


def test_growth_is_zero_for_flat_revenue() -> None:
    assert derive_growth([100.0] * 12) == pytest.approx(0.0, abs=1e-12)


def test_growth_annualises_the_monthly_compound_rate() -> None:
    # 1% every month compounds to 1.01**12 - 1 ~ 12.68% a year.
    revenue = [100.0 * (1.01**i) for i in range(12)]
    assert derive_growth(revenue) == pytest.approx(1.01**12 - 1.0, rel=1e-12)


def test_growth_is_zero_when_the_window_is_unusable() -> None:
    assert derive_growth([]) == 0.0
    assert derive_growth([0.0, 100.0]) == 0.0


# --- opex split ------------------------------------------------------------


def test_opex_split_recovers_an_exact_linear_relationship() -> None:
    revenue = [100.0, 200.0, 300.0, 400.0, 500.0]
    opex = [50.0 + 0.25 * r for r in revenue]
    fixed, variable, fallback = derive_opex_split(opex, revenue)
    assert fixed == pytest.approx(50.0, rel=1e-9)
    assert variable == pytest.approx(0.25, rel=1e-9)
    assert fallback is False


def test_opex_split_falls_back_on_flat_revenue() -> None:
    # A singular design matrix cannot identify a slope, so §1's fallback applies.
    fixed, variable, fallback = derive_opex_split([10.0, 20.0, 30.0], [100.0, 100.0, 100.0])
    assert fallback is True
    assert fixed == pytest.approx(5.0)  # 0.5 * opex0
    assert variable == pytest.approx(0.05)  # 0.5 * opex0 / rev0


def test_opex_split_falls_back_when_the_slope_would_be_negative() -> None:
    # Opex falling as revenue rises implies v < 0, which the frozen F, v >= 0
    # constraint forbids, so the documented fallback is used instead.
    _fixed, _variable, fallback = derive_opex_split(
        [400.0, 300.0, 200.0, 100.0], [100.0, 200.0, 300.0, 400.0]
    )
    assert fallback is True


# --- simple series derivations ---------------------------------------------


def test_da_and_capex_use_the_trailing_mean() -> None:
    assert derive_da([10.0, 20.0, 30.0]) == (20.0, False)
    assert derive_capex([5.0, 15.0]) == (10.0, False)


def test_missing_da_and_capex_report_a_fallback() -> None:
    assert derive_da([]) == (0.0, True)
    assert derive_capex([]) == (0.0, True)


def test_effective_tax_rate_is_tax_over_ebit_minus_interest() -> None:
    periods = [period(0, ebit=150.0, interest_expense=50.0, tax=25.0)]
    assert has_effective_tax(periods) is True
    assert derive_tax_rate(periods) == pytest.approx(0.25)


def test_tax_rate_falls_back_when_history_has_no_positive_ebt() -> None:
    periods = [period(0, ebit=40.0, interest_expense=50.0, tax=0.0)]
    assert has_effective_tax(periods) is False
    assert derive_tax_rate(periods) == 0.25


def test_working_capital_days_convert_stocks_to_days() -> None:
    dso, fallback = derive_wc_days([period(0, receivables=100.0)], "receivables", [1000.0])
    assert dso == pytest.approx(3.0)  # 100/1000*30
    assert fallback is False


def test_working_capital_days_fall_back_when_absent() -> None:
    # receivables is None, so no month can contribute a ratio at all.
    assert derive_wc_days([period(0, receivables=None)], "receivables", [1000.0]) == (0.0, True)


# --- full derivation -------------------------------------------------------

_EXPECTED_PARAMETERS = {
    "growth_rate",
    "cogs_ratio",
    "fixed_cost",
    "variable_cost_ratio",
    "da_monthly",
    "tax_rate",
    "base_rate",
    "floating_debt_share",
    "fx_import_cost_share",
    "fx_revenue_share",
    "commodity_cost_share",
    "dso",
    "dio",
    "dpo",
    "capex_monthly",
    "revenue_capacity",
    "min_cash_buffer",
    "revolver_cap",
    "pass_through",
    "fx_demand_elasticity",
    "initial_debt",
}


def test_derivation_reports_every_frozen_parameter() -> None:
    _assumptions, records, fallbacks = derive_assumptions(dataset([period(i) for i in range(12)]))
    assert _EXPECTED_PARAMETERS <= {r.parameter for r in records}
    assert set(fallbacks) == {r.parameter for r in records if r.fallback_used}


def test_derivation_uses_exposure_contracts_when_present() -> None:
    periods = twelve(
        fx_exposure=FxExposure(foreign_revenue_share=0.4, import_cost_share=0.3),
        commodity_exposure=CommodityExposure(input="steel", cost_share=0.25),
        rate_exposure=RateExposure(floating_debt_share=0.6),
    )
    assumptions, _records, fallbacks = derive_assumptions(dataset(periods))
    assert assumptions.fx_revenue_share == pytest.approx(0.4)
    assert assumptions.fx_import_cost_share == pytest.approx(0.3)
    assert assumptions.commodity_cost_share == pytest.approx(0.25)
    assert assumptions.floating_debt_share == pytest.approx(0.6)
    assert "floating_debt_share" not in fallbacks


def test_derivation_falls_back_when_exposures_are_absent() -> None:
    assumptions, _records, fallbacks = derive_assumptions(dataset([period(i) for i in range(12)]))
    assert assumptions.fx_revenue_share == FALLBACK_FX_SHARE
    assert assumptions.fx_import_cost_share == FALLBACK_FX_SHARE
    assert assumptions.commodity_cost_share == FALLBACK_COMMODITY_SHARE
    assert assumptions.floating_debt_share == FALLBACK_FLOATING_SHARE
    assert assumptions.base_rate == BASE_RATE_FALLBACK
    for name in ("fx_revenue_share", "commodity_cost_share", "floating_debt_share", "base_rate"):
        assert name in fallbacks


def test_buffer_and_revolver_cap_follow_the_frozen_multiples() -> None:
    periods = [period(i, opex=200.0) for i in range(12)]
    assumptions, _records, _fallbacks = derive_assumptions(dataset(periods))
    assert assumptions.min_cash_buffer == pytest.approx(OPEX_BUFFER_MULTIPLE * 200.0)
    assert assumptions.revolver_cap == pytest.approx(OPEX_REVOLVER_MULTIPLE * 200.0)
    assert assumptions.revolver_cap >= assumptions.min_cash_buffer


def test_revenue_capacity_is_the_trailing_maximum() -> None:
    periods = [period(i, revenue=100.0 + i) for i in range(12)]
    assumptions, _records, _fallbacks = derive_assumptions(dataset(periods))
    assert assumptions.revenue_capacity == pytest.approx(111.0)


def test_cogs_ratio_is_the_trailing_mean_ratio() -> None:
    periods = [period(i, revenue=1000.0, cogs=600.0) for i in range(12)]
    assumptions, _records, _fallbacks = derive_assumptions(dataset(periods))
    assert assumptions.cogs_ratio == pytest.approx(0.6)


def test_records_carry_the_frozen_parameter_tags() -> None:
    _assumptions, records, _fallbacks = derive_assumptions(dataset([period(i) for i in range(12)]))
    by_name = {r.parameter: r for r in records}
    assert by_name["pass_through"].tag is ParameterTag.ASSUMPTION
    assert by_name["min_cash_buffer"].tag is ParameterTag.ASSUMPTION
    assert by_name["cogs_ratio"].tag is ParameterTag.REAL
    assert by_name["revenue_capacity"].tag is ParameterTag.REAL
    assert by_name["cogs_ratio"].source


def test_short_history_is_refused_rather_than_shortened() -> None:
    with pytest.raises(InsufficientHistoryError):
        derive_assumptions(dataset([period(i) for i in range(11)]))


def test_missing_revenue_is_reported_and_never_imputed() -> None:
    periods = [period(i) for i in range(12)]
    periods[3] = period(3, revenue=None)
    with pytest.raises(ValueError, match="revenue"):
        derive_assumptions(dataset(periods))


def test_debt_schedule_is_spread_evenly_inside_its_bucket() -> None:
    periods = twelve(
        total_debt=1000.0,
        debt_schedule=[
            DebtScheduleEntry(bucket="0-3m", amount=300.0),
            DebtScheduleEntry(bucket="3-12m", amount=900.0),
        ],
    )
    assumptions, _records, _fallbacks = derive_assumptions(dataset(periods))
    # "0-3m" covers months 1-3 at 300/3 = 100/month; "3-12m" covers months 4-12
    # at 900/9 = 100/month. The buckets do not overlap.
    assert assumptions.principal_for_month(1) == pytest.approx(100.0)
    assert assumptions.principal_for_month(3) == pytest.approx(100.0)
    assert assumptions.principal_for_month(4) == pytest.approx(100.0)
    assert assumptions.principal_for_month(12) == pytest.approx(100.0)
    assert assumptions.principal_for_month(13) == pytest.approx(0.0)


def test_absent_debt_schedule_yields_no_amortization() -> None:
    assumptions, _records, _fallbacks = derive_assumptions(dataset([period(i) for i in range(12)]))
    assert assumptions.debt_amortization == []
    assert assumptions.principal_for_month(1) == 0.0


def test_growth_is_clamped_to_the_frozen_band() -> None:
    # 5% a month compounds far beyond the +15% annual cap, so the clamp bites.
    periods = [period(i, revenue=100.0 * (1.05**i)) for i in range(12)]
    assumptions, records, _fallbacks = derive_assumptions(dataset(periods))
    assert assumptions.growth_rate == pytest.approx(0.15)
    growth_record = next(r for r in records if r.parameter == "growth_rate")
    assert "clamped" in growth_record.source


def test_all_derived_values_are_finite() -> None:
    assumptions, _records, _fallbacks = derive_assumptions(dataset([period(i) for i in range(12)]))
    for name, value in assumptions.model_dump().items():
        if isinstance(value, float):
            assert math.isfinite(value), name


def test_pass_through_matches_the_shared_risk_engine_default() -> None:
    """simulation.md §1 says ptc is "shared with risk engine" (0.3).

    The value is re-declared here rather than imported, so the twin does not
    couple to a Phase 4 metric signature. This test is what stops the two
    constants from drifting apart.
    """
    from backend.risk_engine.metrics.market import calc_commodity_exposure_score

    default = inspect.signature(calc_commodity_exposure_score).parameters["pass_through"].default
    assert PASS_THROUGH == default


def test_revolver_cap_below_buffer_is_rejected() -> None:
    with pytest.raises(ValidationError, match="revolver_cap"):
        SimulationAssumptions(
            growth_rate=0.0,
            cogs_ratio=0.5,
            fixed_cost=0.0,
            variable_cost_ratio=0.0,
            da_monthly=0.0,
            dso=0.0,
            dio=0.0,
            dpo=0.0,
            capex_monthly=0.0,
            revenue_capacity=0.0,
            initial_debt=0.0,
            base_rate=0.0,
            floating_debt_share=0.0,
            min_cash_buffer=100.0,
            revolver_cap=10.0,
            tax_rate=0.25,
            fx_import_cost_share=0.0,
            fx_revenue_share=0.0,
            commodity_cost_share=0.0,
            pass_through=0.3,
            fx_demand_elasticity=0.5,
        )
