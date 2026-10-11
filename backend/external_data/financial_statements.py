"""Adapter for ``data/raw/kaggle/financial statements/Financial Statements.csv``.

Verified provenance: byte-identical (SHA-256) to Kaggle dataset
``rish59/financial-statements-of-major-companies2009-2023`` (license: ODbL /
Database Contents). Annual panel: 161 rows, 12 companies, 2009-2023.

Mapping policy (Phase 3): a source column reaches the canonical
``PeriodFinancials`` schema only when the semantic meaning matches exactly.
``total_debt`` is a single-unknown algebraic derivation from a provided ratio
(``total_debt = (Debt/Equity) * equity``) and is recorded as *derived*.
Precomputed ratios the dataset ships (Current Ratio, ROA, ...) are reported as
dataset-provided values in analyses but are NOT injected into canonical fields
the engine never received — fabricating ``current_assets``/``current_liabilities``
from a single ratio would invent fields.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd

from backend.data_engine.contracts import Frequency, PeriodFinancials
from backend.external_data.contracts import DatasetAudit
from backend.external_data.preprocessing import audit_frame


def _removed_evaluation_runners() -> None:
    """Evaluation runners live in ``backend.external_data.evaluation`` (moved)."""


DATASET_ID = "financial-statements"

REQUIRED_COLUMNS: tuple[str, ...] = (
    "Year",
    "Company",
    "Category",
    "Market Cap(in B USD)",
    "Revenue",
    "Gross Profit",
    "Net Income",
    "Earning Per Share",
    "EBITDA",
    "Share Holder Equity",
    "Cash Flow from Operating",
    "Cash Flow from Investing",
    "Cash Flow from Financial Activities",
    "Current Ratio",
    "Debt/Equity Ratio",
    "ROE",
    "ROA",
    "ROI",
    "Net Profit Margin",
    "Free Cash Flow per Share",
    "Return on Tangible Equity",
    "Number of Employees",
    "Inflation Rate(in US)",
)

# Source column -> canonical PeriodFinancials field (exact semantics only).
CANONICAL_MAP: dict[str, str] = {
    "Revenue": "revenue",
    "Gross Profit": "gross_profit",
    "Net Income": "net_income",
    "EBITDA": "ebitda",
    "Share Holder Equity": "equity",
    "Cash Flow from Operating": "ocf",
}

# Source column -> canonical field produced by documented algebraic derivation.
DERIVED_MAP: dict[str, str] = {
    "Debt/Equity Ratio": "total_debt (= (Debt/Equity Ratio) * equity)",
}

# Present in the dataset but not injectable into the canonical schema without
# fabricating fields (reported as dataset-provided values in analyses only).
PROVIDED_NOT_MAPPED: tuple[str, ...] = (
    "Market Cap(in B USD)",
    "Earning Per Share",
    "Cash Flow from Investing",
    "Cash Flow from Financial Activities",
    "Current Ratio",
    "Debt/Equity Ratio",
    "ROE",
    "ROA",
    "ROI",
    "Net Profit Margin",
    "Free Cash Flow per Share",
    "Return on Tangible Equity",
    "Number of Employees",
    "Inflation Rate(in US)",
)

# Canonical fields required by registry formulas that the dataset cannot supply.
UNAVAILABLE_INPUTS: tuple[str, ...] = (
    "cogs",
    "opex",
    "ebit",
    "da",
    "interest_expense",
    "tax",
    "cash",
    "receivables",
    "inventory",
    "payables",
    "current_assets",
    "current_liabilities",
    "total_assets",
    "total_liabilities",
    "st_debt",
    "lt_debt",
    "capex",
    "fcf",
    "dividends",
)

# Category -> Risk Engine profile sector (documented, conservative mapping used
# solely by the profile-driven gdp_sensitivity calculator).
SECTOR_MAP: dict[str, str] = {
    "Manufacturing": "manufacturing",
}
SECTOR_DEFAULT = "services"


class FinancialStatementsSchemaError(ValueError):
    """Raised when the raw file does not match the verified schema."""


def load_financial_statements(path: str | Path) -> pd.DataFrame:
    """Load, validate, and normalize column names (whitespace stripped)."""
    frame = pd.read_csv(path)
    frame.columns = [str(c).strip() for c in frame.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise FinancialStatementsSchemaError(f"missing columns: {missing}")
    if frame.empty:
        raise FinancialStatementsSchemaError("file contains no data rows")
    frame = frame.copy()
    frame["Year"] = pd.to_numeric(frame["Year"], errors="raise").astype("int64")
    if not frame["Year"].between(1900, 2100).all():
        raise FinancialStatementsSchemaError("Year values out of plausible range")
    frame["Company"] = frame["Company"].astype(str).str.strip()
    frame["Category"] = frame["Category"].astype(str).str.strip()
    return frame


def sector_for_category(category: str) -> str:
    """Conservative Category -> sector mapping (documented assumption)."""
    return SECTOR_MAP.get(category.strip(), SECTOR_DEFAULT)


def _clean_number(value: object) -> float | None:
    """Float or None; NaN/inf become None so frozen validators never see them."""
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def to_canonical_period(row: pd.Series) -> dict[str, object]:
    """Convert one dataset row into a validated canonical period dict.

    Calendar-year period boundaries are a documented representation assumption:
    the dataset provides only ``Year``, not fiscal start/end dates. Financial
    amounts keep their source units (ratios are unit-free; margins and
    volatility are computed within consistent columns).
    """
    year = int(row["Year"])
    payload: dict[str, object] = {
        "period_start": date(year, 1, 1),
        "period_end": date(year, 12, 31),
        "fiscal_year": year,
        "quarter": None,
        "frequency": Frequency.ANNUAL,
        "source": "kaggle:financial-statements",
    }
    for source_column, canonical_field in CANONICAL_MAP.items():
        payload[canonical_field] = _clean_number(row[source_column])
    equity = _clean_number(row["Share Holder Equity"])
    debt_ratio = _clean_number(row["Debt/Equity Ratio"])
    # Single-unknown derivation: total_debt = (Debt/Equity) * equity. This is
    # algebraically exact given both provided inputs (recorded as derived).
    payload["total_debt"] = (
        debt_ratio * equity if debt_ratio is not None and equity is not None else None
    )
    validated = PeriodFinancials(**payload)
    return validated.model_dump(mode="python")


def company_datasets(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Per-company ``{profile, periods}`` datasets for the Risk Engine.

    Periods are strictly chronological so ``periods[-1]`` is the latest year.
    """
    datasets: dict[str, dict[str, object]] = {}
    ordered = frame.sort_values(["Company", "Year"], kind="mergesort")
    for company, group in ordered.groupby("Company", sort=True):
        category = str(group["Category"].iloc[0])
        profile: dict[str, object] = {
            "id": str(company),
            "name": str(company),
            "category": category,
            "sector": sector_for_category(category),
        }
        periods = [to_canonical_period(row) for _, row in group.iterrows()]
        datasets[str(company)] = {"profile": profile, "periods": periods}
    return datasets


def panel_summary(frame: pd.DataFrame) -> dict[str, object]:
    """Structural facts about the panel (Phase 1/13 checks)."""
    per_company = frame["Company"].value_counts().sort_index()
    years = sorted(int(y) for y in frame["Year"].unique())
    ordered = frame.sort_values(["Company", "Year"], kind="mergesort")
    grouped = ordered.groupby("Company")["Year"].apply(lambda s: [int(y) for y in s])
    consecutive = all(
        all(b - a == 1 for a, b in zip(values, values[1:], strict=False))
        for values in grouped
    )
    return {
        "companies": int(frame["Company"].nunique()),
        "observations_per_company": {k: int(v) for k, v in per_company.items()},
        "min_obs_per_company": int(per_company.min()),
        "max_obs_per_company": int(per_company.max()),
        "companies_with_at_least_12_periods": int((per_company >= 12).sum()),
        "years": years,
        "frequency": "annual",
        "all_company_histories_consecutive": bool(consecutive),
        "categories": sorted(str(c) for c in frame["Category"].unique()),
    }


def audit(path: str | Path) -> DatasetAudit:
    """Phase 1 audit for the financial-statements dataset."""
    frame = load_financial_statements(path)
    return audit_frame(
        frame,
        dataset_id=DATASET_ID,
        file_name=Path(path).name,
        identifier_columns=["Company"],
        date_columns=["Year"],
        duplicate_id_column=None,
    )
