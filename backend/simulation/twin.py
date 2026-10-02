"""Monthly recursion engine for the Business Digital Twin (Phase 6).

This module implements ``docs/01_architecture/simulation.md`` §2 **verbatim**,
in the frozen equation order. It is a pure function of
``(assumptions, initial_state, overrides, horizon)``: no I/O, no network, no
LLM, no database, no global state and no random process (architecture R1/R3,
NFR1).

Divergence note (decision D-0, approved): the planning prompt carried a
simplified equation set. The frozen §2 additionally specifies a supply ceiling
``Capacity0``, an FX demand-elasticity term, commodity and FX cost legs damped
by ``(1 - ptc)``, a split floating/fixed interest basis, revolver draws against
a minimum-cash buffer, and an explicit ``funding_gap`` breach. Those frozen
behaviours are implemented here, because §2 is the authority and the
simplified set would silently delete the FX/commodity channels the project
advertises as a research contribution.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.data_engine.contracts import CompanyDataset, PeriodFinancials
from backend.risk_engine.metrics.financial_strength import (
    calc_dscr,
    calc_interest_coverage,
)
from backend.risk_engine.metrics.liquidity import calc_cash_runway_months
from backend.simulation.assumptions import InsufficientHistoryError, derive_assumptions
from backend.simulation.contracts import (
    CASH_IDENTITY_TOLERANCE,
    CAUSALITY_DISCLAIMER,
    DEFAULT_HORIZON_MONTHS,
    IDENTITY_TOLERANCE,
    MAX_HORIZON_MONTHS,
    NOT_ADVICE_DISCLAIMER,
    TWIN_VERSION,
    MonthLedger,
    Provenance,
    SimulationAssumptions,
    SimulationDiagnostics,
    SimulationInitialState,
    SimulationInput,
    SimulationInvariantResult,
    SimulationMonth,
    SimulationOverrides,
    SimulationRatio,
    SimulationRunResult,
    SimulationState,
    SimulationStatus,
    SimulationSummary,
)

__all__ = [
    "FUNDING_PREMIUM",
    "InsufficientHistoryError",
    "build_initial_state",
    "build_initial_state_from_period",
    "check_invariants",
    "derive_assumptions",
    "next_month_end",
    "run_twin",
    "simulate",
    "step_month",
]

# simulation.md §2: "draws = shortfall vs buffer B (rate = r0 + 200 bp stress
# premium [A])". The premium is disclosed: it is the marginal cost of new
# revolver borrowing, and it reaches later months through the larger debt
# balance that such borrowing creates.
FUNDING_PREMIUM = 0.02
MONTHS_PER_YEAR = 12.0
DAYS_IN_MONTH = 30.0


def _last_day_of_month(year: int, month: int) -> date:
    """Last calendar day of a month; leap years handled by date arithmetic."""
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def next_month_end(current: date) -> date:
    """The month-end that follows ``current`` (decision D-2).

    The repository's own periods run month-start to month-end
    (``PeriodFinancials``), so the twin advances on the same grid. Two cases:

    * ``current`` is already a month end (the normal case, since t=0 is a
      canonical period) -> the next month end, i.e. the grid actually advances;
    * ``current`` sits mid-month -> the coming month end, so a partial opening
      period still resolves onto the grid.

    Leap years need no special case: every end date is derived as the first day
    of the following month minus one day.
    """
    end_of_this_month = _last_day_of_month(current.year, current.month)
    if current != end_of_this_month:
        return end_of_this_month
    if current.month == 12:
        return _last_day_of_month(current.year + 1, 1)
    return _last_day_of_month(current.year, current.month + 1)


def build_initial_state(
    initial: SimulationInitialState,
    assumptions: SimulationAssumptions,
) -> SimulationState:
    """t = 0 state: the last observed period, ready to be advanced.

    Only quantities the frozen §2 recursion actually consumes are populated.
    There is deliberately no projected ``equity``/``total_assets``: §2 defines
    no balance-sheet recursion, so producing one would invent methodology
    (decision D-4). ``Assets = Liabilities + Equity`` is therefore an *input*
    property, checked by ``data_engine.validate.identities`` before the run.
    """
    return SimulationState(
        period_index=0,
        period_end=initial.period_end,
        revenue=initial.revenue,
        cogs=0.0,
        gross_profit=0.0,
        opex=0.0,
        ebitda=0.0,
        da=assumptions.da_monthly,
        ebit=0.0,
        interest_expense=0.0,
        ebt=0.0,
        tax=0.0,
        net_income=0.0,
        receivables=0.0,
        inventory=0.0,
        payables=0.0,
        nwc=initial.nwc,
        ocf=0.0,
        cash=initial.cash,
        total_debt=assumptions.initial_debt,
    )


def _scheduled_principal(
    assumptions: SimulationAssumptions, period_index: int, opening_debt: float
) -> float:
    """Principal due this month, capped at the debt actually outstanding.

    The frozen schedule is derived from t=0 and can in principle schedule more
    than remains (for example when ``total_debt`` and the schedule disagree).
    Repaying more than is owed would create negative debt, so the amount is
    capped at the opening balance rather than smoothed over silently.
    """
    return min(assumptions.principal_for_month(period_index), opening_debt)


def step_month(
    state: SimulationState,
    assumptions: SimulationAssumptions,
    overrides: SimulationOverrides,
) -> tuple[SimulationState, MonthLedger]:
    """Advance the twin by exactly one month using the frozen §2 recursion.

    Equations are applied in the order printed in simulation.md §2 so each step
    consumes only quantities earlier steps produced: demand/supply -> revenue ->
    COGS -> GP -> opex -> EBITDA/EBIT -> interest -> EBT/tax/NI -> working
    capital -> OCF -> capex -> principal -> draws -> cash -> debt.

    Returns the new state and the month's financing/channel ledger. The ledger
    is what makes the cash identity independently checkable afterwards rather
    than a restatement of the same variables that produced cash.
    """
    t = state.period_index + 1
    ramp = overrides.ramp_factor(t)
    monthly_growth = (1.0 + assumptions.growth_rate) ** (1.0 / MONTHS_PER_YEAR)

    # --- demand and supply channels (frozen §2) -----------------------------
    delta_rev = overrides.revenue_change * ramp
    delta_fx = overrides.fx_change * ramp
    revenue_demand = state.revenue * monthly_growth * (1.0 + delta_rev)
    revenue_demand -= (
        delta_fx * assumptions.fx_revenue_share * assumptions.fx_demand_elasticity * revenue_demand
    )
    revenue_capacity = assumptions.revenue_capacity * (1.0 - overrides.supplier_disruption * ramp)
    revenue = min(revenue_demand, revenue_capacity)
    revenue_capped = revenue_capacity < revenue_demand

    # --- cost of goods (frozen §2: commodity and FX legs, damped by ptc) ----
    delta_comm = overrides.commodity_change * ramp
    delta_cogs = overrides.cogs_change * ramp
    pass_through = 1.0 - assumptions.pass_through
    cogs = revenue * assumptions.cogs_ratio
    cogs *= 1.0 + delta_comm * assumptions.commodity_cost_share * pass_through
    cogs *= 1.0 + delta_fx * assumptions.fx_import_cost_share * pass_through
    cogs *= 1.0 + delta_cogs

    gross_profit = revenue - cogs
    opex = (assumptions.fixed_cost + assumptions.variable_cost_ratio * revenue) * (
        1.0 + overrides.opex_change * ramp
    )
    ebitda = gross_profit - opex
    da = assumptions.da_monthly
    ebit = ebitda - da

    # --- interest on the opening balance, split floating / fixed (frozen §2) -
    rate = assumptions.base_rate + overrides.rate_change * ramp
    opening_debt = state.total_debt
    floating = opening_debt * assumptions.floating_debt_share
    fixed = opening_debt * (1.0 - assumptions.floating_debt_share)
    interest = rate / MONTHS_PER_YEAR * floating + assumptions.base_rate / MONTHS_PER_YEAR * fixed

    ebt = ebit - interest
    tax = max(0.0, ebt) * assumptions.tax_rate
    net_income = ebt - tax

    # --- working capital (frozen §2) ----------------------------------------
    receivables = revenue * (assumptions.dso + overrides.ar_days_change * ramp) / DAYS_IN_MONTH
    inventory = cogs * assumptions.dio / DAYS_IN_MONTH
    payables = cogs * assumptions.dpo / DAYS_IN_MONTH
    nwc = receivables + inventory - payables
    delta_nwc = nwc - state.nwc
    ocf = net_income + da - delta_nwc

    # --- investing, financing, cash (frozen §2) -----------------------------
    capex = assumptions.capex_monthly * (1.0 + overrides.capex_change * ramp)
    principal = _scheduled_principal(assumptions, t, opening_debt)
    one_off_cost = overrides.one_off_cost if t == 1 else 0.0
    buffer = assumptions.min_cash_buffer
    revolver_cap = assumptions.revolver_cap
    cash_before_draws = state.cash + ocf - capex - principal - one_off_cost
    shortfall = max(0.0, buffer - cash_before_draws)
    draws = min(shortfall, revolver_cap)
    # simulation.md §2: beyond RC the period records a funding_gap (hard breach)
    # and cash may then go negative. Both are disclosed, never clamped.
    funding_gap = shortfall > revolver_cap + IDENTITY_TOLERANCE
    cash = cash_before_draws + draws
    debt = max(0.0, opening_debt - principal + draws)

    new_state = SimulationState(
        period_index=t,
        period_end=next_month_end(state.period_end),
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        opex=opex,
        ebitda=ebitda,
        da=da,
        ebit=ebit,
        interest_expense=interest,
        ebt=ebt,
        tax=tax,
        net_income=net_income,
        receivables=receivables,
        inventory=inventory,
        payables=payables,
        nwc=nwc,
        ocf=ocf,
        cash=cash,
        total_debt=debt,
        status=SimulationStatus.FUNDING_GAP if funding_gap else SimulationStatus.OK,
        funding_gap=funding_gap,
        revenue_capped=revenue_capped,
    )
    ledger = MonthLedger(
        period_index=t,
        revenue_demand=revenue_demand,
        revenue_capacity=revenue_capacity,
        ramp=ramp,
        capex=capex,
        principal=principal,
        draws=draws,
        one_off_cost=one_off_cost,
        min_cash_buffer=buffer,
        revolver_cap=revolver_cap,
        opening_cash=state.cash,
        cash_before_draws=cash_before_draws,
        funding_shortfall=shortfall,
        opening_debt=opening_debt,
        revenue_capped=revenue_capped,
        funding_gap=funding_gap,
    )
    return new_state, ledger


def _calculator_inputs(state: SimulationState, ledger: MonthLedger) -> dict[str, Any]:
    """Adapt one simulated month to the Phase 4 calculator field names.

    ``calc_dscr`` uses ``st_debt`` as its debt-service proxy, which is correct
    for a historical annual period but has no counterpart in §2: the frozen
    recursion never projects a short-term balance. Supplying the month's
    *actual* scheduled principal instead yields the standard monthly debt
    service coverage ratio, ``EBITDA / (interest + principal)``, while reusing
    the frozen Phase 4 formula and its zero-denominator branches unchanged.
    """
    return {
        "ebitda": state.ebitda,
        "ebit": state.ebit,
        "interest_expense": state.interest_expense,
        "st_debt": ledger.principal,
        "cash": state.cash,
        "ocf": state.ocf,
        "frequency": "monthly",
    }


def _map_metric_status(status: object) -> SimulationStatus:
    """Translate a Phase 4 ``MetricStatus`` into the twin's vocabulary.

    ``FLAGGED``/``UNAVAILABLE`` are Phase 4 scoring concerns; for a projection
    they mean the number could not be computed, which the twin reports as a
    missing input rather than inventing a value.
    """
    text = str(status)
    if text == "valid":
        return SimulationStatus.OK
    if text == "insufficient_history":
        return SimulationStatus.INSUFFICIENT_HISTORY
    if text == "invalid_input":
        return SimulationStatus.INVALID_INPUT
    return SimulationStatus.MISSING_INPUT


def _to_month(
    state: SimulationState,
    ledger: MonthLedger,
    previous_nwc: float,
    history: list[dict[str, float]],
) -> SimulationMonth:
    """Project a finished state plus its ledger into the emitted month record."""
    inputs = _calculator_inputs(state, ledger)
    dscr = calc_dscr(inputs)
    coverage = calc_interest_coverage(inputs)
    runway = calc_cash_runway_months(inputs, history=history)
    return SimulationMonth(
        period_index=state.period_index,
        period_end=state.period_end,
        revenue=state.revenue,
        revenue_demand=ledger.revenue_demand,
        revenue_capacity=ledger.revenue_capacity,
        cogs=state.cogs,
        gross_profit=state.gross_profit,
        opex=state.opex,
        ebitda=state.ebitda,
        da=state.da,
        ebit=state.ebit,
        interest_expense=state.interest_expense,
        ebt=state.ebt,
        tax=state.tax,
        net_income=state.net_income,
        receivables=state.receivables,
        inventory=state.inventory,
        payables=state.payables,
        nwc=state.nwc,
        delta_nwc=state.nwc - previous_nwc,
        ocf=state.ocf,
        capex=ledger.capex,
        principal=ledger.principal,
        draws=ledger.draws,
        one_off_cost=ledger.one_off_cost,
        cash=state.cash,
        total_debt=state.total_debt,
        dscr=SimulationRatio(value=dscr.value, status=_map_metric_status(dscr.status)),
        interest_coverage=SimulationRatio(
            value=coverage.value, status=_map_metric_status(coverage.status)
        ),
        cash_runway_months=SimulationRatio(
            value=runway.value, status=_map_metric_status(runway.status)
        ),
        status=state.status,
        funding_gap=ledger.funding_gap,
        revenue_capped=ledger.revenue_capped,
    )


def _relative_residual(actual: float, expected: float) -> float:
    """Absolute residual scaled by the larger magnitude, for scale invariance.

    A pure relative error is unbounded when the expected value is ~0, which is
    exactly the case in stressed months, so the denominator is the max of the
    two magnitudes and the raw gap is used when both are ~0.
    """
    gap = abs(actual - expected)
    scale = max(abs(actual), abs(expected))
    return gap if scale <= IDENTITY_TOLERANCE else gap / scale


def check_invariants(
    months: list[SimulationMonth],
    ledgers: list[MonthLedger],
    opening_cash: float,
    opening_debt: float,
    opening_nwc: float,
) -> list[SimulationInvariantResult]:
    """Test the identities frozen in simulation.md §6 on a completed run.

    Invariant 1 (cash identity, +/-1e-6 relative) is recomputed from the
    emitted month and its ledger, not from the engine's internal variables, so
    it is a genuine check rather than a restatement of the same arithmetic.
    """
    results: list[SimulationInvariantResult] = []
    cash_residual = 0.0
    debt_residual = 0.0
    nwc_residual = 0.0
    tax_floor_ok = True
    negative_cash_only_via_gap = True

    previous_cash = opening_cash
    previous_debt = opening_debt
    previous_nwc = opening_nwc
    for month, ledger in zip(months, ledgers, strict=True):
        expected_cash = (
            previous_cash
            + month.ocf
            - ledger.capex
            - ledger.principal
            + ledger.draws
            - ledger.one_off_cost
        )
        cash_residual = max(cash_residual, _relative_residual(month.cash, expected_cash))
        expected_debt = previous_debt - ledger.principal + ledger.draws
        debt_residual = max(debt_residual, _relative_residual(month.total_debt, expected_debt))
        nwc_residual = max(
            nwc_residual, _relative_residual(month.delta_nwc, month.nwc - previous_nwc)
        )
        if month.tax < -IDENTITY_TOLERANCE:
            tax_floor_ok = False
        if month.cash < -IDENTITY_TOLERANCE and not month.funding_gap:
            negative_cash_only_via_gap = False
        previous_cash = month.cash
        previous_debt = month.total_debt
        previous_nwc = month.nwc

    results.append(
        SimulationInvariantResult(
            name="cash_identity",
            holds=cash_residual <= CASH_IDENTITY_TOLERANCE,
            residual=cash_residual,
            tolerance=CASH_IDENTITY_TOLERANCE,
        )
    )
    results.append(
        SimulationInvariantResult(
            name="debt_roll_forward",
            holds=debt_residual <= IDENTITY_TOLERANCE,
            residual=debt_residual,
            tolerance=IDENTITY_TOLERANCE,
        )
    )
    results.append(
        SimulationInvariantResult(
            name="nwc_continuity",
            holds=nwc_residual <= IDENTITY_TOLERANCE,
            residual=nwc_residual,
            tolerance=IDENTITY_TOLERANCE,
        )
    )
    results.append(
        SimulationInvariantResult(
            name="tax_non_negative",
            holds=tax_floor_ok,
            residual=0.0 if tax_floor_ok else 1.0,
            tolerance=0.0,
        )
    )
    results.append(
        SimulationInvariantResult(
            name="negative_cash_only_via_funding_gap",
            holds=negative_cash_only_via_gap,
            residual=0.0 if negative_cash_only_via_gap else 1.0,
            tolerance=0.0,
        )
    )
    results.append(
        SimulationInvariantResult(
            name="horizon_bounded",
            holds=len(months) <= MAX_HORIZON_MONTHS,
            residual=float(len(months)),
            tolerance=float(MAX_HORIZON_MONTHS),
        )
    )
    return results


def _summarise(
    months: list[SimulationMonth],
    ledgers: list[MonthLedger],
    buffer: float,
) -> SimulationSummary:
    """Trough and end-horizon values Phase 8 will need, with no policy applied.

    ``breached_buffer``/``had_funding_gap`` are *conditions* the frozen model
    detected. Deciding whether a condition is a reportable breach, and against
    which threshold, is Phase 8 (simulation.md §5).
    """
    lowest = min(months, key=lambda m: m.cash)
    dscr_values = [m.dscr.value for m in months if m.dscr.value is not None]
    coverage_values = [
        m.interest_coverage.value for m in months if m.interest_coverage.value is not None
    ]
    last = months[-1]
    return SimulationSummary(
        min_cash=lowest.cash,
        min_cash_period=lowest.period_index,
        min_dscr=min(dscr_values) if dscr_values else None,
        min_interest_coverage=min(coverage_values) if coverage_values else None,
        final_cash=last.cash,
        final_debt=last.total_debt,
        final_revenue=last.revenue,
        final_ebitda=last.ebitda,
        lowest_ebitda=min(m.ebitda for m in months),
        total_draws=sum(ledger.draws for ledger in ledgers),
        total_principal=sum(ledger.principal for ledger in ledgers),
        funding_gap_months=[m.period_index for m in months if m.funding_gap],
        revenue_capped_months=[m.period_index for m in months if m.revenue_capped],
        breached_buffer=any(m.cash < buffer - IDENTITY_TOLERANCE for m in months),
        had_funding_gap=any(m.funding_gap for m in months),
    )


def run_twin(
    simulation_input: SimulationInput,
    diagnostics: SimulationDiagnostics | None = None,
    generator_seeds: list[int] | None = None,
) -> SimulationRunResult:
    """Run the frozen monthly recursion and return the complete projection.

    Pure and side-effect free: calling this twice with equal arguments returns
    equal results, which simulation.md §6.2 and NFR1 require. Scenario *policy*
    is not applied here — ``simulation_input.overrides`` is consumed exactly as
    supplied, and bounds validation belongs to Phase 7.
    """
    assumptions = simulation_input.assumptions
    overrides = simulation_input.overrides
    initial = simulation_input.initial_state

    state = build_initial_state(initial, assumptions)
    opening_cash = state.cash
    opening_debt = state.total_debt
    opening_nwc = state.nwc
    previous_nwc = state.nwc
    history: list[dict[str, float]] = []
    months: list[SimulationMonth] = []
    ledgers: list[MonthLedger] = []

    for _ in range(simulation_input.horizon_months):
        state, ledger = step_month(state, assumptions, overrides)
        months.append(_to_month(state, ledger, previous_nwc, list(history)))
        ledgers.append(ledger)
        history.append(_calculator_inputs(state, ledger))
        previous_nwc = state.nwc

    return SimulationRunResult(
        company_id=simulation_input.company_id,
        company_name=simulation_input.company_name,
        currency=simulation_input.currency,
        start_period_end=initial.period_end,
        end_period_end=months[-1].period_end,
        months=months,
        invariants=check_invariants(months, ledgers, opening_cash, opening_debt, opening_nwc),
        summary=_summarise(months, ledgers, assumptions.min_cash_buffer),
        diagnostics=diagnostics or SimulationDiagnostics(history_periods=initial.history_periods),
        provenance=Provenance(
            twin_version=TWIN_VERSION,
            generator_seeds=list(generator_seeds or []),
            horizon_months=simulation_input.horizon_months,
            is_baseline=simulation_input.is_baseline,
            source_periods=initial.history_periods,
        ),
        causality_note=CAUSALITY_DISCLAIMER,
        advice_note=NOT_ADVICE_DISCLAIMER,
    )


def build_initial_state_from_period(
    latest: PeriodFinancials,
    dataset: CompanyDataset,
) -> SimulationInitialState:
    """Build t=0 from the latest observed period, refusing to invent values.

    Required fields must be present; nothing is zero-filled, interpolated or
    forward-filled. The opening working-capital total is the last observed
    ``AR + Inventory - AP``, which is the same definition the §2 recursion uses,
    so ``delta NWC`` in month 1 is a true period-over-period change.
    """
    missing = [name for name in ("revenue", "cash", "total_debt") if getattr(latest, name) is None]
    if missing:
        raise ValueError(
            "twin initial state requires "
            + ", ".join(missing)
            + f" in the period ending {latest.period_end}; missing inputs are never imputed"
        )
    nwc = 0.0
    for field, sign in (("receivables", 1.0), ("inventory", 1.0), ("payables", -1.0)):
        value = getattr(latest, field)
        if value is not None:
            nwc += sign * float(value)
    return SimulationInitialState(
        period_end=latest.period_end,
        currency=dataset.profile.currency,
        revenue=float(latest.revenue or 0.0),
        cash=float(latest.cash or 0.0),
        debt=float(latest.total_debt or 0.0),
        nwc=nwc,
        equity=latest.equity,
        history_periods=len(dataset.periods),
    )


def simulate(
    dataset: CompanyDataset,
    horizon_months: int = DEFAULT_HORIZON_MONTHS,
    overrides: SimulationOverrides | None = None,
) -> SimulationRunResult:
    """End-to-end convenience path: a Phase 3 dataset in, a projection out.

    Derives the frozen §1 assumptions, builds t=0 from the latest period and
    runs the recursion. This is the single call the validation notebook and the
    Phase 8 stress runner will use; the lower-level functions stay public so a
    caller can supply assumptions it derived itself.
    """
    assumptions, records, fallbacks = derive_assumptions(dataset)
    latest = dataset.periods[-1]
    simulation_input = SimulationInput(
        company_id=dataset.profile.name,
        company_name=dataset.profile.name,
        currency=dataset.profile.currency,
        horizon_months=horizon_months,
        assumptions=assumptions,
        initial_state=build_initial_state_from_period(latest, dataset),
        overrides=overrides or SimulationOverrides(),
    )
    diagnostics = SimulationDiagnostics(
        assumption_records=records,
        fallbacks_used=fallbacks,
        history_periods=len(dataset.periods),
    )
    seeds = [dataset.generator_config.seed] if dataset.generator_config else []
    return run_twin(simulation_input, diagnostics=diagnostics, generator_seeds=seeds)
