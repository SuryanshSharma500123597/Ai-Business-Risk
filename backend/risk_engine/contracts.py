"""Risk Engine Data Contracts.

Typed, immutable Pydantic contracts for quantitative metric outputs,
dimension scores, composite aggregation, additive contributions, and sensitivity analysis.
"""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Single source of truth for the formula-registry version. Every formula output
# stamps this value (requirements.md FR2) and it bumps on any formula/band change
# (risk-engine.md §1). ``registry`` re-exports it for backwards compatibility.
REGISTRY_VERSION = "1.0.0"

# Stage 5 frozen minimums (approved Stage 5 design; metric formulas unchanged).
MIN_BETA_ALIGNED_OBS = 120  # risk-engine.md §4: beta min 120 obs, 252d window target
MIN_VAR_ES_OBS = 60  # calc_var_95 / calc_es_95 listed-mode floor
MIN_VOL_OBS = 30  # equity/FX volatility floor (Q-M1: keep 30, do not raise to 60)
MIN_CPI_MONTHS = 24  # inflation_passthrough 24-month window (Q-C2 strict)
MIN_FEDFUNDS_MONTHS = 60  # rate_environment trailing 5-year median (Q-C2 strict)


class MetricStatus(StrEnum):
    VALID = "valid"
    MISSING_INPUT = "missing_input"
    INVALID_INPUT = "invalid_input"
    UNAVAILABLE = "unavailable"
    FLAGGED = "flagged"
    INSUFFICIENT_HISTORY = "insufficient_history"


class SeverityLabel(StrEnum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"
    CRITICAL = "Critical"


def get_severity_label(score: float | None) -> SeverityLabel | None:
    """Classify 0-100 risk score into standard severity bands.

    0 <= score < 25: Low
    25 <= score < 50: Moderate
    50 <= score < 75: High
    75 <= score <= 100: Critical
    """
    if score is None or not math.isfinite(score):
        return None
    clamped = max(0.0, min(100.0, score))
    if clamped < 25.0:
        return SeverityLabel.LOW
    if clamped < 50.0:
        return SeverityLabel.MODERATE
    if clamped < 75.0:
        return SeverityLabel.HIGH
    return SeverityLabel.CRITICAL


class MetricResult(BaseModel):
    """Result of calculating and scoring a single quantitative metric."""

    model_config = ConfigDict(extra="forbid")

    metric_id: str
    name: str
    dimension: str
    value: float | None = None
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    severity: SeverityLabel | None = None
    status: MetricStatus = MetricStatus.VALID
    message: str | None = None
    unit: str = ""
    weight_in_dimension: float = Field(default=0.0, ge=0.0, le=1.0)
    contribution_to_dimension: float = 0.0
    contribution_to_composite: float = 0.0
    inputs_used: dict[str, Any] = Field(default_factory=dict)
    registry_version: str = REGISTRY_VERSION
    # Frozen edge-case outcome (risk-engine.md §2-§8 "Edge cases" column), e.g.
    # "revenue=0 -> 100" or "CL=0 -> score 5". Applied verbatim by ``score_metric``
    # instead of interpolating ``value``, so zero-denominator cases never emit
    # non-finite values and always hit the frozen target score.
    forced_score: float | None = Field(default=None, ge=0.0, le=100.0)

    @field_validator("value", "score", "forced_score", mode="after")
    @classmethod
    def _finite_floats(cls, val: object) -> object:
        if isinstance(val, float) and not math.isfinite(val):
            raise ValueError("metric float values must be finite")
        return val


class DimensionResult(BaseModel):
    """Aggregated risk score and exact contributions for one risk dimension."""

    model_config = ConfigDict(extra="forbid")

    dimension_id: str
    name: str
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    severity: SeverityLabel | None = None
    weight: float = Field(ge=0.0, le=1.0)
    effective_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    contribution: float = 0.0
    metrics: list[MetricResult] = Field(default_factory=list)
    available_count: int = 0
    total_count: int = 0
    registry_version: str = REGISTRY_VERSION


class CompositeResult(BaseModel):
    """Composite risk assessment combining all available dimensions."""

    model_config = ConfigDict(extra="forbid")

    score: float | None = Field(default=None, ge=0.0, le=100.0)
    severity: SeverityLabel | None = None
    registry_version: str
    dimensions: dict[str, DimensionResult]
    total_contributions: float = 0.0
    missing_dimensions: list[str] = Field(default_factory=list)


class SensitivityScenario(BaseModel):
    """Single weight perturbation scenario in sensitivity analysis."""

    model_config = ConfigDict(extra="forbid")

    perturbed_dimension: str
    direction: float  # e.g., +0.2 or -0.2
    weights: dict[str, float]
    composite_score: float = Field(ge=0.0, le=100.0)
    dimension_ranks: list[str]  # ordered dimension IDs highest risk to lowest


class SensitivityResult(BaseModel):
    """Results of weight sensitivity analysis across dimensions."""

    model_config = ConfigDict(extra="forbid")

    baseline_score: float | None = Field(default=None, ge=0.0, le=100.0)
    min_score: float | None = Field(default=None, ge=0.0, le=100.0)
    max_score: float | None = Field(default=None, ge=0.0, le=100.0)
    score_range: float = Field(default=0.0, ge=0.0)
    scenarios: list[SensitivityScenario] = Field(default_factory=list)
    rank_stability_score: float = Field(ge=-1.0, le=1.0)  # Spearman correlation average vs baseline


class AlignedSeries(BaseModel):
    """One aligned daily-return leg for Stage 5 market inputs (approved Q-A1/Q-B2).

    Returns are decimal daily log returns (``r = ln(P_t / P_{t-1})``), computed by
    the deterministic Phase 3 -> Phase 4 adapter — never by the caller inline.
    """

    model_config = ConfigDict(extra="forbid")

    dates: list[date] = Field(default_factory=list)
    returns: list[float] = Field(default_factory=list)
    symbol_or_series_id: str = ""
    source: str = ""
    as_of: date | None = None
    currency: str | None = None

    @field_validator("returns", mode="after")
    @classmethod
    def _finite_returns(cls, values: list[float]) -> list[float]:
        for value in values:
            if not math.isfinite(value):
                raise ValueError("aligned series returns must be finite")
        return values


class SeriesProvenance(BaseModel):
    """Source provenance carried alongside one Stage 5 input leg."""

    model_config = ConfigDict(extra="forbid")

    symbol_or_series_id: str = ""
    source: str = ""
    as_of: date | None = None
    observation_count: int = Field(default=0, ge=0)
    checksum: str | None = None
    license_tag: str | None = None


class RiskEngineMarketInputs(BaseModel):
    """Typed Stage 5 market/macro inputs (approved Q-A1).

    Every field is optional so private/offline companies simply leave listed-only
    legs empty and receive the existing UNAVAILABLE / MISSING_INPUT statuses.
    Scalar macro fields are pre-aggregated by the deterministic adapter; the risk
    engine never fetches HTTP, cache, or SQL (architecture R3).
    """

    model_config = ConfigDict(extra="forbid")

    equity_returns: AlignedSeries | None = None
    benchmark_returns: AlignedSeries | None = None
    fx_returns: AlignedSeries | None = None
    cpi_change_pct_24m: float | None = None
    gross_margin_change_pp_24m: float | None = None
    fedfunds_current: float | None = None
    fedfunds_trailing_5y_median: float | None = None
    gdp_volatility: float | None = None
    provenance: dict[str, SeriesProvenance] = Field(default_factory=dict)

    @field_validator(
        "cpi_change_pct_24m",
        "gross_margin_change_pp_24m",
        "fedfunds_current",
        "fedfunds_trailing_5y_median",
        "gdp_volatility",
        mode="after",
    )
    @classmethod
    def _finite_scalars(cls, val: object) -> object:
        if isinstance(val, float) and not math.isfinite(val):
            raise ValueError("market-input scalars must be finite")
        return val


class WeightsRef(BaseModel):
    """Contract preparation for Phase 10 weight persistence (approved Q-W1).

    Carried/passthrough only — Stage 5 performs no database writes and the risk
    engine stays database-independent. Phase 10 owns repositories/services/API.
    """

    model_config = ConfigDict(extra="forbid")

    weights_id: str | None = None
    version: str | None = None
    weights: dict[str, float] = Field(default_factory=dict)

    @field_validator("weights", mode="after")
    @classmethod
    def _weights_sum_to_one(cls, weights: dict[str, float]) -> dict[str, float]:
        if weights and not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError("weights must sum to 1")
        return weights


class RiskAssessmentReport(BaseModel):
    """Top-level report containing comprehensive quantitative risk evaluation."""

    model_config = ConfigDict(extra="forbid")

    company_id: str | None = None
    company_name: str | None = None
    as_of_date: str
    registry_version: str
    composite: CompositeResult
    sensitivity: SensitivityResult
    metrics: list[MetricResult]
