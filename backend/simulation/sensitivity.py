"""Single-factor sensitivity sweeps through the frozen twin (Phase 8).

Frozen authority: docs/01_architecture/simulation.md §6.3 — "Monotonicity
sweeps: single-factor sweeps (delta_rev -50% -> +50%) move trough cash and
EBITDA monotonically in the expected direction." The frozen invariant is
stated *from the baseline twin*, so a sweep here is one-factor-at-a-time
(OFAT) from the zero-shock world: exactly one shock field is non-zero per
point, every other shock field is held at 0, and the reference run is the
same zero-override ``simulate()`` baseline that ``stress.run_stress`` uses.
Combined shocks are measured by ``run_stress`` (its waterfall), not here.

Each point re-runs the identical deterministic ``simulate()`` path (locked
decision G: 9 evenly spaced inclusive-endpoint grid points over the frozen
§3 bounds, plus the zero-shock baseline point) — no analytic derivatives,
no stochastic paths, no combinatorial grids, no LLM, no I/O, no database
(architecture rules R1/R3).

Scope boundary (locked decision G, and the recorded finding D-6-3): this
module *reports* the response curve. It does not assert monotonicity —
frozen §6.3 monotonicity is contradicted by the twin on trough cash (a
revenue contraction can raise trough cash by releasing working capital),
which is pinned as a finding rather than papered over. Tests therefore
assert determinism, ordering, endpoint inclusion and recomputation, never
a direction of travel.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import CompanyDataset
from backend.simulation import scenarios as sc
from backend.simulation.contracts import SimulationRunResult
from backend.simulation.stress import (
    STRESS_VERSION,
    Breach,
    KPIImpact,
    compare_kpis,
    detect_breaches,
    resolve_min_cash_buffer,
)
from backend.simulation.twin import simulate

# Sweepable fields: the nine bounded shock fields. Excludes one_off_cost
# (unbounded — no grid endpoints exist, decision K of Phase 7), and the
# envelope fields horizon_months/ramp_months/name (not shocks).
SWEEPABLE_FIELDS: tuple[str, ...] = (
    "revenue_change_pct",
    "cogs_change_pct",
    "opex_change_pct",
    "interest_rate_change_pp",
    "fx_change_pct",
    "commodity_price_change_pct",
    "supplier_disruption_pct",
    "capex_change_pct",
    "ar_days_change",
)

# Locked decision G: 9 grid points, inclusive of both frozen §3 bounds.
SWEEP_POINTS = 9

# Run-count cap: at most 9 grid runs + the baseline run per call.
MAX_SWEEP_RUNS = 10

# The sweep's documented reference point (frozen §6.3 reads from baseline).
SENSITIVITY_REFERENCE = "zero_shock_baseline"


class SensitivityPoint(BaseModel):
    """One grid point: field value, KPI deltas, breached rule names."""

    model_config = ConfigDict(extra="forbid")

    value: float
    is_baseline_point: bool = False
    kpi_impacts: list[KPIImpact] = Field(default_factory=list)
    breaches: list[str] = Field(default_factory=list)


class SensitivityResult(BaseModel):
    """Deterministic single-factor sweep result, ascending by field value."""

    model_config = ConfigDict(extra="forbid")

    field: str
    scenario_name: str = ""
    horizon_months: int = 0
    reference: str = SENSITIVITY_REFERENCE
    points: list[SensitivityPoint] = Field(default_factory=list)
    breach_onset: dict[str, float] = Field(default_factory=dict)
    stress_version: str = STRESS_VERSION
    scenario_version: str = sc.SCENARIO_VERSION
    validated_params_hash: str = ""


def _sweep_grid(field: str, points: int) -> list[float]:
    """Evenly spaced inclusive-endpoint grid over the frozen §3 bounds."""
    lower, upper = sc.FIELD_BOUNDS[field]
    if upper is None:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"field '{field}' has no upper bound; it cannot be swept",
            {"field": field, "lower": lower},
        )
    if points < 2:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "a sweep needs at least 2 grid points",
            {"field": field, "points": points},
        )
    if points > MAX_SWEEP_RUNS:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"a sweep is capped at {MAX_SWEEP_RUNS} runs per call",
            {"field": field, "points": points},
        )
    return [lower + (upper - lower) * index / (points - 1) for index in range(points)]


def _sweep_raw(validated: sc.ValidatedScenario, field: str, value: float) -> dict[str, Any]:
    """A flat scenario envelope carrying exactly one non-zero shock field."""
    return {
        "name": validated.params.name,
        "horizon_months": validated.params.horizon_months,
        "ramp_months": validated.params.ramp_months,
        field: value,
    }


def _validated_point(
    validated: sc.ValidatedScenario, field: str, value: float
) -> sc.ValidatedScenario:
    """Validate one sweep point through the Phase 7 gate (same bounds rule).

    AI-origin scenarios re-enter the confirmation gate for every point, so
    a sweep can never execute a scenario shape the Phase 7 gate would have
    held back (frozen FD-3).
    """
    point = sc.validate_params(
        _sweep_raw(validated, field, value),
        origin=validated.origin,
        mapping_notes=[
            f"sensitivity sweep reference={SENSITIVITY_REFERENCE}",
            f"{field} = {value}",
        ],
        source_text=validated.provenance.source_text,
        model=validated.provenance.model,
        preset_id=validated.provenance.preset_id,
    )
    if point.confirmation_status is sc.ScenarioConfirmationStatus.AWAITING_CONFIRMATION:
        point = sc.confirm(point)
    return point


def _breached_rules(breaches: list[Breach]) -> list[str]:
    """Breached rule names in frozen BREACH_ORDER (locked decision F).

    ``unevaluable`` rules are never reported as breaches; the Phase 8
    current-ratio proxy blocker (B1) stays visible in ``run_stress`` output.
    """
    return [breach.rule for breach in breaches if breach.status == "breached"]


def sweep_single_factor(
    dataset: CompanyDataset,
    validated: sc.ValidatedScenario,
    field: str,
    *,
    points: int = SWEEP_POINTS,
) -> SensitivityResult:
    """Sweep one shock field over its frozen bounds from the zero-shock base.

    The baseline point (field = 0) is always present — it is added to the
    grid when the grid does not already contain it — and flagged, so the
    reference sits inside every result. Each point reports KPI impacts
    versus the same zero-override baseline ``run_stress`` uses, plus the
    names of the breached live rules in frozen order, and
    ``breach_onset`` maps each breached rule to the lowest swept value at
    which it started breaching.

    Both the baseline run and every point run must satisfy the twin's own
    invariants; a failure refuses the sweep instead of reporting curve
    points from a broken run.
    """
    if validated.confirmation_status is not sc.ScenarioConfirmationStatus.VALIDATED:
        raise AppError(
            ErrorCode.SCENARIO_PENDING_CONFIRM,
            "scenario must be validated before a sensitivity sweep",
            {"status": validated.confirmation_status.value},
        )
    if field not in SWEEPABLE_FIELDS:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"field '{field}' is not sweepable",
            {"field": field, "sweepable": list(SWEEPABLE_FIELDS)},
        )

    horizon = validated.params.horizon_months
    values = sorted(set(_sweep_grid(field, points)) | {0.0})

    baseline_run = simulate(dataset, horizon_months=horizon)
    if not baseline_run.invariants_hold:
        raise AppError(
            ErrorCode.INTERNAL_ERROR,
            "twin invariants failed on the sweep baseline; sweep refused",
            {"field": field, "horizon_months": horizon},
        )
    currency = str(baseline_run.currency)
    buffer = resolve_min_cash_buffer(baseline_run)

    results: list[SensitivityPoint] = []
    for value in values:
        point_scenario = _validated_point(validated, field, value)
        run: SimulationRunResult = simulate(
            dataset,
            horizon_months=horizon,
            overrides=sc.to_overrides(point_scenario),
        )
        if not run.invariants_hold:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "twin invariants failed on a sweep point; sweep refused",
                {"field": field, "value": value},
            )
        results.append(
            SensitivityPoint(
                value=value,
                is_baseline_point=value == 0.0,
                kpi_impacts=compare_kpis(baseline_run, run, currency=currency),
                breaches=_breached_rules(detect_breaches(run, buffer=buffer)),
            )
        )

    onset: dict[str, float] = {}
    for point in results:  # ascending by value, so the first hit is the onset
        for rule in point.breaches:
            onset.setdefault(rule, point.value)

    return SensitivityResult(
        field=field,
        scenario_name=validated.params.name,
        horizon_months=horizon,
        points=results,
        breach_onset=onset,
        validated_params_hash=validated.provenance.validated_params_hash,
    )
