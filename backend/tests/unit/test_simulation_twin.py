"""Unit tests for the frozen §2 monthly recursion (Phase 6).

Each frozen equation in docs/01_architecture/simulation.md §2 is tested
individually, then the whole run is checked end to end. A hand-computed
two-month fixture pins the arithmetic independently of any generator, and the
financing block (buffer, revolver, funding gap) and the date grid get their own
coverage because that is where a silent error would be most plausible.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pytest

from backend.simulation.contracts import (
    MAX_HORIZON_MONTHS,
    SimulationAssumptions,
    SimulationInitialState,
    SimulationInput,
    SimulationMonth,
    SimulationOverrides,
    SimulationStatus,
)
from backend.simulation.twin import next_month_end, run_twin

# --- fixtures --------------------------------------------------------------


def assumptions(**overrides: Any) -> SimulationAssumptions:
    """Fully specified, deliberately round assumptions for hand arithmetic."""
    base: dict[str, Any] = {
        "growth_rate": 0.0,
        "cogs_ratio": 0.50,
        "fixed_cost": 0.0,
        "variable_cost_ratio": 0.10,
        "da_monthly": 0.0,
        "dso": 0.0,
        "dio": 0.0,
        "dpo": 0.0,
        "capex_monthly": 0.0,
        "revenue_capacity": 1_000_000.0,
        "initial_debt": 0.0,
        "base_rate": 0.12,
        "floating_debt_share": 1.0,
        "min_cash_buffer": 0.0,
        "revolver_cap": 0.0,
        "tax_rate": 0.25,
        "fx_import_cost_share": 0.0,
        "fx_revenue_share": 0.0,
        "commodity_cost_share": 0.0,
        "pass_through": 0.3,
        "fx_demand_elasticity": 0.5,
    }
    base.update(overrides)
    return SimulationAssumptions(**base)


def initial_state(**overrides: Any) -> SimulationInitialState:
    base: dict[str, Any] = {
        "period_end": date(2024, 12, 31),
        "revenue": 1000.0,
        "cash": 5000.0,
        "debt": 0.0,
        "nwc": 0.0,
        "history_periods": 12,
    }
    base.update(overrides)
    return SimulationInitialState(**base)


def make_input(
    horizon: int = 1,
    a: dict[str, Any] | None = None,
    o: SimulationOverrides | None = None,
    state: SimulationInitialState | None = None,
) -> SimulationInput:
    """Build a run.

    ``a`` overrides frozen §1 assumptions; ``o`` supplies already-structured
    §2 scenario deltas. Keeping them apart matters: they are different frozen
    concepts, and the contracts enforce ``extra="forbid"`` precisely so a
    scenario delta cannot be mistaken for an assumption.
    """
    return SimulationInput(
        horizon_months=horizon,
        assumptions=assumptions(**(a or {})),
        initial_state=state or initial_state(),
        overrides=o or SimulationOverrides(),
    )


def one_month(
    a: dict[str, Any] | None = None, o: SimulationOverrides | None = None
) -> SimulationMonth:
    return run_twin(make_input(1, a=a, o=o)).months[0]


# --- date grid -------------------------------------------------------------


def test_month_end_advances_across_the_grid() -> None:
    assert next_month_end(date(2024, 12, 31)) == date(2025, 1, 31)
    assert next_month_end(date(2025, 1, 31)) == date(2025, 2, 28)
    assert next_month_end(date(2024, 2, 29)) == date(2024, 3, 31)  # leap year
    assert next_month_end(date(2023, 2, 28)) == date(2023, 3, 31)  # non-leap


def test_mid_month_start_resolves_onto_the_grid() -> None:
    assert next_month_end(date(2024, 12, 15)) == date(2024, 12, 31)


def test_simulated_periods_advance_one_month_each() -> None:
    result = run_twin(make_input(3))
    assert [m.period_end for m in result.months] == [
        date(2025, 1, 31),
        date(2025, 2, 28),
        date(2025, 3, 31),
    ]
    assert [m.period_index for m in result.months] == [1, 2, 3]


# --- hand-computed month ---------------------------------------------------


def test_month_one_matches_hand_calculation() -> None:
    """Every frozen §2 line computed by hand, then compared to the engine.

    Opening: Rev=1000, cash=5000, debt=0, NWC=0. g=0 so the monthly growth
    factor is 1; c0=0.5, v=0.1, tau=0.25, DA=0, no debt.
      Rev_dem = 1000 * 1 * 1                 = 1000
      Rev_sup = 1_000_000 * 1                = 1_000_000
      Rev_t   = min(1000, 1_000_000)         = 1000
      COGS_t  = 1000 * 0.5                   = 500
      GP_t    = 1000 - 500                   = 500
      Opex_t  = 0 + 0.1 * 1000               = 100
      EBITDA  = 500 - 100                    = 400 ; EBIT = 400
      Interest= 0.12/12 * 0                  = 0
      EBT     = 400 ; Tax = 400 * 0.25 = 100 ; NI = 300
      AR/Inv/AP = 0 (all day counts 0)       ->  NWC = 0 ; dNWC = 0
      OCF     = 300 + 0 - 0                  = 300
      Capex/principal/one_off = 0
      Cash    = 5000 + 300                   = 5300
    """
    month = one_month()
    assert month.revenue == pytest.approx(1000.0)
    assert month.cogs == pytest.approx(500.0)
    assert month.gross_profit == pytest.approx(500.0)
    assert month.opex == pytest.approx(100.0)
    assert month.ebitda == pytest.approx(400.0)
    assert month.ebit == pytest.approx(400.0)
    assert month.interest_expense == pytest.approx(0.0)
    assert month.ebt == pytest.approx(400.0)
    assert month.tax == pytest.approx(100.0)
    assert month.net_income == pytest.approx(300.0)
    assert month.nwc == pytest.approx(0.0)
    assert month.delta_nwc == pytest.approx(0.0)
    assert month.ocf == pytest.approx(300.0)
    assert month.cash == pytest.approx(5300.0)
    assert month.total_debt == pytest.approx(0.0)


def test_month_two_continues_from_month_one() -> None:
    """Month 2 opens on month 1's balances; with g=0 revenue stays flat."""
    result = run_twin(make_input(2))
    first, second = result.months
    assert second.revenue == pytest.approx(first.revenue)
    assert second.cash == pytest.approx(first.cash + 300.0)


def test_growth_compounds_monthly_from_the_annual_rate() -> None:
    month = one_month(a={"growth_rate": 0.12})
    assert month.revenue == pytest.approx(1000.0 * (1.12 ** (1.0 / 12.0)), rel=1e-12)


# --- individual equations --------------------------------------------------


def test_gross_profit_is_revenue_minus_cogs() -> None:
    month = one_month()
    assert month.gross_profit == pytest.approx(month.revenue - month.cogs)


def test_ebitda_is_gp_minus_opex_and_ebit_subtracts_da() -> None:
    month = one_month(a={"da_monthly": 25.0})
    assert month.ebitda == pytest.approx(month.gross_profit - month.opex)
    assert month.ebit == pytest.approx(month.ebitda - 25.0)


def test_tax_applies_only_to_positive_ebt() -> None:
    # A huge D&A drives EBT negative; tax must be exactly zero, never negative.
    month = one_month(a={"da_monthly": 1000.0})
    assert month.ebt < 0.0
    assert month.tax == 0.0
    assert month.net_income == pytest.approx(month.ebt)


def test_interest_splits_floating_and_fixed_legs() -> None:
    """r0 applies to both legs; the opening balance is what gets charged."""
    month = one_month(a={"initial_debt": 1200.0, "base_rate": 0.12, "floating_debt_share": 0.5})
    # (0.12/12)*(1200*0.5) + (0.12/12)*(1200*0.5) = 6 + 6 = 12
    assert month.interest_expense == pytest.approx(12.0)
    assert month.ebt == pytest.approx(400.0 - 12.0)


def test_rate_change_moves_only_the_floating_leg() -> None:
    month = one_month(
        a={"initial_debt": 1200.0, "base_rate": 0.12, "floating_debt_share": 0.5},
        o=SimulationOverrides(rate_change=0.02),
    )
    # (0.14/12)*600 + (0.12/12)*600 = 7 + 6 = 13
    assert month.interest_expense == pytest.approx(13.0)


def test_zero_debt_gives_zero_interest() -> None:
    assert one_month(a={"initial_debt": 0.0}).interest_expense == 0.0


def test_working_capital_follows_dso_dio_dpo() -> None:
    month = one_month(a={"dso": 30.0, "dio": 30.0, "dpo": 15.0})
    assert month.receivables == pytest.approx(1000.0)  # 1000 * 30/30
    assert month.inventory == pytest.approx(500.0)  # 500 * 30/30
    assert month.payables == pytest.approx(250.0)  # 500 * 15/30
    assert month.nwc == pytest.approx(1000.0 + 500.0 - 250.0)


def test_delta_nwc_is_the_period_over_period_change() -> None:
    result = run_twin(make_input(3, a={"dso": 30.0}))
    for index, month in enumerate(result.months):
        previous = 0.0 if index == 0 else result.months[index - 1].nwc
        assert month.delta_nwc == pytest.approx(month.nwc - previous)


def test_ocf_is_ni_plus_da_minus_delta_nwc() -> None:
    month = one_month(a={"dso": 30.0, "da_monthly": 50.0})
    assert month.ocf == pytest.approx(month.net_income + month.da - month.delta_nwc)


# --- supply and demand channels -------------------------------------------


def test_supplier_disruption_caps_revenue_at_capacity() -> None:
    """Rev_t = min(Rev_dem, Capacity0 * (1 - d_supplier))."""
    month = one_month(a={"revenue_capacity": 800.0}, o=SimulationOverrides(supplier_disruption=0.5))
    assert month.revenue_capacity == pytest.approx(400.0)
    assert month.revenue == pytest.approx(400.0)
    assert month.revenue_capped is True


def test_revenue_is_uncapped_when_demand_is_below_capacity() -> None:
    month = one_month(a={"revenue_capacity": 1_000_000.0})
    assert month.revenue == pytest.approx(1000.0)
    assert month.revenue_capped is False


def test_revenue_decline_scales_revenue_and_its_cogs_together() -> None:
    month = one_month(o=SimulationOverrides(revenue_change=-0.20))
    assert month.revenue == pytest.approx(800.0)
    assert month.cogs == pytest.approx(400.0)  # c0 is a ratio of new revenue


def test_fx_depreciation_cuts_demand_and_raises_costs() -> None:
    """d_fx lowers demand via rho_rev*e_fx and raises COGS via kappa_fx*(1-ptc)."""
    month = one_month(
        a={"fx_revenue_share": 0.5, "fx_import_cost_share": 0.5},
        o=SimulationOverrides(fx_change=0.10),
    )
    # Demand: 1000 * (1 - 0.1*0.5*0.5) = 1000 * 0.975 = 975
    assert month.revenue_demand == pytest.approx(975.0)
    assert month.revenue == pytest.approx(975.0)
    # COGS: 975 * 0.5 * (1 + 0.1*0.5*0.7) = 487.5 * 1.035
    assert month.cogs == pytest.approx(975.0 * 0.5 * (1.0 + 0.10 * 0.5 * 0.7))


def test_commodity_shock_is_damped_by_the_pass_through() -> None:
    month = one_month(a={"commodity_cost_share": 0.5}, o=SimulationOverrides(commodity_change=1.0))
    # COGS = 1000 * 0.5 * (1 + 1.0*0.5*0.7) = 500 * 1.35 = 675
    assert month.cogs == pytest.approx(675.0)


def test_cogs_inflation_applies_after_the_commodity_leg() -> None:
    plain = one_month().cogs
    inflated = one_month(o=SimulationOverrides(cogs_change=0.10)).cogs
    assert inflated == pytest.approx(plain * 1.10)


def test_opex_inflation_scales_fixed_and_variable_together() -> None:
    month = one_month(a={"fixed_cost": 50.0}, o=SimulationOverrides(opex_change=0.10))
    assert month.opex == pytest.approx((50.0 + 0.10 * 1000.0) * 1.10)


def test_ar_days_change_shifts_receivables() -> None:
    month = one_month(a={"dso": 30.0}, o=SimulationOverrides(ar_days_change=15.0))
    assert month.receivables == pytest.approx(1000.0 * 45.0 / 30.0)


# --- ramp ------------------------------------------------------------------
#
# Note on compounding: the frozen equation is
# ``Rev_dem_t = Rev_{t-1} * (1+g) * (1+d_rev,t)``, so a persistent delta is
# applied to the *previous* month's revenue and therefore compounds every
# month. A "step" in simulation.md §2 means the delta is fully applied from
# t = 1, not that revenue stays frozen.


def test_zero_ramp_applies_the_full_delta_from_month_one() -> None:
    result = run_twin(make_input(2, o=SimulationOverrides(revenue_change=-0.20)))
    assert result.months[0].revenue == pytest.approx(800.0)
    # The step persists: 800 * 0.8 in month 2.
    assert result.months[1].revenue == pytest.approx(640.0)


def test_ramp_reaches_full_effect_only_at_the_ramp_length() -> None:
    overrides = SimulationOverrides(revenue_change=-0.20, ramp_months=4)
    result = run_twin(make_input(4, o=overrides))
    # Weight at t is t/R, so the monthly shock is 5%, 10%, 15%, 20% and each
    # one compounds onto the revenue the previous month produced.
    assert result.months[0].revenue == pytest.approx(1000.0 * 0.95)
    assert result.months[1].revenue == pytest.approx(1000.0 * 0.95 * 0.90)
    assert result.months[2].revenue == pytest.approx(1000.0 * 0.95 * 0.90 * 0.85)
    assert result.months[3].revenue == pytest.approx(1000.0 * 0.95 * 0.90 * 0.85 * 0.80)


def test_a_zero_delta_leaves_revenue_flat() -> None:
    result = run_twin(make_input(4))
    assert all(m.revenue == pytest.approx(1000.0) for m in result.months)


# --- financing, buffer and funding gap -------------------------------------


def test_one_off_cost_is_charged_once_in_month_one() -> None:
    result = run_twin(make_input(3, o=SimulationOverrides(one_off_cost=250.0)))
    assert result.months[0].one_off_cost == pytest.approx(250.0)
    assert result.months[1].one_off_cost == 0.0
    assert result.months[2].one_off_cost == 0.0


def test_capex_reduces_cash_and_is_scaled_by_its_delta() -> None:
    month = one_month(a={"capex_monthly": 100.0})
    assert month.capex == pytest.approx(100.0)
    assert month.cash == pytest.approx(5000.0 + 300.0 - 100.0)
    scaled = one_month(a={"capex_monthly": 100.0}, o=SimulationOverrides(capex_change=0.5))
    assert scaled.capex == pytest.approx(150.0)


def test_no_draw_when_cash_sits_above_the_buffer() -> None:
    month = one_month(a={"min_cash_buffer": 600.0, "revolver_cap": 2000.0})
    # Cash before draws is 5300, far above the 600 buffer.
    assert month.draws == 0.0
    assert month.cash == pytest.approx(5300.0)


def test_a_real_shortfall_draws_up_to_the_buffer() -> None:
    # A one-off cost in month 1 pushes cash below the buffer without breaching
    # the revolver, which is the ordinary "draw to restore liquidity" case.
    month = one_month(
        a={"min_cash_buffer": 6000.0, "revolver_cap": 10000.0},
        o=SimulationOverrides(one_off_cost=2000.0),
    )
    # Cash before draws = 5300 - 2000 = 3300, so the shortfall is 2700.
    assert month.draws == pytest.approx(2700.0)
    assert month.cash == pytest.approx(6000.0)
    assert month.funding_gap is False


def test_draws_are_capped_at_the_revolver_and_flag_a_funding_gap() -> None:
    month = one_month(
        a={"min_cash_buffer": 6000.0, "revolver_cap": 10000.0},
        o=SimulationOverrides(one_off_cost=20000.0),
    )
    # Cash before draws = 5300 - 20000 = -14700, so the shortfall is 20700,
    # which exceeds RC = 10000: only 10000 is drawn and the rest is a gap.
    assert month.draws == pytest.approx(10000.0)
    assert month.funding_gap is True
    assert month.status is SimulationStatus.FUNDING_GAP


def test_cash_may_go_negative_only_through_a_funding_gap() -> None:
    result = run_twin(
        make_input(
            3,
            a={"min_cash_buffer": 6000.0, "revolver_cap": 10000.0},
            o=SimulationOverrides(one_off_cost=20000.0),
        )
    )
    for month in result.months:
        if month.cash < 0.0:
            assert month.funding_gap is True
    assert result.summary.had_funding_gap is True
    assert result.summary.funding_gap_months


def test_a_funding_gap_run_still_holds_every_invariant() -> None:
    result = run_twin(
        make_input(
            6,
            a={"min_cash_buffer": 6000.0, "revolver_cap": 10000.0, "initial_debt": 2000.0},
            o=SimulationOverrides(one_off_cost=20000.0),
        )
    )
    assert result.invariants_hold is True
    # The frozen rule: cash may go negative ONLY through a funding gap.
    assert all(m.cash >= 0.0 or m.funding_gap for m in result.months)


def test_healthy_run_reports_no_breach_conditions() -> None:
    result = run_twin(make_input(6))
    assert result.summary.had_funding_gap is False
    assert result.summary.funding_gap_months == []
    assert result.summary.breached_buffer is False
    assert all(m.status is SimulationStatus.OK for m in result.months)


def test_principal_reduces_debt_and_cash() -> None:
    from backend.simulation.contracts import DebtAmortization

    base = assumptions(
        initial_debt=1000.0,
        debt_amortization=[
            DebtAmortization(bucket="0-3m", months=3, amount=300.0, monthly_principal=100.0)
        ],
    )
    result = run_twin(
        SimulationInput(
            horizon_months=2,
            assumptions=base,
            initial_state=initial_state(),
            overrides=SimulationOverrides(),
        )
    )
    assert result.months[0].principal == pytest.approx(100.0)
    assert result.months[0].total_debt == pytest.approx(900.0)
    assert result.months[1].total_debt == pytest.approx(800.0)
    assert result.summary.total_principal == pytest.approx(200.0)


def test_principal_never_drives_debt_below_zero() -> None:
    """A schedule over-stating the debt is capped, not allowed to go negative."""
    from backend.simulation.contracts import DebtAmortization

    base = assumptions(
        initial_debt=100.0,
        debt_amortization=[
            DebtAmortization(bucket="0-3m", months=3, amount=900.0, monthly_principal=300.0)
        ],
    )
    result = run_twin(
        SimulationInput(
            horizon_months=3,
            assumptions=base,
            initial_state=initial_state(),
            overrides=SimulationOverrides(),
        )
    )
    assert all(m.total_debt >= 0.0 for m in result.months)
    assert result.months[0].total_debt == pytest.approx(0.0)


def test_draws_increase_debt() -> None:
    month = one_month(
        a={"min_cash_buffer": 6000.0, "revolver_cap": 10000.0, "initial_debt": 500.0},
        o=SimulationOverrides(one_off_cost=2000.0),
    )
    # Interest 0.12/12*500 = 5, so EBT 395, tax 98.75, NI 296.25, OCF 296.25.
    # Cash before draws = 5000 + 296.25 - 2000 = 3296.25 -> shortfall 2703.75.
    assert month.draws == pytest.approx(2703.75)
    assert month.total_debt == pytest.approx(500.0 + 2703.75)


# --- ratios, horizon, determinism -----------------------------------------


def test_ratios_come_from_the_phase_four_calculators() -> None:
    month = one_month(a={"initial_debt": 1200.0})
    # EBITDA 400, interest 12 -> coverage = 400/12
    assert month.interest_coverage.value == pytest.approx(400.0 / 12.0)
    assert month.dscr.is_available
    assert month.cash_runway_months.is_available


def test_dscr_and_runway_are_reported_for_every_month() -> None:
    result = run_twin(make_input(6, a={"initial_debt": 1200.0}))
    for month in result.months:
        assert month.dscr.status is not None
        assert month.cash_runway_months.status is not None


def test_horizon_of_one_and_thirty_six_are_accepted() -> None:
    assert run_twin(make_input(1)).horizon_months == 1
    assert run_twin(make_input(MAX_HORIZON_MONTHS)).horizon_months == MAX_HORIZON_MONTHS


def test_horizon_beyond_the_frozen_maximum_is_rejected() -> None:
    with pytest.raises(ValueError, match="horizon_months"):
        SimulationInput(
            horizon_months=MAX_HORIZON_MONTHS + 1,
            assumptions=assumptions(),
            initial_state=initial_state(),
        )


def test_zero_horizon_is_rejected() -> None:
    with pytest.raises(ValueError):
        SimulationInput(horizon_months=0, assumptions=assumptions(), initial_state=initial_state())


def test_identical_inputs_produce_identical_outputs() -> None:
    first = run_twin(make_input(12, a={"growth_rate": 0.05, "initial_debt": 900.0}))
    second = run_twin(make_input(12, a={"growth_rate": 0.05, "initial_debt": 900.0}))
    assert first.model_dump() == second.model_dump()


def test_all_frozen_invariants_hold_on_a_baseline_run() -> None:
    result = run_twin(make_input(24, a={"growth_rate": 0.05, "initial_debt": 5000.0, "dso": 45.0}))
    assert {inv.name for inv in result.invariants} == {
        "cash_identity",
        "debt_roll_forward",
        "nwc_continuity",
        "tax_non_negative",
        "negative_cash_only_via_funding_gap",
        "horizon_bounded",
    }
    assert result.invariants_hold is True


def test_cash_identity_residual_is_within_tolerance() -> None:
    result = run_twin(make_input(24, a={"growth_rate": 0.05, "initial_debt": 5000.0, "dso": 45.0}))
    cash = next(i for i in result.invariants if i.name == "cash_identity")
    assert cash.residual <= cash.tolerance


def test_no_month_contains_a_nonfinite_value() -> None:
    result = run_twin(make_input(24, a={"growth_rate": 0.10, "initial_debt": 5000.0, "dso": 45.0}))
    for month in result.months:
        for name, value in month.model_dump().items():
            if isinstance(value, float):
                assert math.isfinite(value), name


def test_summary_reports_trough_and_end_horizon() -> None:
    result = run_twin(make_input(12))
    assert result.summary.final_cash == pytest.approx(result.months[-1].cash)
    assert result.summary.min_cash == pytest.approx(min(m.cash for m in result.months))
    assert result.summary.min_cash_period in [m.period_index for m in result.months]
    assert result.summary.lowest_ebitda == pytest.approx(min(m.ebitda for m in result.months))


def test_run_result_carries_the_frozen_disclaimers_and_version() -> None:
    result = run_twin(make_input(1))
    assert "causal" in result.causality_note.lower()
    assert "advice" in result.advice_note.lower()
    assert result.provenance.twin_version


def test_trajectory_helper_returns_a_series() -> None:
    assert len(run_twin(make_input(6)).trajectory("cash")) == 6


# --- end to end on the canonical generator --------------------------------


def canonical(seed: int = 1001, periods: int = 24) -> Any:
    from backend.data_engine.contracts import SyntheticCompanyConfig
    from backend.data_engine.ingest.synthetic import generate_company

    return generate_company(SyntheticCompanyConfig(seed=seed, periods=periods))


def test_simulate_end_to_end_on_a_canonical_fixture() -> None:
    from backend.simulation.twin import simulate

    result = simulate(canonical(), horizon_months=12)
    assert result.horizon_months == 12
    assert result.invariants_hold is True
    assert result.provenance.is_baseline is True
    assert result.provenance.generator_seeds == [1001]
    assert result.diagnostics.history_periods == 24
    assert result.diagnostics.assumption_records


def test_simulate_ends_after_the_last_observed_period() -> None:
    from backend.simulation.twin import simulate

    dataset = canonical()
    result = simulate(dataset, horizon_months=12)
    assert result.start_period_end == dataset.periods[-1].period_end
    assert result.end_period_end > result.start_period_end


def test_a_harsh_scenario_degrades_the_projected_business() -> None:
    """Phase 6 applies structured deltas; it does not judge or rank them."""
    from backend.simulation.twin import simulate

    dataset = canonical(seed=1002)
    baseline = simulate(dataset, horizon_months=12)
    stressed = simulate(
        dataset,
        horizon_months=12,
        overrides=SimulationOverrides(revenue_change=-0.30, rate_change=0.02),
    )
    assert min(m.revenue for m in stressed.months) < min(m.revenue for m in baseline.months)
    assert min(m.ebitda for m in stressed.months) < min(m.ebitda for m in baseline.months)
    # Coverage ratios are float | None: a debt-free run legitimately reports None.
    baseline_dscr = baseline.summary.min_dscr
    baseline_coverage = baseline.summary.min_interest_coverage
    stressed_dscr = stressed.summary.min_dscr
    stressed_coverage = stressed.summary.min_interest_coverage
    assert baseline_dscr is not None
    assert baseline_coverage is not None
    assert stressed_dscr is not None
    assert stressed_coverage is not None
    assert stressed_dscr < baseline_dscr
    assert stressed_coverage < baseline_coverage
    assert stressed.provenance.is_baseline is False


def test_a_shrinking_business_releases_working_capital() -> None:
    """A falling revenue shock can leave OCF positive while net income is negative.

    ``OCF_t = NI_t + DA - dNWC_t`` (simulation.md §2): when the business
    contracts, receivables and inventory are collected and run off faster than
    profit falls, so ``dNWC`` is strongly negative and the cash flow statement
    improves even as the income statement deteriorates. This is a real property
    of the frozen model, not a defect, and it is why the engine reports OCF and
    net income as separate series. It is also why simulation.md §6.3's "trough
    cash moves monotonically" does not hold in general — see the Phase 6 phase
    report (deferred item D-6-3).
    """
    from backend.simulation.twin import simulate

    stressed = simulate(
        canonical(seed=1002),
        horizon_months=12,
        overrides=SimulationOverrides(revenue_change=-0.30),
    )
    losing_months = [m for m in stressed.months if m.net_income < 0.0]
    assert losing_months, "expected the shock to turn net income negative"
    assert all(m.delta_nwc < 0.0 for m in losing_months)
    assert any(m.ocf > 0.0 for m in losing_months)


def test_simulate_is_reproducible_for_every_canonical_seed() -> None:
    from backend.simulation.twin import simulate

    for seed in (1001, 1002, 1003, 1004, 1005):
        dataset = canonical(seed)
        assert simulate(dataset, 12).model_dump() == simulate(dataset, 12).model_dump()
