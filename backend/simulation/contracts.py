"""Typed contracts for the Business Digital Twin (Phase 6).

Field-level freezing: docs/01_architecture/simulation.md §1 (twin parameter
table, [R]/[A] tags, constraints) and §2 (monthly recursion). Structural
conventions follow the existing engines — ``extra="forbid"``, Pydantic
``Field`` bounds, and ``math.isfinite`` guards, mirroring
``data_engine.contracts.PeriodFinancials`` and ``risk_engine.contracts``.

Unit convention (decision D-6): every scenario delta in
``SimulationOverrides`` is a *decimal fraction* (0.02 == 2 percentage points,
-0.15 == -15%). Converting the Phase 7 scenario JSON schema's ``*_pct`` /
``*_pp`` values into fractions is Phase 7's job; the twin only ever sees
fractions. Amounts are in the company reporting currency; ratios (g, c0, tau,
DSO ...) are unitless and per-month where the recursion divides by 12.
"""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.data_engine.contracts import AllowedCurrency
from backend.risk_engine.contracts import REGISTRY_VERSION

# Version of the twin model itself. Bumped on any change to the frozen
# recursion in docs/01_architecture/simulation.md §2. testing.md §4 (frozen):
# "A golden change without a registry/twin version bump is a defect" — so a
# trajectory golden may only move when this value moves.
TWIN_VERSION = "1.0.0"

# Frozen interpretation labels carried on every twin output. A simulation shows
# what the documented equations imply under the stated assumptions; it is not
# evidence about why the business behaves that way, and it is not advice.
CAUSALITY_DISCLAIMER = (
    "Assumption-based intervention on a model, not discovered causal truth: "
    "twin deltas show what the documented equations imply under the stated "
    "assumptions, not why the business behaves that way."
)
NOT_ADVICE_DISCLAIMER = (
    "Not professional financial advice, not a forecast and not a regulatory "
    "model; outputs are reproducible engineering artifacts, not financial "
    "recommendations."
)

# Frozen horizon bound (simulation.md §1: "Horizon H <= 36 months; monthly
# step t = 1..H"). simulation.md fixes the maximum but not the default; the
# value 12 matches the Phase 7 scenario schema default (decision D-3).
MAX_HORIZON_MONTHS = 36
DEFAULT_HORIZON_MONTHS = 12

# simulation.md §6.1: cash identity holds to +/-1e-6 *relative*.
CASH_IDENTITY_TOLERANCE = 1e-6
# Algebraic identities (debt roll, NWC continuity) are exact by construction;
# 1e-9 matches the existing golden tolerance in test_golden_profiles.py.
IDENTITY_TOLERANCE = 1e-9

# Minimum trailing window required to derive g, c0, DSO/DIO/DPO, Capex0 and
# Capacity0 (all are "trailing 12-mo" derivations, simulation.md §1). There is
# no shorter window that can honour the frozen specification, and inventing one
# would be silent fabrication, so short histories abort rather than degrade.
MIN_TRAILING_MONTHS = 12
TRAILING_WINDOW = 12

# Debt amortization buckets (data_engine.contracts.DebtScheduleEntry literals)
# with the month window each covers, measured from t=0. simulation.md §1 says
# "equal amortization inside buckets" but does not fix the window lengths, so
# they are derived from the bucket names themselves (decision D-2, recorded in
# docs/06_digital_twin/phase-report.md).
DEBT_BUCKETS: dict[str, int] = {"0-3m": 3, "3-12m": 9, "1-3y": 24, "3y+": 36}


class ParameterTag(StrEnum):
    """Provenance tag for a twin parameter (simulation.md §1)."""

    REAL = "real"
    ASSUMPTION = "assumption"
    SCENARIO = "scenario"


class SimulationStatus(StrEnum):
    """Per-period simulation outcome.

    Deliberately *not* an extension of ``risk_engine.MetricStatus``: that enum
    is frozen Phase 4 vocabulary, and the twin needs states it has no name for
    (``funding_gap``, ``insufficient_history``) while never needing
    ``flagged``/``unavailable``. A separate enum keeps Phase 4 untouched
    (decision D-10).
    """

    OK = "ok"
    MISSING_INPUT = "missing_input"
    INVALID_INPUT = "invalid_input"
    INSUFFICIENT_HISTORY = "insufficient_history"
    FUNDING_GAP = "funding_gap"


class AssumptionRecord(BaseModel):
    """One derived [R]/[A] parameter and exactly how it was obtained."""

    model_config = ConfigDict(extra="forbid")

    parameter: str
    value: float
    tag: ParameterTag
    source: str
    fallback_used: bool = False


class DebtAmortization(BaseModel):
    """One debt bucket spread evenly across its month window (simulation.md §1)."""

    model_config = ConfigDict(extra="forbid")

    bucket: Literal["0-3m", "3-12m", "1-3y", "3y+"]
    months: int = Field(ge=1)
    amount: float = Field(ge=0.0)
    monthly_principal: float = Field(ge=0.0)


_ASSUMPTION_FIELDS = (
    "growth_rate",
    "cogs_ratio",
    "fixed_cost",
    "variable_cost_ratio",
    "da_monthly",
    "dso",
    "dio",
    "dpo",
    "capex_monthly",
    "revenue_capacity",
    "initial_debt",
    "base_rate",
    "floating_debt_share",
    "min_cash_buffer",
    "revolver_cap",
    "tax_rate",
    "fx_import_cost_share",
    "fx_revenue_share",
    "commodity_cost_share",
    "pass_through",
    "fx_demand_elasticity",
)


class SimulationAssumptions(BaseModel):
    """The frozen §1 parameter set, fully derived before the first month.

    Every field carries the constraint printed in simulation.md §1. A value
    that required a documented fallback is additionally reported in
    ``SimulationDiagnostics.assumption_records`` with ``fallback_used=True``,
    so a reader can always tell a real input from an assumed one.
    """

    model_config = ConfigDict(extra="forbid")

    # --- operating ---
    growth_rate: float = Field(ge=-0.05, le=0.15)  # g, annual, clamped
    cogs_ratio: float = Field(ge=0.0, le=1.0)  # c0, trailing mean cogs/revenue
    fixed_cost: float = Field(ge=0.0)  # F, monthly opex intercept
    variable_cost_ratio: float = Field(ge=0.0)  # v, monthly opex slope
    da_monthly: float = Field(ge=0.0)  # DA, trailing da / 12
    dso: float = Field(ge=0.0)  # receivables days
    dio: float = Field(ge=0.0)  # inventory days
    dpo: float = Field(ge=0.0)  # payables days
    capex_monthly: float = Field(ge=0.0)  # Capex0, trailing mean
    revenue_capacity: float = Field(ge=0.0)  # Capacity0, trailing 12-mo max revenue
    # --- financing ---
    initial_debt: float = Field(ge=0.0)  # D0
    base_rate: float = Field(ge=0.0)  # r0, annual nominal
    floating_debt_share: float = Field(ge=0.0, le=1.0)  # phi
    debt_amortization: list[DebtAmortization] = Field(default_factory=list)
    min_cash_buffer: float = Field(ge=0.0)  # B = 1.0 x monthly opex
    revolver_cap: float = Field(ge=0.0)  # RC = 3.0 x monthly opex
    # --- tax ---
    tax_rate: float = Field(ge=0.0, le=0.45)  # tau
    # --- exposure / macro ---
    fx_import_cost_share: float = Field(ge=0.0, le=1.0)  # kappa_fx
    fx_revenue_share: float = Field(ge=0.0, le=1.0)  # rho_rev
    commodity_cost_share: float = Field(ge=0.0, le=1.0)  # kappa_c
    pass_through: float = Field(ge=0.0, le=1.0)  # ptc, shared with risk_engine
    fx_demand_elasticity: float = Field(ge=0.0, le=1.0)  # e_fx

    @field_validator(*_ASSUMPTION_FIELDS, mode="after")
    @classmethod
    def _finite_assumptions(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("twin assumptions must be finite")
        return value

    @model_validator(mode="after")
    def _revolver_covers_buffer(self) -> SimulationAssumptions:
        # simulation.md §1: "Revolver cap RC ... constraint RC >= B".
        if self.revolver_cap < self.min_cash_buffer:
            raise ValueError("revolver_cap must be >= min_cash_buffer")
        return self

    def principal_for_month(self, period_index: int) -> float:
        """Scheduled principal repaid in month ``period_index`` (t = 1..H).

        "Equal amortization inside buckets" (simulation.md §1): each bucket's
        amount is spread evenly over its month window, and a month repays every
        bucket whose window contains it. Buckets are read from ``periods[-1]``
        so the schedule is consumed exactly once.
        """
        total = 0.0
        for entry in self.debt_amortization:
            start = _bucket_start_month(entry.bucket)
            if start <= period_index <= start + entry.months - 1:
                total += entry.monthly_principal
        return total


def _bucket_start_month(bucket: str) -> int:
    """First simulated month (1-based) covered by a debt bucket.

    "0-3m" -> month 1, "3-12m" -> month 4, "1-3y" -> month 13, "3y+" -> month
    37 (beyond the 36-month frozen horizon, so it never repays in a run).
    """
    return {"0-3m": 1, "3-12m": 4, "1-3y": 13, "3y+": 37}[bucket]


class SimulationOverrides(BaseModel):
    """Already-structured [S] scenario deltas, expressed as decimal fractions.

    Phase 6 validates *type and finiteness only*. The bounded JSON schema, the
    out-of-range clamp/reject policy, the presets and natural-language
    translation all belong to Phase 7 (simulation.md §3-§4), so no bound is
    enforced here beyond the two structural ones below: a cost cannot be
    negative and a ramp cannot be negative.
    """

    model_config = ConfigDict(extra="forbid")

    ramp_months: int = Field(default=0, ge=0)
    revenue_change: float = 0.0
    cogs_change: float = 0.0
    opex_change: float = 0.0
    rate_change: float = 0.0
    fx_change: float = 0.0
    commodity_change: float = 0.0
    supplier_disruption: float = 0.0
    capex_change: float = 0.0
    ar_days_change: float = 0.0
    one_off_cost: float = Field(default=0.0, ge=0.0)

    @field_validator(
        "revenue_change",
        "cogs_change",
        "opex_change",
        "rate_change",
        "fx_change",
        "commodity_change",
        "supplier_disruption",
        "capex_change",
        "ar_days_change",
        "one_off_cost",
        mode="after",
    )
    @classmethod
    def _finite_overrides(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("scenario deltas must be finite")
        return value

    @property
    def is_baseline(self) -> bool:
        """True when every delta is zero, i.e. a pure baseline projection."""
        return all(
            getattr(self, field) == 0.0
            for field in (
                "revenue_change",
                "cogs_change",
                "opex_change",
                "rate_change",
                "fx_change",
                "commodity_change",
                "supplier_disruption",
                "capex_change",
                "ar_days_change",
                "one_off_cost",
            )
        )

    def ramp_factor(self, period_index: int) -> float:
        """Linear ramp weight in [0, 1] for a delta at month ``period_index``.

        simulation.md §2: "Scenario deltas enter as step changes at t = 1
        unless ramp_months R > 0 (linear ramp over R months)". So R = 0 (or
        absent) is a step that is fully applied from t = 1, and R > 0 reaches
        full effect at t = R.
        """
        if self.ramp_months <= 0:
            return 1.0
        return min(1.0, period_index / self.ramp_months)


class SimulationInitialState(BaseModel):
    """t = 0: the last observed period, carried into the first simulated month."""

    model_config = ConfigDict(extra="forbid")

    period_end: date
    currency: AllowedCurrency = "INR"
    revenue: float = Field(ge=0.0)
    cash: float = Field(ge=0.0)
    debt: float = Field(ge=0.0)
    nwc: float
    equity: float | None = None
    history_periods: int = Field(ge=0)

    @field_validator("revenue", "cash", "debt", "nwc", "equity", mode="after")
    @classmethod
    def _finite_state(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("initial state values must be finite")
        return value


class SimulationInput(BaseModel):
    """Everything one twin run needs. No hidden globals, no I/O."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = ""
    company_name: str = ""
    currency: AllowedCurrency = "INR"
    horizon_months: int = Field(default=DEFAULT_HORIZON_MONTHS, ge=1, le=MAX_HORIZON_MONTHS)
    assumptions: SimulationAssumptions
    initial_state: SimulationInitialState
    overrides: SimulationOverrides = Field(default_factory=SimulationOverrides)

    @property
    def is_baseline(self) -> bool:
        return self.overrides.is_baseline


class SimulationState(BaseModel):
    """Twin state. Exactly what the §2 recursion advances from month to month.

    Deliberately *not* a full balance sheet: simulation.md §2 defines no
    recursion for ``equity``/``total_assets``, so projecting one would invent
    methodology that the frozen specification does not contain (decision D-4).
    """

    model_config = ConfigDict(extra="forbid")

    period_index: int = Field(ge=0)
    period_end: date
    revenue: float
    cogs: float
    gross_profit: float
    opex: float
    ebitda: float
    da: float
    ebit: float
    interest_expense: float
    ebt: float
    tax: float
    net_income: float
    receivables: float
    inventory: float
    payables: float
    nwc: float
    ocf: float
    cash: float
    total_debt: float
    status: SimulationStatus = SimulationStatus.OK
    funding_gap: bool = False
    revenue_capped: bool = False

    @model_validator(mode="after")
    def _debt_never_negative(self) -> SimulationState:
        # The recursion cannot repay more than is outstanding; a negative
        # balance would be a modelling bug, not a valid stressed state.
        if self.total_debt < -IDENTITY_TOLERANCE:
            raise ValueError("simulated debt must not be negative")
        return self


class SimulationRatio(BaseModel):
    """A ratio emitted per month together with the status of its calculation.

    Keeps the Phase 4 convention of reporting *why* a number is absent rather
    than substituting a zero.
    """

    model_config = ConfigDict(extra="forbid")

    value: float | None = None
    status: SimulationStatus = SimulationStatus.OK

    @property
    def is_available(self) -> bool:
        return self.value is not None


class SimulationMonth(BaseModel):
    """One projected month, t = 1..H.

    Field names mirror ``PeriodFinancials`` (revenue/cogs/gross_profit/opex/
    ebitda/da/ebit/interest_expense/tax/net_income/cash/receivables/inventory/
    payables/ocf) so downstream phases and the Phase 4 calculators consume a
    month without a translation layer.
    """

    model_config = ConfigDict(extra="forbid")

    period_index: int = Field(ge=1)
    period_end: date
    # income statement
    revenue: float
    revenue_demand: float
    revenue_capacity: float
    cogs: float
    gross_profit: float
    opex: float
    ebitda: float
    da: float
    ebit: float
    interest_expense: float
    ebt: float
    tax: float
    net_income: float
    # working capital
    receivables: float
    inventory: float
    payables: float
    nwc: float
    delta_nwc: float
    # cash flow and financing
    ocf: float
    capex: float
    principal: float
    draws: float
    one_off_cost: float
    cash: float
    total_debt: float
    # ratios (Phase 4 calculators)
    dscr: SimulationRatio = Field(default_factory=SimulationRatio)
    interest_coverage: SimulationRatio = Field(default_factory=SimulationRatio)
    cash_runway_months: SimulationRatio = Field(default_factory=SimulationRatio)
    # status
    status: SimulationStatus = SimulationStatus.OK
    funding_gap: bool = False
    revenue_capped: bool = False

    @property
    def is_healthy(self) -> bool:
        return self.status is SimulationStatus.OK


class MonthLedger(BaseModel):
    """The financing and channel detail of one stepped month.

    These are *flows and ceilings* for the month, not balances, so they are kept
    beside the state rather than inside it: that is what lets the cash identity
    be re-checked independently instead of being a tautology of the same
    variables that produced cash.
    """

    model_config = ConfigDict(extra="forbid")

    period_index: int = Field(ge=1)
    revenue_demand: float
    revenue_capacity: float
    ramp: float = Field(ge=0.0)
    capex: float = Field(ge=0.0)
    principal: float = Field(ge=0.0)
    draws: float = Field(ge=0.0)
    one_off_cost: float = Field(ge=0.0)
    min_cash_buffer: float = Field(ge=0.0)
    revolver_cap: float = Field(ge=0.0)
    opening_cash: float
    cash_before_draws: float
    funding_shortfall: float = Field(ge=0.0)
    opening_debt: float = Field(ge=0.0)
    revenue_capped: bool = False
    funding_gap: bool = False


class SimulationInvariantResult(BaseModel):
    """One tested identity and whether it held on this run."""

    model_config = ConfigDict(extra="forbid")

    name: str
    holds: bool
    residual: float
    tolerance: float


class SimulationDiagnostics(BaseModel):
    """How the run was set up, and every place an assumption had to stand in."""

    model_config = ConfigDict(extra="forbid")

    assumption_records: list[AssumptionRecord] = Field(default_factory=list)
    fallbacks_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    history_periods: int = 0
    trailing_window: int = TRAILING_WINDOW


class SimulationSummary(BaseModel):
    """Trough and end-horizon values: the raw material for Phase 8 deltas.

    Phase 6 reports what happened; it does not compare runs and does not decide
    that anything is a breach. ``breached_buffer``/``had_funding_gap`` are
    pre-computed *conditions*; thresholds and the breach policy are Phase 8
    (simulation.md §5).
    """

    model_config = ConfigDict(extra="forbid")

    min_cash: float
    min_cash_period: int
    min_dscr: float | None = None
    min_interest_coverage: float | None = None
    final_cash: float
    final_debt: float
    final_revenue: float
    final_ebitda: float
    lowest_ebitda: float
    total_draws: float = 0.0
    total_principal: float = 0.0
    funding_gap_months: list[int] = Field(default_factory=list)
    revenue_capped_months: list[int] = Field(default_factory=list)
    breached_buffer: bool = False
    had_funding_gap: bool = False


class Provenance(BaseModel):
    """Reproducibility stamp carried on every twin run."""

    model_config = ConfigDict(extra="forbid")

    twin_version: str
    registry_version: str = REGISTRY_VERSION
    generator_seeds: list[int] = Field(default_factory=list)
    horizon_months: int = 0
    is_baseline: bool = True
    source_periods: int = 0
    detail: dict[str, Any] = Field(default_factory=dict)


class SimulationRunResult(BaseModel):
    """Complete, machine-readable output of one twin run."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = ""
    company_name: str = ""
    currency: AllowedCurrency = "INR"
    start_period_end: date
    end_period_end: date
    months: list[SimulationMonth] = Field(default_factory=list)
    invariants: list[SimulationInvariantResult] = Field(default_factory=list)
    summary: SimulationSummary
    diagnostics: SimulationDiagnostics = Field(default_factory=SimulationDiagnostics)
    provenance: Provenance
    causality_note: str = ""
    advice_note: str = ""

    @property
    def horizon_months(self) -> int:
        return len(self.months)

    @property
    def invariants_hold(self) -> bool:
        return all(inv.holds for inv in self.invariants)

    def trajectory(self, field: str) -> list[float]:
        """Time series for one SimulationMonth field, for charting and Phase 8."""
        return [float(getattr(m, field)) for m in self.months]
