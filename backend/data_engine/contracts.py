"""Canonical data contracts (frozen field names: docs/01_architecture/data.md §1).

One source of truth for the wide `financials` shape used by the risk engine,
simulation, and API. The ORM models in backend/database/models.py mirror these
names; duplicate data models are not permitted.
"""

from __future__ import annotations

import hashlib
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Sector(StrEnum):
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    SERVICES_SAAS = "services_saas"


class CompanySize(StrEnum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    STABLE = "stable"
    STRESSED = "stressed"


class ConcentrationProfile(StrEnum):
    DISPERSED = "dispersed"
    MODERATE = "moderate"
    CONCENTRATED = "concentrated"


class AnomalyType(StrEnum):
    MARGIN_COLLAPSE = "margin_collapse"
    RECEIVABLE_SPIKE = "receivable_spike"
    COST_EXPLOSION = "cost_explosion"


class Frequency(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class DataOrigin(StrEnum):
    SYNTHETIC = "synthetic"
    MANUAL = "manual"
    EDGAR = "edgar"


AllowedCurrency = Literal["INR", "USD", "EUR"]

# --- Frozen validation constants (data.md §3) ---

REQUIRED_CONCEPTS: tuple[str, ...] = (
    "revenue",
    "cogs",
    "cash",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "equity",
    "interest_expense",
)

OPTIONAL_CONCEPTS: tuple[str, ...] = (
    "gross_profit",
    "opex",
    "ebitda",
    "da",
    "ebit",
    "net_income",
    "receivables",
    "inventory",
    "payables",
    "total_debt",
    "st_debt",
    "lt_debt",
    "capex",
    "ocf",
    "fcf",
    "dividends",
    "customers",
    "suppliers",
    "products",
    "regions",
    "fx_exposure",
    "commodity_exposure",
    "rate_exposure",
    "debt_schedule",
)

COVERAGE_GATE_PCT = 70.0  # below this the run is blocked (DATA_COVERAGE_LOW)
IDENTITY_TOLERANCE = 0.005  # 0.5% relative tolerance for accounting identities
SHARE_SUM_TOLERANCE = 0.01  # concentration shares must sum to 1 ± 0.01
MIN_PERIODS_FOR_ML = 8

NUMERIC_CONCEPT_FIELDS: tuple[str, ...] = (
    # income statement
    "revenue",
    "cogs",
    "gross_profit",
    "opex",
    "ebitda",
    "da",
    "ebit",
    "interest_expense",
    "tax",
    "net_income",
    # balance sheet
    "cash",
    "receivables",
    "inventory",
    "payables",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "equity",
    "total_debt",
    "st_debt",
    "lt_debt",
    # cash flow
    "capex",
    "ocf",
    "fcf",
    "dividends",
)


def hash_name(name: str) -> str:
    """Stable privacy hash for customer/supplier names (data.md §1)."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]


class ShareEntry(BaseModel):
    """One concentration entry. Customers/suppliers use name_hash; products/
    regions keep plain names (frozen data.md §1)."""

    model_config = ConfigDict(extra="forbid")

    name_hash: str | None = None
    name: str | None = None
    share: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_label(self) -> ShareEntry:
        if not (self.name_hash or self.name):
            raise ValueError("ShareEntry requires name_hash or name")
        if self.name_hash and self.name:
            raise ValueError("ShareEntry cannot carry both name_hash and name")
        return self


class FxExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    foreign_revenue_share: float = Field(default=0.0, ge=0.0, le=1.0)
    import_cost_share: float = Field(default=0.0, ge=0.0, le=1.0)


class CommodityExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    cost_share: float = Field(ge=0.0, le=1.0)


class RateExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floating_debt_share: float = Field(default=0.5, ge=0.0, le=1.0)


class DebtScheduleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: Literal["0-3m", "3-12m", "1-3y", "3y+"]
    amount: float = Field(ge=0.0)


class PeriodFinancials(BaseModel):
    """One period of the canonical wide schema (data.md §1)."""

    model_config = ConfigDict(extra="forbid")

    period_start: date
    period_end: date
    fiscal_year: int | None = None
    quarter: int | None = None
    frequency: Frequency
    source: str

    # income statement
    revenue: float | None = None
    cogs: float | None = None
    gross_profit: float | None = None
    opex: float | None = None
    ebitda: float | None = None
    da: float | None = None
    ebit: float | None = None
    interest_expense: float | None = None
    tax: float | None = None
    net_income: float | None = None
    # balance sheet
    cash: float | None = None
    receivables: float | None = None
    inventory: float | None = None
    payables: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    equity: float | None = None
    total_debt: float | None = None
    st_debt: float | None = None
    lt_debt: float | None = None
    # cash flow
    capex: float | None = None
    ocf: float | None = None
    fcf: float | None = None
    dividends: float | None = None
    # concentration buckets
    customers: list[ShareEntry] | None = None
    suppliers: list[ShareEntry] | None = None
    products: list[ShareEntry] | None = None
    regions: list[ShareEntry] | None = None
    # exposures
    fx_exposure: FxExposure | None = None
    commodity_exposure: CommodityExposure | None = None
    rate_exposure: RateExposure | None = None
    debt_schedule: list[DebtScheduleEntry] | None = None


class CompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    sector: Sector
    currency: AllowedCurrency = "INR"
    data_origin: DataOrigin = DataOrigin.SYNTHETIC
    description: str | None = None


class AnomalyInjection(BaseModel):
    """Labeled anomaly for ML evaluation (data.md §4)."""

    model_config = ConfigDict(extra="forbid")

    type: AnomalyType
    start_month: int = Field(ge=1)
    duration_months: int = Field(ge=1, le=36)
    magnitude: float = Field(gt=0.0)


class SyntheticCompanyConfig(BaseModel):
    """Generator parameters (frozen data.md §4 table)."""

    model_config = ConfigDict(extra="forbid")

    sector: Sector = Sector.MANUFACTURING
    size: CompanySize = CompanySize.MEDIUM
    health: HealthStatus = HealthStatus.STABLE
    currency: AllowedCurrency = "INR"
    periods: int = Field(default=24, ge=3, le=36)
    frequency: Frequency = Frequency.MONTHLY
    growth_drift_monthly_pct: float = Field(default=0.5, ge=-3.0, le=3.0)
    seasonality: bool | None = None  # None => sector default (retail: on)
    concentration: ConcentrationProfile = ConcentrationProfile.MODERATE
    inject_anomalies: list[AnomalyInjection] = Field(default_factory=list)
    seed: int

    @model_validator(mode="after")
    def _resolve_defaults(self) -> SyntheticCompanyConfig:
        # Frozen data.md §4: "12–36 monthly or 3–10 annual" — for annual
        # frequency `periods` counts YEARS; months = periods × 12.
        if self.frequency == Frequency.ANNUAL and not (3 <= self.periods <= 10):
            raise ValueError("annual frequency requires 3..10 periods (years)")
        if self.frequency == Frequency.MONTHLY and not (12 <= self.periods <= 36):
            raise ValueError("monthly frequency requires 12..36 periods")
        return self

    @property
    def effective_seasonality(self) -> bool:
        if self.seasonality is not None:
            return self.seasonality
        return self.sector == Sector.RETAIL


class GeneratedCompany(BaseModel):
    """Generator output: profile + ordered periods."""

    profile: CompanyProfile
    periods: list[PeriodFinancials]
    generator_config: SyntheticCompanyConfig

    @property
    def anomaly_labels(self) -> list[AnomalyInjection]:
        return self.generator_config.inject_anomalies


class CoverageIssue(BaseModel):
    concept: str
    detail: str


class ValidationReport(BaseModel):
    """Result of the frozen validation rules (data.md §3)."""

    required_pct: float = Field(ge=0.0, le=100.0)
    optional_pct: float = Field(ge=0.0, le=100.0)
    missing_required: list[CoverageIssue] = Field(default_factory=list)
    missing_optional: list[CoverageIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blocked: bool = False

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "required_pct": self.required_pct,
            "optional_pct": self.optional_pct,
            "missing_required": [i.concept for i in self.missing_required],
            "warnings": self.warnings,
            "blocked": self.blocked,
        }
