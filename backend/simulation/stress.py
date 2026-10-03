"""Stress Testing & Impact Analysis — deterministic comparison (Phase 8).

Runs a validated Phase 7 scenario against the frozen Phase 6 twin twice
(baseline with zero overrides, stressed with the scenario's overrides),
then compares: KPI impacts (trough + end-horizon), breach detection on the
frozen simulation.md §5 policy, an exact monthly-then-sum EBITDA waterfall
with a below-EBITDA bridge to net income, and a structured result.

Frozen authority: docs/01_architecture/simulation.md §5 (outputs) and §6
(invariants: reproducibility, breach consistency, 0.5% waterfall closure).
Locked Phase 8 decisions from the approved plan addendum are recorded
inline as ``Decision <letter>`` comments.

Scope boundaries (deliberate, enforced by this module's contents):
- This module compares twin outputs. It does not re-derive assumptions,
  re-implement the §2 recursion, or score risk (no dimension deltas: the
  risk engine needs balance-sheet fields the twin never projects — see
  ``dimension_deltas_note``; fabricating them would invent methodology).
- It performs no LLM calls, no I/O, no network, no database writes and is
  not served (architecture rules R1/R3). No ``backend/guardrails/``
  package is created (decision L from Phase 7 stands).
- Breach output is deterministic status/records only — no severity levels
  (locked decision E).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import CompanyDataset
from backend.simulation import scenarios as sc
from backend.simulation.contracts import (
    REGISTRY_VERSION,
    TWIN_VERSION,
    SimulationRunResult,
)
from backend.simulation.twin import simulate

# Decision A: Phase 8 version covering comparison + breach + waterfall +
# sensitivity behavior. Bumped on any change to that logic — mirroring
# TWIN_VERSION / SCENARIO_VERSION / REGISTRY_VERSION.
STRESS_VERSION = "1.0.0"

# Waterfall closure: components sum to total impact within 0.5% (frozen
# simulation.md §6.5, requirements FR6), with an absolute floor so the
# zero-delta case is well-defined.
WATERFALL_CLOSURE_REL = 0.005

# Frozen simulation.md §5 breach defaults ("defaults, configurable").
RUNWAY_BREACH_MONTHS = 6.0
DSCR_BREACH = 1.2
INTEREST_COVERAGE_BREACH = 1.5

# Frozen §5 breach listing order. Never alphabetical (locked decision F).
BREACH_ORDER: tuple[str, ...] = (
    "runway_below_6_months",
    "dscr_below_1_2",
    "interest_coverage_below_1_5",
    "cash_below_buffer",
    "funding_gap_occurred",
    "current_ratio_proxy_below_1",
)

# Frozen §5 KPI listing order. Never alphabetical (locked decision F).
KPI_ORDER: tuple[str, ...] = (
    "revenue",
    "ebitda",
    "net_income",
    "min_cash",
    "runway",
    "min_dscr",
)

# Frozen §5 waterfall order, then the below-EBITDA bridge order.
WATERFALL_ORDER: tuple[str, ...] = (
    "revenue_effect",
    "input_cost_effect",
    "opex_effect",
    "other_one_off",
)
BRIDGE_ORDER: tuple[str, ...] = ("interest_effect", "tax_effect")


class KPIImpact(BaseModel):
    """One KPI delta: baseline / stressed / absolute / percent (plan §D)."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    scope: str  # "trough" | "end"
    baseline: float | None = None
    stressed: float | None = None
    delta_absolute: float | None = None
    delta_pct: float | None = None
    delta_pct_reason: str = ""
    unit: str = ""
    higher_better: bool = True


class Breach(BaseModel):
    """One frozen-policy breach rule evaluated on the stressed run."""

    model_config = ConfigDict(extra="forbid")

    rule: str
    metric: str
    threshold: float | None = None
    observed: float | None = None
    periods: list[int] = Field(default_factory=list)
    status: str = "not_breached"  # "breached" | "not_breached" | "unevaluable"
    reason: str = ""


class WaterfallComponent(BaseModel):
    """One frozen-order waterfall/bridge component (plan §5 order)."""

    model_config = ConfigDict(extra="forbid")

    component: str
    delta_ebitda: float = 0.0
    delta_ni: float | None = None
    note: str = ""


class BreachPolicy(BaseModel):
    """Optional overrides of the frozen §5 breach defaults.

    Every field defaults to None meaning "use the frozen default"; an
    explicit value replaces that threshold for this run only. No
    persistence of custom policies (Phase 10).
    """

    model_config = ConfigDict(extra="forbid")

    runway_months: float | None = None
    dscr: float | None = None
    interest_coverage: float | None = None

    def _finite_or_raise(self, name: str, value: float | None) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"breach policy '{name}' must be a number",
                {"field": name, "observed": value},
            )
        finite = float(value)
        if not math.isfinite(finite):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"breach policy '{name}' must be finite",
                {"field": name, "observed": value},
            )
        return finite

    def resolved(self) -> dict[str, float]:
        """Frozen defaults with explicit overrides applied."""
        runway = self._finite_or_raise("runway_months", self.runway_months)
        dscr = self._finite_or_raise("dscr", self.dscr)
        coverage = self._finite_or_raise("interest_coverage", self.interest_coverage)
        return {
            "runway_months": RUNWAY_BREACH_MONTHS if runway is None else runway,
            "dscr": DSCR_BREACH if dscr is None else dscr,
            "interest_coverage": (INTEREST_COVERAGE_BREACH if coverage is None else coverage),
        }


class StressTestResult(BaseModel):
    """Complete deterministic output of one baseline-vs-stressed comparison."""

    model_config = ConfigDict(extra="forbid")

    scenario_name: str
    horizon_months: int
    baseline: SimulationRunResult
    stressed: SimulationRunResult
    kpi_impacts: list[KPIImpact] = Field(default_factory=list)
    breaches: list[Breach] = Field(default_factory=list)
    waterfall: list[WaterfallComponent] = Field(default_factory=list)
    below_bridge: list[WaterfallComponent] = Field(default_factory=list)
    interaction_residual: float = 0.0
    dimension_deltas: Any | None = None
    dimension_deltas_note: dict[str, Any] = Field(default_factory=dict)
    stress_version: str = STRESS_VERSION
    scenario_version: str = sc.SCENARIO_VERSION
    twin_version: str = TWIN_VERSION
    registry_version: str = REGISTRY_VERSION
    validated_params_hash: str = ""
    result_hash: str = ""
    causality_note: str = ""
    advice_note: str = ""


def _require_validated(validated: sc.ValidatedScenario) -> None:
    """Only VALIDATED scenarios execute — AI input must confirm first."""
    if validated.confirmation_status is not sc.ScenarioConfirmationStatus.VALIDATED:
        raise AppError(
            ErrorCode.SCENARIO_PENDING_CONFIRM,
            "scenario must be validated before stress execution",
            {"status": validated.confirmation_status.value},
        )


def _resolve_horizon(validated: sc.ValidatedScenario, horizon_override: int | None) -> int:
    """Decision C: the scenario horizon is the execution horizon."""
    horizon = validated.params.horizon_months
    if horizon_override is None:
        return horizon
    if not isinstance(horizon_override, int) or isinstance(horizon_override, bool):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "horizon_override must be an integer",
            {"observed": horizon_override},
        )
    if horizon_override != horizon:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "horizon_override must equal the validated scenario horizon",
            {"scenario_horizon": horizon, "observed": horizon_override},
        )
    return horizon


def _pct_change(baseline: float | None, stressed: float | None) -> tuple[float | None, str]:
    """Decision D: Δ% is None (with reason) when the baseline is 0/None."""
    if baseline is None or stressed is None:
        return None, "unavailable_input"
    if baseline == 0.0:
        return None, "zero_baseline"
    value = (stressed - baseline) / abs(baseline)
    if not math.isfinite(value):
        return None, "nonfinite_result"
    return value, ""


def _impact(
    metric: str,
    scope: str,
    baseline: float | None,
    stressed: float | None,
    *,
    unit: str,
    higher_better: bool = True,
) -> KPIImpact:
    """One KPI row: absolute delta always numeric-or-None, Δ% per decision D."""
    if baseline is None or stressed is None:
        absolute: float | None = None
    else:
        absolute = stressed - baseline
        if not math.isfinite(absolute):
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "nonfinite KPI delta from twin outputs",
                {"metric": metric, "scope": scope},
            )
    pct, reason = _pct_change(baseline, stressed)
    return KPIImpact(
        metric=metric,
        scope=scope,
        baseline=baseline,
        stressed=stressed,
        delta_absolute=absolute,
        delta_pct=pct,
        delta_pct_reason=reason,
        unit=unit,
        higher_better=higher_better,
    )


def _ratio_values(run: SimulationRunResult, field: str) -> list[float | None]:
    return [getattr(m, field).value for m in run.months]


def compare_kpis(
    baseline: SimulationRunResult, stressed: SimulationRunResult, *, currency: str
) -> list[KPIImpact]:
    """Frozen §5 KPI comparison at trough and end-horizon, in frozen order."""
    impacts: list[KPIImpact] = []

    base_rev = baseline.trajectory("revenue")
    stress_rev = stressed.trajectory("revenue")
    impacts.append(_impact("revenue", "trough", min(base_rev), min(stress_rev), unit=currency))
    impacts.append(_impact("revenue", "end", base_rev[-1], stress_rev[-1], unit=currency))

    base_ebitda = baseline.trajectory("ebitda")
    stress_ebitda = stressed.trajectory("ebitda")
    impacts.append(_impact("ebitda", "trough", min(base_ebitda), min(stress_ebitda), unit=currency))
    impacts.append(_impact("ebitda", "end", base_ebitda[-1], stress_ebitda[-1], unit=currency))

    base_ni = baseline.trajectory("net_income")
    stress_ni = stressed.trajectory("net_income")
    impacts.append(_impact("net_income", "trough", min(base_ni), min(stress_ni), unit=currency))
    impacts.append(_impact("net_income", "end", base_ni[-1], stress_ni[-1], unit=currency))

    impacts.append(
        _impact(
            "min_cash",
            "trough",
            baseline.summary.min_cash,
            stressed.summary.min_cash,
            unit=currency,
        )
    )
    impacts.append(
        _impact(
            "min_cash",
            "end",
            baseline.summary.final_cash,
            stressed.summary.final_cash,
            unit=currency,
        )
    )

    base_runway = [v for v in _ratio_values(baseline, "cash_runway_months") if v is not None]
    stress_runway = [v for v in _ratio_values(stressed, "cash_runway_months") if v is not None]
    impacts.append(
        _impact(
            "runway",
            "trough",
            min(base_runway) if base_runway else None,
            min(stress_runway) if stress_runway else None,
            unit="months",
        )
    )
    last_base_runway = _ratio_values(baseline, "cash_runway_months")[-1]
    last_stress_runway = _ratio_values(stressed, "cash_runway_months")[-1]
    impacts.append(_impact("runway", "end", last_base_runway, last_stress_runway, unit="months"))

    base_dscr = [v for v in _ratio_values(baseline, "dscr") if v is not None]
    stress_dscr = [v for v in _ratio_values(stressed, "dscr") if v is not None]
    impacts.append(
        _impact(
            "min_dscr",
            "trough",
            min(base_dscr) if base_dscr else None,
            min(stress_dscr) if stress_dscr else None,
            unit="ratio",
        )
    )
    impacts.append(
        _impact(
            "min_dscr",
            "end",
            _ratio_values(baseline, "dscr")[-1],
            _ratio_values(stressed, "dscr")[-1],
            unit="ratio",
        )
    )
    return impacts


def _monthly_breach(
    rule: str,
    metric: str,
    values: Sequence[float | None],
    threshold: float,
    *,
    observed_worst: float | None,
) -> Breach:
    """One threshold rule evaluated month-by-month (locked decision E)."""
    periods = [
        index + 1 for index, value in enumerate(values) if value is not None and value < threshold
    ]
    return Breach(
        rule=rule,
        metric=metric,
        threshold=threshold,
        observed=observed_worst,
        periods=periods,
        status="breached" if periods else "not_breached",
        reason="" if periods else f"no month below {threshold}",
    )


def detect_breaches(
    stressed: SimulationRunResult,
    *,
    buffer: float,
    policy: BreachPolicy | None = None,
) -> list[Breach]:
    """Frozen §5 breach policy on the stressed run, in frozen order.

    Blocker B1: the current-ratio proxy is not computable — the twin
    projects no current_assets/current_liabilities (deliberate D-4) and
    the frozen spec defines no proxy formula, so inventing one would be
    new financial methodology. It is emitted as ``unevaluable`` with an
    explicit machine-readable reason, and the frozen rule stays documented
    as deferred.
    """
    thresholds = (policy or BreachPolicy()).resolved()
    breaches: list[Breach] = []

    runway = _ratio_values(stressed, "cash_runway_months")
    runway_known = [v for v in runway if v is not None]
    breaches.append(
        _monthly_breach(
            "runway_below_6_months",
            "cash_runway_months",
            runway,
            thresholds["runway_months"],
            observed_worst=min(runway_known) if runway_known else None,
        )
    )

    dscr = _ratio_values(stressed, "dscr")
    dscr_known = [v for v in dscr if v is not None]
    breaches.append(
        _monthly_breach(
            "dscr_below_1_2",
            "dscr",
            dscr,
            thresholds["dscr"],
            observed_worst=min(dscr_known) if dscr_known else None,
        )
    )

    coverage = _ratio_values(stressed, "interest_coverage")
    coverage_known = [v for v in coverage if v is not None]
    breaches.append(
        _monthly_breach(
            "interest_coverage_below_1_5",
            "interest_coverage",
            coverage,
            thresholds["interest_coverage"],
            observed_worst=min(coverage_known) if coverage_known else None,
        )
    )

    cash = stressed.trajectory("cash")
    breaches.append(
        _monthly_breach("cash_below_buffer", "cash", cash, buffer, observed_worst=min(cash))
    )

    gap_months = list(stressed.summary.funding_gap_months)
    breaches.append(
        Breach(
            rule="funding_gap_occurred",
            metric="funding_gap",
            threshold=None,
            observed=float(len(gap_months)),
            periods=gap_months,
            status="breached" if gap_months else "not_breached",
            reason="funding gap months recorded by the twin" if gap_months else "no funding gap",
        )
    )

    breaches.append(
        Breach(
            rule="current_ratio_proxy_below_1",
            metric="current_ratio_proxy",
            threshold=1.0,
            observed=None,
            periods=[],
            status="unevaluable",
            reason=(
                "the twin projects AR/Inventory/AP flows but no "
                "current_assets/current_liabilities levels (D-4); the frozen "
                "spec defines no proxy formula and Phase 8 does not invent "
                "financial methodology"
            ),
        )
    )
    return breaches


def attribute_waterfall(
    baseline: SimulationRunResult, stressed: SimulationRunResult
) -> tuple[list[WaterfallComponent], list[WaterfallComponent], float, float]:
    """Frozen §5 EBITDA waterfall, monthly-then-sum, with closure proof.

    Per month t (baseline b, stressed s, all values read from the emitted
    month records — no formula recalculation):

    - ``GM_b,t = (Rev_b,t − COGS_b,t) / Rev_b,t`` (0.0 when Rev_b,t = 0)
    - revenue effect ``R_t = (Rev_s,t − Rev_b,t) · GM_b,t`` (frozen formula)
    - input-cost effect ``I_t = ΔRev_t·(COGS_b,t/Rev_b,t) − ΔCOGS_t`` — the
      COGS movement beyond revenue-scaling at baseline margin, i.e. exactly
      the commodity/FX/cogs-shock margin-rate channel in one frozen bucket
    - opex effect ``O_t = −(Opex_s,t − Opex_b,t)``
    - other/one-off ``E_t = ΔEBITDA_t − R_t − I_t − O_t`` (residual)

    Exactness: R+I+O = ΔRev·(GM + COGS/Rev) − ΔCOGS − ΔOpex = ΔEBITDA, so E
    is floating-point dust, not a hiding place. ``one_off_cost`` never
    enters EBITDA per frozen §2 (cash-flow-only at t=1): it is not forced
    into attribution and no ΔEBITDA is attributed to it.

    Below-EBITDA bridge (frozen order): interest ``−ΣΔInt``,
    tax ``−ΣΔTax``; ``ΔNI = ΔEBITDA + interest + tax`` exactly (DA is
    assumption-identical across runs).

    Returns ``(waterfall, bridge, interaction_residual, bridge_residual)``.
    """
    revenue = 0.0
    input_cost = 0.0
    opex = 0.0
    other = 0.0
    interest = 0.0
    tax = 0.0
    total_ebitda_delta = 0.0
    total_ni_delta = 0.0
    for base, stress in zip(baseline.months, stressed.months, strict=True):
        gm_base = (base.revenue - base.cogs) / base.revenue if base.revenue != 0.0 else 0.0
        cogs_rate_base = base.cogs / base.revenue if base.revenue != 0.0 else 0.0
        delta_rev = stress.revenue - base.revenue
        delta_cogs = stress.cogs - base.cogs
        delta_opex = stress.opex - base.opex
        delta_ebitda = stress.ebitda - base.ebitda
        revenue += delta_rev * gm_base
        input_cost += delta_rev * cogs_rate_base - delta_cogs
        opex += -delta_opex
        other += (
            delta_ebitda
            - (delta_rev * gm_base)
            - (delta_rev * cogs_rate_base - delta_cogs)
            + delta_opex
        )
        interest += -(stress.interest_expense - base.interest_expense)
        tax += -(stress.tax - base.tax)
        total_ebitda_delta += delta_ebitda
        total_ni_delta += stress.net_income - base.net_income
    interaction_residual = total_ebitda_delta - (revenue + input_cost + opex + other)
    bridge_residual = total_ni_delta - (total_ebitda_delta + interest + tax)
    waterfall = [
        WaterfallComponent(component="revenue_effect", delta_ebitda=revenue),
        WaterfallComponent(component="input_cost_effect", delta_ebitda=input_cost),
        WaterfallComponent(component="opex_effect", delta_ebitda=opex),
        WaterfallComponent(
            component="other_one_off",
            delta_ebitda=other,
            note=(
                "floating-point residual of the exact decomposition; "
                "one_off_cost affects cash flow only (frozen §2) and is "
                "never attributed ΔEBITDA"
            ),
        ),
    ]
    bridge = [
        WaterfallComponent(component="interest_effect", delta_ebitda=0.0, delta_ni=interest),
        WaterfallComponent(component="tax_effect", delta_ebitda=0.0, delta_ni=tax),
    ]
    return waterfall, bridge, interaction_residual, bridge_residual


def _closure_ok(total: float, residual: float) -> bool:
    """Frozen 0.5% closure with an absolute floor for the zero-delta case."""
    return abs(residual) <= max(WATERFALL_CLOSURE_REL * abs(total), 1e-9)


def resolve_min_cash_buffer(run: SimulationRunResult) -> float:
    """Frozen buffer ``B`` the run itself used (simulation.md §1: ``B``).

    Read from the run's own diagnostics so the breach threshold "cash < B"
    can never drift from the ``B`` the twin actually applied. A missing
    record is an internal error, never a silent 0.0 — a silent zero would
    turn the rule into "cash < 0" and misreport the breach.
    """
    for record in run.diagnostics.assumption_records:
        if record.parameter == "min_cash_buffer":
            value = float(record.value)
            if math.isfinite(value) and value >= 0.0:
                return value
    raise AppError(
        ErrorCode.INTERNAL_ERROR,
        "run diagnostics carry no min_cash_buffer assumption record",
        {"company_id": run.company_id},
    )


def _hash_result(payload: dict[str, Any]) -> str:
    """Decision I: SHA-256 over canonical JSON (determinism aid)."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def run_stress(
    dataset: CompanyDataset,
    validated: sc.ValidatedScenario,
    horizon_override: int | None = None,
    policy: BreachPolicy | None = None,
) -> StressTestResult:
    """Run one baseline-vs-stressed comparison through the frozen twin.

    Decision B: both runs use the same deterministic ``simulate()`` path —
    baseline with zero overrides, stressed with ``to_overrides(validated)``.
    Decision C: the scenario horizon is the execution horizon. Both runs'
    invariants must hold or the comparison is refused (a twin failure is
    never papered over).

    Blocker B2: per-dimension risk deltas are unavailable — re-scoring
    needs a full CompanyDataset (equity, total_assets, current balances…)
    that the twin never projects, and Phase 8 does not fabricate projected
    balance-sheet values. ``dimension_deltas`` is None with an explicit
    machine-readable note listing the missing projected fields.
    """
    _require_validated(validated)
    horizon = _resolve_horizon(validated, horizon_override)
    overrides = sc.to_overrides(validated)

    baseline = simulate(dataset, horizon_months=horizon)
    stressed = simulate(dataset, horizon_months=horizon, overrides=overrides)

    if not baseline.invariants_hold or not stressed.invariants_hold:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "twin invariants failed; comparison refused",
            {
                "baseline_invariants": [
                    {"name": inv.name, "holds": inv.holds} for inv in baseline.invariants
                ],
                "stressed_invariants": [
                    {"name": inv.name, "holds": inv.holds} for inv in stressed.invariants
                ],
            },
        )

    currency = str(baseline.currency)
    kpi_impacts = compare_kpis(baseline, stressed, currency=currency)
    buffer = resolve_min_cash_buffer(stressed)
    breaches = detect_breaches(stressed, buffer=buffer, policy=policy)
    waterfall, bridge, residual, bridge_residual = attribute_waterfall(baseline, stressed)

    total_ebitda_delta = sum(m.ebitda for m in stressed.months) - sum(
        m.ebitda for m in baseline.months
    )
    if not _closure_ok(total_ebitda_delta, residual):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "waterfall closure breached the frozen 0.5% tolerance",
            {"total_delta": total_ebitda_delta, "residual": residual},
        )
    total_ni_delta = sum(m.net_income for m in stressed.months) - sum(
        m.net_income for m in baseline.months
    )
    if not _closure_ok(total_ni_delta, bridge_residual):
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "below-EBITDA bridge closure breached the frozen 0.5% tolerance",
            {"total_delta": total_ni_delta, "residual": bridge_residual},
        )

    result = StressTestResult(
        scenario_name=validated.params.name,
        horizon_months=horizon,
        baseline=baseline,
        stressed=stressed,
        kpi_impacts=kpi_impacts,
        breaches=breaches,
        waterfall=waterfall,
        below_bridge=bridge,
        interaction_residual=residual,
        dimension_deltas=None,
        dimension_deltas_note={
            "status": "deferred",
            "reason": (
                "re-scoring the stressed end-state needs a full "
                "CompanyDataset, but the twin projects no balance-sheet "
                "levels; Phase 8 does not fabricate projected values"
            ),
            "missing_fields": [
                "equity",
                "total_assets",
                "current_assets",
                "current_liabilities",
                "total_liabilities",
                "st_debt",
                "lt_debt",
            ],
        },
        validated_params_hash=validated.provenance.validated_params_hash,
        causality_note=baseline.causality_note,
        advice_note=baseline.advice_note,
    )
    payload = result.model_dump(mode="json", exclude={"result_hash"})
    result.result_hash = _hash_result(payload)
    return result
