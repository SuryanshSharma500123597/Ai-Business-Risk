"""Canonical data contracts (frozen field names: docs/01_architecture/data.md §1).

One source of truth for the wide `financials` shape used by the risk engine,
simulation, and API. The ORM models in backend/database/models.py mirror these
names; duplicate data models are not permitted.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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

    @field_validator("share", mode="after")
    @classmethod
    def _finite_share(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("share must be finite")
        return value

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

    @field_validator("foreign_revenue_share", "import_cost_share", mode="after")
    @classmethod
    def _finite_share(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("exposure share must be finite")
        return value


class CommodityExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: str
    cost_share: float = Field(ge=0.0, le=1.0)

    @field_validator("cost_share", mode="after")
    @classmethod
    def _finite_share(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("cost share must be finite")
        return value


class RateExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floating_debt_share: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("floating_debt_share", mode="after")
    @classmethod
    def _finite_share(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("floating debt share must be finite")
        return value


class DebtScheduleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: Literal["0-3m", "3-12m", "1-3y", "3y+"]
    amount: float = Field(ge=0.0)

    @field_validator("amount", mode="after")
    @classmethod
    def _finite_amount(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("debt amount must be finite")
        return value


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

    @field_validator(*NUMERIC_CONCEPT_FIELDS, mode="after")
    @classmethod
    def _finite_numeric(cls, value: object) -> object:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("numeric financial values must be finite")
        return value

    @model_validator(mode="after")
    def _valid_period_calendar_fields(self) -> PeriodFinancials:
        # Ordering is evaluated at dataset level so malformed source rows can
        # be loaded and reported together rather than failing one row early.
        if self.quarter is not None and self.quarter not in (1, 2, 3, 4):
            raise ValueError("quarter must be between 1 and 4")
        if self.frequency is Frequency.ANNUAL and self.quarter is not None:
            raise ValueError("annual periods must not have a quarter")
        return self


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
    seed: int = Field(ge=0)

    @model_validator(mode="after")
    def _resolve_defaults(self) -> SyntheticCompanyConfig:
        # Frozen data.md §4: "12–36 monthly or 3–10 annual" — for annual
        # frequency `periods` counts YEARS; months = periods × 12.
        if self.frequency == Frequency.ANNUAL and not (3 <= self.periods <= 10):
            raise ValueError("annual frequency requires 3..10 periods (years)")
        if self.frequency == Frequency.MONTHLY and not (12 <= self.periods <= 36):
            raise ValueError("monthly frequency requires 12..36 periods")
        if self.frequency is Frequency.QUARTERLY:
            raise ValueError("quarterly synthetic generation is not supported")
        horizon_months = self.periods * (12 if self.frequency is Frequency.ANNUAL else 1)
        for injection in self.inject_anomalies:
            if injection.start_month + injection.duration_months - 1 > horizon_months:
                raise ValueError("anomaly window must fit within the configured periods")
        return self

    @property
    def effective_seasonality(self) -> bool:
        if self.seasonality is not None:
            return self.seasonality
        return self.sector == Sector.RETAIL


class CompanyDataset(BaseModel):
    """Source-neutral company dataset shared by ingestion and storage."""

    model_config = ConfigDict(extra="forbid")

    profile: CompanyProfile
    periods: list[PeriodFinancials]
    generator_config: SyntheticCompanyConfig | None = None
    edgar_cik: str | None = None


class GeneratedCompany(CompanyDataset):
    """Generator output: a dataset with its reproducibility configuration."""

    generator_config: SyntheticCompanyConfig

    @property
    def anomaly_labels(self) -> list[AnomalyInjection]:
        return self.generator_config.inject_anomalies


class CoverageIssue(BaseModel):
    concept: str
    detail: str


class QualityIssue(BaseModel):
    """Typed data-quality finding; errors block storage, warnings do not."""

    severity: Literal["error", "warning", "info"]
    code: str
    detail: str
    period_index: int | None = None


class ValidationReport(BaseModel):
    """Result of coverage and all-period data-quality validation."""

    required_pct: float = Field(ge=0.0, le=100.0)
    optional_pct: float = Field(ge=0.0, le=100.0)
    missing_required: list[CoverageIssue] = Field(default_factory=list)
    missing_optional: list[CoverageIssue] = Field(default_factory=list)
    issues: list[QualityIssue] = Field(default_factory=list)
    # Kept for callers of the original helper API. New code should inspect issues.
    warnings: list[str] = Field(default_factory=list)
    blocked: bool = False

    @property
    def errors(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def infos(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.severity == "info"]

    @property
    def typed_warnings(self) -> list[QualityIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @model_validator(mode="after")
    def _errors_block(self) -> ValidationReport:
        if any(issue.severity == "error" for issue in self.issues):
            self.blocked = True
        return self

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "required_pct": self.required_pct,
            "optional_pct": self.optional_pct,
            "missing_required": [i.concept for i in self.missing_required],
            "warnings": self.warnings,
            "issues": [issue.model_dump() for issue in self.issues],
            "blocked": self.blocked,
        }
