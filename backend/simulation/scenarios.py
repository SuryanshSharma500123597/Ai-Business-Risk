"""Scenario Engine — deterministic bounded scenario validation (Phase 7).

Converts human-readable scenario input (structured form parameters, a frozen
preset id, or an AI-translated candidate JSON) into a structured, bounded,
versioned, provenance-stamped scenario representation that Phase 8 can feed
to the frozen twin.

Frozen authority: docs/01_architecture/simulation.md §3 (scenario schema,
exact bounds, clamp-within-1.25x/reject rule, unknown-keys-rejected) and §4
(eight presets). This module implements that schema verbatim. Locked Phase 7
decisions A-L are recorded inline as ``Decision <letter>`` comments.

Scope boundaries (deliberate, enforced by this module's contents):
- This module validates and normalizes scenarios. It does not run the twin:
  ``run_twin``/``simulate`` are never called here (hard requirement 3).
- It does not compare runs, emit breach policy or build a waterfall
  (Phase 8, simulation.md §5).
- It performs no LLM calls: an AI translator's output arrives as a plain
  ``TranslationCandidate`` dict and is re-validated from scratch. The LLM is
  an untrusted proposer; deterministic validation is the authority.
- It does not persist (no database writes, architecture rule R1/R3) and is
  not served (no API; Phase 10). Clamp events are *returned* in-memory in
  the ``guardrail_events`` shape of database.md for later persistence.
- Guardrail logic lives here (decision L): no ``backend/guardrails/``
  package is created in Phase 7.

Documented interpretations (locked decisions D and E):
- Decision D: a positive FX shock (``fx_change_pct > 0``) means
  company-currency *depreciation* under the frozen Phase 6 equations: import
  costs rise via κ_fx and foreign demand falls via ρ_rev·e_fx.
- Decision E: scenario deltas are *persistent monthly levels* applied every
  month t = 1..H. They are not annualized and not converted into monthly
  rates; the frozen "annual %/pp" phrasing fixes units, not time-application.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.core.errors import AppError, ErrorCode
from backend.simulation.contracts import (
    DEFAULT_HORIZON_MONTHS,
    MAX_HORIZON_MONTHS,
    SimulationOverrides,
)

# Decision A: single scenario version covering schema + bounds + presets.
# Bumped on any change to the frozen §3 schema, the clamp/reject rule, or
# the frozen §4 preset values — mirroring TWIN_VERSION / REGISTRY_VERSION.
SCENARIO_VERSION = "1.0.0"

# Frozen §3 structural envelope.
MAX_NAME_LENGTH = 80
MAX_RAMP_MONTHS = 12
DEFAULT_RAMP_MONTHS = 0

# Frozen §3 clamp tolerance: within 1.25x of a bound the value is clamped
# (severity info, action clamp); beyond it the scenario is rejected.
CLAMP_TOLERANCE = 1.25

# Frozen §3 numeric bounds, per field. ``one_off_cost`` has no upper bound
# (decision K: keep unbounded — the frozen spec provides none).
FIELD_BOUNDS: dict[str, tuple[float, float | None]] = {
    "revenue_change_pct": (-50.0, 50.0),
    "cogs_change_pct": (-50.0, 50.0),
    "opex_change_pct": (-50.0, 50.0),
    "interest_rate_change_pp": (-5.0, 5.0),
    "fx_change_pct": (-50.0, 50.0),
    "commodity_price_change_pct": (-50.0, 100.0),
    "supplier_disruption_pct": (0.0, 100.0),
    "capex_change_pct": (-100.0, 100.0),
    "ar_days_change": (-30.0, 60.0),
    "one_off_cost": (0.0, None),
}

# Frozen §3 field list (shocks only; name/horizon/ramp are the envelope).
SHOCK_FIELDS: tuple[str, ...] = tuple(FIELD_BOUNDS)

# Frozen §4 presets, verbatim ("template defaults, user-editable, not
# regulator-calibrated"). Values are in schema units (*_pct / *_pp / days).
PRESET_PARAMS: dict[str, dict[str, float]] = {
    "recession": {"revenue_change_pct": -15.0, "ar_days_change": 10.0},
    "inflation": {"cogs_change_pct": 12.0, "opex_change_pct": 8.0},
    "rate_shock": {"interest_rate_change_pp": 2.0},
    "fx_shock": {"fx_change_pct": 10.0},
    "commodity_shock": {"commodity_price_change_pct": 25.0},
    "demand_collapse": {"revenue_change_pct": -30.0, "ar_days_change": 15.0},
    "supplier_disruption": {"supplier_disruption_pct": 40.0},
    "combined_stress": {
        "revenue_change_pct": -20.0,
        "cogs_change_pct": 10.0,
        "interest_rate_change_pp": 2.0,
        "commodity_price_change_pct": 15.0,
        "ar_days_change": 10.0,
    },
}

PRESET_DESCRIPTIONS: dict[str, str] = {
    "recession": "Revenue downturn with slower collections.",
    "inflation": "Input-cost and operating-cost pressure.",
    "rate_shock": "Interest-rate shock on the floating-rate debt leg.",
    "fx_shock": (
        "Company-currency depreciation: import costs rise via κ_fx and "
        "foreign demand falls via ρ_rev·e_fx (decision D)."
    ),
    "commodity_shock": "Input commodity price pressure via κ_c.",
    "demand_collapse": "Severe revenue contraction with slower collections.",
    "supplier_disruption": "Supply-capacity cut capping revenue via Capacity₀.",
    "combined_stress": "DFAST-patterned multi-factor stress.",
}


class ScenarioOrigin(StrEnum):
    """Where a scenario came from. Matches database.md ``scenarios.type``."""

    PRESET = "preset"
    FORM = "form"
    AI = "ai"


class ScenarioConfirmationStatus(StrEnum):
    """Confirmation lifecycle. Matches database.md ``scenarios.status``."""

    VALIDATED = "validated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CANCELLED = "cancelled"


class ClampEvent(BaseModel):
    """One applied clamp, in the database.md ``guardrail_events`` shape.

    Returned in-memory inside the validation result; Phase 7 writes no
    database rows (no agent run exists yet to own the FK).
    """

    model_config = ConfigDict(extra="forbid")

    # Decision J: rule naming format.
    rule: str
    severity: str = "info"
    action: str = "clamp"
    detail: dict[str, Any] = Field(default_factory=dict)


class ScenarioParams(BaseModel):
    """The frozen simulation.md §3 schema, verbatim.

    All shock fields are optional with default 0 (absent shock = no shock).
    Raw user-facing units: ``*_pct`` percent, ``*_pp`` percentage points,
    ``ar_days_change`` absolute days, ``one_off_cost`` company-currency
    amount charged at t=1. The schema carries no currency field (hard
    requirement 6): currency binds to the company at run time in Phase 8/10.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    horizon_months: int = Field(default=DEFAULT_HORIZON_MONTHS, ge=1, le=MAX_HORIZON_MONTHS)
    ramp_months: int = Field(default=DEFAULT_RAMP_MONTHS, ge=0, le=MAX_RAMP_MONTHS)
    revenue_change_pct: float = 0.0
    cogs_change_pct: float = 0.0
    opex_change_pct: float = 0.0
    interest_rate_change_pp: float = 0.0
    fx_change_pct: float = 0.0
    commodity_price_change_pct: float = 0.0
    supplier_disruption_pct: float = 0.0
    capex_change_pct: float = 0.0
    ar_days_change: float = 0.0
    one_off_cost: float = 0.0

    @field_validator(*SHOCK_FIELDS)
    @classmethod
    def _must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value

    @model_validator(mode="after")
    def _check_ramp_within_horizon(self) -> ScenarioParams:
        # Decision F: ramp_months > horizon_months is REJECTED, not clamped.
        if self.ramp_months > self.horizon_months:
            raise ValueError(
                f"ramp_months ({self.ramp_months}) exceeds horizon_months ({self.horizon_months})"
            )
        return self


class TranslationCandidate(BaseModel):
    """The deterministic receiving dock for an AI translator's output.

    Phase 7 performs no LLM calls (hard requirement 5). The translator
    (Phase 9) proposes; this model only carries the proposal plus its
    ``mapping_notes`` so deterministic validation can judge it.
    """

    model_config = ConfigDict(extra="forbid")

    candidate: dict[str, Any]
    mapping_notes: list[str] = Field(default_factory=list)
    source_text: str = ""
    model: str = ""


class ScenarioProvenance(BaseModel):
    """Provenance stamp carried on every validated scenario."""

    model_config = ConfigDict(extra="forbid")

    origin: ScenarioOrigin
    scenario_version: str = SCENARIO_VERSION
    preset_id: str | None = None
    source_text: str = ""
    model: str = ""
    # Decision I: SHA-256 over canonical JSON of the validated params —
    # provenance metadata only, never a scenario input.
    validated_params_hash: str = ""


class ValidatedScenario(BaseModel):
    """A validated, bounded scenario ready for Phase 8 consumption."""

    model_config = ConfigDict(extra="forbid")

    params: ScenarioParams
    confirmation_status: ScenarioConfirmationStatus
    origin: ScenarioOrigin
    clamped: list[str] = Field(default_factory=list)
    guardrail_events: list[ClampEvent] = Field(default_factory=list)
    mapping_notes: list[str] = Field(default_factory=list)
    provenance: ScenarioProvenance


def _clamp_limit(bound: float | None, *, upper: bool) -> float | None:
    """Outer edge of the frozen clamp band for one bound."""
    if bound is None:
        return None
    if bound == 0.0:
        # 1.25x of a zero bound is still zero: any nonzero breach rejects.
        return 0.0
    if upper:
        return bound * CLAMP_TOLERANCE if bound > 0.0 else bound / CLAMP_TOLERANCE
    return bound * CLAMP_TOLERANCE if bound < 0.0 else bound / CLAMP_TOLERANCE


def _clamp_field(field: str, value: float) -> tuple[float, ClampEvent | None]:
    """Apply the frozen clamp/reject rule to one shock value."""
    lower, upper = FIELD_BOUNDS[field]
    if lower is not None and value < lower:
        limit = _clamp_limit(lower, upper=False)
        assert limit is not None
        if value >= limit:
            event = ClampEvent(
                rule=f"scenario_bounds.{field}",
                detail={"field": field, "observed": value, "bound": lower, "applied": lower},
            )
            return lower, event
        raise AppError(
            ErrorCode.SCENARIO_OUT_OF_BOUNDS,
            f"scenario field '{field}' below allowed range",
            {"field": field, "observed": value, "bound": lower},
        )
    if upper is not None and value > upper:
        limit = _clamp_limit(upper, upper=True)
        assert limit is not None
        if value <= limit:
            event = ClampEvent(
                rule=f"scenario_bounds.{field}",
                detail={"field": field, "observed": value, "bound": upper, "applied": upper},
            )
            return upper, event
        raise AppError(
            ErrorCode.SCENARIO_OUT_OF_BOUNDS,
            f"scenario field '{field}' above allowed range",
            {"field": field, "observed": value, "bound": upper},
        )
    return value, None


def _apply_bounds(raw: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[ClampEvent]]:
    """Apply the frozen clamp-within-1.25x/reject rule to raw shock values."""
    applied: dict[str, Any] = dict(raw)
    clamped: list[str] = []
    events: list[ClampEvent] = []
    for field in SHOCK_FIELDS:
        if field not in applied:
            continue
        value_in = applied[field]
        if isinstance(value_in, bool) or not isinstance(value_in, (int, float)):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"scenario field '{field}' must be a number",
                {"field": field, "observed": value_in},
            )
        value = float(value_in)
        if not math.isfinite(value):
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"scenario field '{field}' must be finite",
                {"field": field, "observed": value_in},
            )
        applied_value, event = _clamp_field(field, value)
        applied[field] = applied_value
        if event is not None:
            clamped.append(field)
            events.append(event)
    return applied, clamped, events


def _hash_params(params: ScenarioParams) -> str:
    """Decision I: SHA-256 over canonical JSON of the validated params."""
    canonical = json.dumps(params.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_params(
    raw: dict[str, Any],
    *,
    origin: ScenarioOrigin,
    mapping_notes: list[str] | None = None,
    source_text: str = "",
    model: str = "",
    preset_id: str | None = None,
) -> ValidatedScenario:
    """Validate raw scenario input into a bounded ``ValidatedScenario``.

    Unknown keys are rejected by ``ScenarioParams`` (``extra="forbid"``);
    the frozen clamp/reject rule applies to shock values; the
    ramp-vs-horizon invariant (decision F) is enforced by the model.
    Confirmation routing follows FD-3: ``ai`` origin requires explicit
    confirmation, ``form``/``preset`` validate directly.
    """
    if not isinstance(raw, dict):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "scenario must be a mapping of schema fields",
            {"observed_type": type(raw).__name__},
        )
    values, clamped, events = _apply_bounds(raw)
    try:
        params = ScenarioParams(**values)
    except ValueError as exc:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"scenario schema violation: {exc}",
            {"detail": str(exc)},
        ) from exc
    if origin is ScenarioOrigin.AI:
        status = ScenarioConfirmationStatus.AWAITING_CONFIRMATION
    else:
        status = ScenarioConfirmationStatus.VALIDATED
    provenance = ScenarioProvenance(
        origin=origin,
        preset_id=preset_id,
        source_text=source_text,
        model=model,
        validated_params_hash=_hash_params(params),
    )
    return ValidatedScenario(
        params=params,
        confirmation_status=status,
        origin=origin,
        clamped=clamped,
        guardrail_events=events,
        mapping_notes=list(mapping_notes or []),
        provenance=provenance,
    )


def validate_candidate(candidate: TranslationCandidate) -> ValidatedScenario:
    """Validate an AI translator's candidate JSON from scratch.

    The translator is untrusted: a valid-looking value outside bounds is
    still clamped or rejected deterministically, and mapping notes are
    carried through for the human confirmation step, never trusted.
    """
    return validate_params(
        candidate.candidate,
        origin=ScenarioOrigin.AI,
        mapping_notes=candidate.mapping_notes,
        source_text=candidate.source_text,
        model=candidate.model,
    )


def get_preset(preset_id: str) -> ValidatedScenario:
    """Expand a frozen §4 preset into a validated scenario.

    Decision G: preset application defaults are ``name = preset_id``,
    ``horizon_months = 12``, ``ramp_months = 0``.
    """
    if preset_id not in PRESET_PARAMS:
        raise AppError(
            ErrorCode.NOT_FOUND,
            f"unknown scenario preset '{preset_id}'",
            {"preset_id": preset_id, "known": sorted(PRESET_PARAMS)},
        )
    raw: dict[str, Any] = {
        "name": preset_id,
        "horizon_months": DEFAULT_HORIZON_MONTHS,
        "ramp_months": DEFAULT_RAMP_MONTHS,
    }
    raw.update(PRESET_PARAMS[preset_id])
    return validate_params(raw, origin=ScenarioOrigin.PRESET, preset_id=preset_id)


def list_presets() -> list[dict[str, Any]]:
    """List the frozen preset library (backing data for the future tool)."""
    return [
        {
            "preset_id": preset_id,
            "name": preset_id,
            "params": dict(PRESET_PARAMS[preset_id]),
            "description": PRESET_DESCRIPTIONS[preset_id],
            "scenario_version": SCENARIO_VERSION,
        }
        for preset_id in sorted(PRESET_PARAMS)
    ]


def confirm(scenario: ValidatedScenario) -> ValidatedScenario:
    """Confirm an ``awaiting_confirmation`` scenario (FD-3 human step).

    Decision H: confirmation re-validates deterministically — bounds or the
    scenario version could have changed since translation, so the stored
    params pass through validation again before the status flips.
    """
    if scenario.confirmation_status is not ScenarioConfirmationStatus.AWAITING_CONFIRMATION:
        raise AppError(
            ErrorCode.RUN_STATE_INVALID,
            "only scenarios awaiting confirmation can be confirmed",
            {"status": scenario.confirmation_status.value},
        )
    refreshed = validate_params(
        scenario.params.model_dump(mode="json"),
        origin=scenario.origin,
        mapping_notes=scenario.mapping_notes,
        source_text=scenario.provenance.source_text,
        model=scenario.provenance.model,
        preset_id=scenario.provenance.preset_id,
    )
    refreshed.confirmation_status = ScenarioConfirmationStatus.VALIDATED
    return refreshed


def cancel(scenario: ValidatedScenario) -> ValidatedScenario:
    """Cancel a scenario awaiting confirmation (the frozen ``cancelled`` end)."""
    if scenario.confirmation_status is not ScenarioConfirmationStatus.AWAITING_CONFIRMATION:
        raise AppError(
            ErrorCode.RUN_STATE_INVALID,
            "only scenarios awaiting confirmation can be cancelled",
            {"status": scenario.confirmation_status.value},
        )
    scenario.confirmation_status = ScenarioConfirmationStatus.CANCELLED
    return scenario


def to_overrides(validated: ValidatedScenario) -> SimulationOverrides:
    """Normalize a validated scenario to frozen twin fractions (D-6).

    ``*_pct`` values are divided by 100; ``*_pp`` values are divided by 100
    (2.0pp == 0.02 rate fraction); ``ar_days_change`` and ``one_off_cost``
    pass through unchanged. Only ``VALIDATED`` scenarios convert — confirming
    first is mandatory for AI-translated input.
    """
    if validated.confirmation_status is not ScenarioConfirmationStatus.VALIDATED:
        raise AppError(
            ErrorCode.SCENARIO_PENDING_CONFIRM,
            "scenario must be confirmed before conversion to twin overrides",
            {"status": validated.confirmation_status.value},
        )
    params = validated.params
    return SimulationOverrides(
        ramp_months=params.ramp_months,
        revenue_change=params.revenue_change_pct / 100.0,
        cogs_change=params.cogs_change_pct / 100.0,
        opex_change=params.opex_change_pct / 100.0,
        rate_change=params.interest_rate_change_pp / 100.0,
        fx_change=params.fx_change_pct / 100.0,
        commodity_change=params.commodity_price_change_pct / 100.0,
        supplier_disruption=params.supplier_disruption_pct / 100.0,
        capex_change=params.capex_change_pct / 100.0,
        ar_days_change=params.ar_days_change,
        one_off_cost=params.one_off_cost,
    )


def normalize_basis_points(basis_points: float, *, note: str = "") -> float:
    """Decision B: normalize an explicit basis-point quote to pp.

    ``200`` → ``2.0``. Only for *explicit* basis-point expressions; an
    ambiguous bare percent (decision C) must never reach this function —
    it stays unconfirmed/invalid instead. The caller records the conversion
    in ``mapping_notes``.
    """
    if isinstance(basis_points, bool) or not isinstance(basis_points, (int, float)):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "basis-point value must be a number",
            {"observed": basis_points},
        )
    value = float(basis_points)
    if not math.isfinite(value):
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "basis-point value must be finite",
            {"observed": basis_points},
        )
    _ = note
    return value / 100.0
