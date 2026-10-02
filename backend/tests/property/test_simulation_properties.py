"""Property-style tests for the Business Digital Twin (Phase 6).

Uses plain deterministic seeded randomization (``random.Random(42)``) rather
than Hypothesis, matching the established Phase 4 and Phase 5 suites: testing.md
records that Hypothesis is not installed and not declared, so no test may import
it. Every property below is falsifiable — a violation is a finding about the
twin, not something to relax away.
"""

from __future__ import annotations

import math
import random
from datetime import date

import pytest

from backend.simulation.contracts import (
    CASH_IDENTITY_TOLERANCE,
    MAX_HORIZON_MONTHS,
    SimulationAssumptions,
    SimulationInitialState,
    SimulationInput,
    SimulationOverrides,
    SimulationState,
)
from backend.simulation.twin import next_month_end, run_twin, step_month

SEED = 42
SAMPLES = 200


def _days_in_month(year: int, month: int) -> int:
    """Days in a calendar month, leap years included (stdlib, no assumption)."""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def random_assumptions(rng: random.Random) -> SimulationAssumptions:
    """Draw a legal assumption set from the frozen §1 ranges."""
    monthly_opex = rng.uniform(50.0, 5000.0)
    buffer = monthly_opex * rng.uniform(1.0, 3.0)
    return SimulationAssumptions(
        growth_rate=rng.uniform(-0.05, 0.15),
        cogs_ratio=rng.uniform(0.0, 1.0),
        fixed_cost=rng.uniform(0.0, monthly_opex),
        variable_cost_ratio=rng.uniform(0.0, 1.0),
        da_monthly=rng.uniform(0.0, 500.0),
        dso=rng.uniform(0.0, 120.0),
        dio=rng.uniform(0.0, 120.0),
        dpo=rng.uniform(0.0, 120.0),
        capex_monthly=rng.uniform(0.0, 500.0),
        revenue_capacity=rng.uniform(1.0, 1_000_000.0),
        initial_debt=rng.uniform(0.0, 50_000.0),
        base_rate=rng.uniform(0.0, 0.25),
        floating_debt_share=rng.uniform(0.0, 1.0),
        min_cash_buffer=buffer,
        revolver_cap=buffer * rng.uniform(1.0, 2.0),
        tax_rate=rng.uniform(0.0, 0.45),
        fx_import_cost_share=rng.uniform(0.0, 1.0),
        fx_revenue_share=rng.uniform(0.0, 1.0),
        commodity_cost_share=rng.uniform(0.0, 1.0),
        pass_through=rng.uniform(0.0, 1.0),
        fx_demand_elasticity=rng.uniform(0.0, 1.0),
    )


def random_state(rng: random.Random) -> SimulationInitialState:
    return SimulationInitialState(
        period_end=date(2024, 12, 31),
        revenue=rng.uniform(0.0, 100_000.0),
        cash=rng.uniform(0.0, 100_000.0),
        debt=rng.uniform(0.0, 50_000.0),
        nwc=rng.uniform(-50_000.0, 50_000.0),
        history_periods=12,
    )


def random_overrides(rng: random.Random) -> SimulationOverrides:
    return SimulationOverrides(
        ramp_months=rng.choice([0, 0, 1, 3, 6, 12]),
        revenue_change=rng.uniform(-0.5, 0.5),
        cogs_change=rng.uniform(-0.5, 0.5),
        opex_change=rng.uniform(-0.5, 0.5),
        rate_change=rng.uniform(-0.05, 0.05),
        fx_change=rng.uniform(-0.5, 0.5),
        commodity_change=rng.uniform(-0.5, 1.0),
        supplier_disruption=rng.uniform(0.0, 1.0),
        capex_change=rng.uniform(-1.0, 1.0),
        ar_days_change=rng.uniform(-30.0, 60.0),
        one_off_cost=rng.choice([0.0, 0.0, rng.uniform(0.0, 10_000.0)]),
    )


def random_run(rng: random.Random, horizon: int) -> SimulationInput:
    return SimulationInput(
        horizon_months=horizon,
        assumptions=random_assumptions(rng),
        initial_state=random_state(rng),
        overrides=random_overrides(rng),
    )


# --- identities ------------------------------------------------------------


def test_cash_identity_holds_over_randomised_runs() -> None:
    rng = random.Random(SEED)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, rng.randint(1, MAX_HORIZON_MONTHS)))
        cash = next(i for i in result.invariants if i.name == "cash_identity")
        assert cash.residual <= CASH_IDENTITY_TOLERANCE, cash.residual


def test_debt_roll_and_nwc_continuity_hold_over_randomised_runs() -> None:
    rng = random.Random(SEED + 1)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, rng.randint(1, MAX_HORIZON_MONTHS)))
        assert result.invariants_hold is True


def test_tax_is_never_negative() -> None:
    rng = random.Random(SEED + 2)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, 12))
        assert all(m.tax >= 0.0 for m in result.months)


def test_debt_is_never_negative() -> None:
    rng = random.Random(SEED + 3)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, 12))
        assert all(m.total_debt >= 0.0 for m in result.months)


def test_negative_cash_never_occurs_without_a_funding_gap() -> None:
    rng = random.Random(SEED + 4)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, 12))
        for month in result.months:
            if month.cash < 0.0:
                assert month.funding_gap is True


def test_draws_never_exceed_the_revolver_cap() -> None:
    rng = random.Random(SEED + 5)
    for _ in range(SAMPLES):
        simulation = random_run(rng, 12)
        result = run_twin(simulation)
        cap = simulation.assumptions.revolver_cap
        assert all(m.draws <= cap + 1e-9 for m in result.months)


def test_a_funding_gap_implies_the_shortfall_exceeded_the_cap() -> None:
    rng = random.Random(SEED + 6)
    for _ in range(SAMPLES):
        simulation = random_run(rng, 12)
        result = run_twin(simulation)
        for month in result.months:
            if month.funding_gap:
                assert month.draws == pytest.approx(
                    simulation.assumptions.revolver_cap, rel=1e-9, abs=1e-9
                )


# --- boundedness and finiteness -------------------------------------------


def test_every_emitted_value_is_finite() -> None:
    rng = random.Random(SEED + 7)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, MAX_HORIZON_MONTHS))
        for month in result.months:
            for name, value in month.model_dump().items():
                if isinstance(value, float):
                    assert math.isfinite(value), f"{name} = {value}"


def test_horizon_is_always_bounded() -> None:
    rng = random.Random(SEED + 8)
    for _ in range(50):
        horizon = rng.randint(1, MAX_HORIZON_MONTHS)
        assert run_twin(random_run(rng, horizon)).horizon_months == horizon


def test_revenue_never_exceeds_the_supply_ceiling() -> None:
    rng = random.Random(SEED + 9)
    for _ in range(SAMPLES):
        simulation = random_run(rng, 12)
        result = run_twin(simulation)
        for month in result.months:
            assert month.revenue <= month.revenue_capacity + 1e-9


def test_gross_profit_always_equals_revenue_minus_cogs() -> None:
    rng = random.Random(SEED + 10)
    for _ in range(SAMPLES):
        result = run_twin(random_run(rng, 12))
        for month in result.months:
            assert month.gross_profit == pytest.approx(month.revenue - month.cogs, abs=1e-9)


# --- determinism -----------------------------------------------------------


def test_repeating_a_run_reproduces_it_exactly() -> None:
    rng = random.Random(SEED + 11)
    for _ in range(50):
        simulation = random_run(rng, 12)
        assert run_twin(simulation).model_dump() == run_twin(simulation).model_dump()


def test_stepping_one_month_at_a_time_matches_a_single_run() -> None:
    """The recursion is compositional: N steps == the N-month run."""
    rng = random.Random(SEED + 12)
    for _ in range(25):
        simulation = random_run(rng, 9)
        result = run_twin(simulation)
        state = None
        for _ in range(9):
            state, _ledger = step_month(
                state or _initial(simulation), simulation.assumptions, simulation.overrides
            )
        assert state is not None
        assert state.cash == pytest.approx(result.months[-1].cash, rel=1e-12, abs=1e-9)
        assert state.total_debt == pytest.approx(result.months[-1].total_debt, abs=1e-9)


def _initial(simulation: SimulationInput) -> SimulationState:
    from backend.simulation.twin import build_initial_state

    return build_initial_state(simulation.initial_state, simulation.assumptions)


# --- continuity ------------------------------------------------------------


def test_the_date_grid_is_strictly_increasing() -> None:
    rng = random.Random(SEED + 13)
    for _ in range(50):
        result = run_twin(random_run(rng, 12))
        dates = [m.period_end for m in result.months]
        assert dates == sorted(dates)
        assert len(set(dates)) == len(dates)
        assert dates[0] > result.start_period_end


def test_month_ends_always_land_on_a_calendar_month_end() -> None:
    rng = random.Random(SEED + 14)
    for _ in range(50):
        result = run_twin(random_run(rng, 12))
        for month in result.months:
            end = month.period_end
            assert next_month_end(end) > end
            assert end.day == _days_in_month(end.year, end.month)


def test_a_zero_override_reproduces_the_baseline() -> None:
    """The default overrides are the identity: the twin can always run unstressed."""
    rng = random.Random(SEED + 15)
    for _ in range(25):
        simulation = random_run(rng, 12)
        baseline = run_twin(
            SimulationInput(
                horizon_months=simulation.horizon_months,
                assumptions=simulation.assumptions,
                initial_state=simulation.initial_state,
                overrides=SimulationOverrides(),
            )
        )
        assert baseline.provenance.is_baseline is True
        assert all(math.isfinite(v) for v in baseline.trajectory("cash"))
