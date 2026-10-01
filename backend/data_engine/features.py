"""Feature preparation: canonical raw values only.

This module deliberately does not calculate ratios, growth, scores, imputations,
or model features. It only flattens numeric canonical financial facts and
exposure values, retaining missing values as pandas NA/NaN and adding explicit
coverage indicators for downstream consumers.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from backend.data_engine.contracts import (
    NUMERIC_CONCEPT_FIELDS,
    OPTIONAL_CONCEPTS,
    REQUIRED_CONCEPTS,
)
from backend.data_engine.validate.schema_checks import coverage_report

_EXPOSURE_FIELDS = {
    "fx_exposure": ("foreign_revenue_share", "import_cost_share"),
    "commodity_exposure": ("cost_share",),
    "rate_exposure": ("floating_debt_share",),
}


def _raw_dict(period: Any) -> dict[str, Any]:
    """Flatten one PeriodFinancials without deriving a new financial fact."""
    values = period.model_dump(mode="python")
    result: dict[str, Any] = {
        "period_start": values["period_start"],
        "period_end": values["period_end"],
        "fiscal_year": values["fiscal_year"],
        "quarter": values["quarter"],
        "frequency": str(values["frequency"]),
        "source": values["source"],
    }
    for field in NUMERIC_CONCEPT_FIELDS:
        result[field] = values.get(field)
    for parent, children in _EXPOSURE_FIELDS.items():
        payload = values.get(parent)
        if payload is None:
            for child in children:
                result[f"{parent}_{child}"] = None
        else:
            for child in children:
                result[f"{parent}_{child}"] = payload.get(child)
    return result


def numeric_financial_frame(periods: Iterable[Any]) -> pd.DataFrame:
    """Return one row per period of normalized raw numeric facts and exposures."""
    frame = pd.DataFrame([_raw_dict(period) for period in periods])
    if frame.empty:
        return pd.DataFrame(columns=["period_start", "period_end", *NUMERIC_CONCEPT_FIELDS])
    return frame.sort_values("period_end", kind="stable").reset_index(drop=True)


def coverage_frame(periods: list[Any]) -> pd.DataFrame:
    """Return per-period presence flags; no values are filled or transformed."""
    rows: list[dict[str, Any]] = []
    concepts = (*REQUIRED_CONCEPTS, *OPTIONAL_CONCEPTS)
    for period in periods:
        values = period.model_dump(mode="python")
        row: dict[str, Any] = {
            "period_end": values["period_end"],
            "source": values["source"],
        }
        for concept in concepts:
            value = values.get(concept)
            row[f"has_{concept}"] = value is not None and value != [] and value != {}
        rows.append(row)
    return pd.DataFrame(rows).sort_values("period_end", kind="stable").reset_index(drop=True)


def build_feature_frame(dataset: Any) -> pd.DataFrame:
    """Combine raw numeric facts with explicit per-period coverage flags."""
    periods = list(dataset.periods)
    raw = numeric_financial_frame(periods)
    coverage = coverage_frame(periods)
    if raw.empty:
        return raw
    return raw.merge(coverage, on=["period_end", "source"], how="left", validate="one_to_one")


def prepare_features(dataset: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return ``(raw_frame, metadata)`` for feature consumers and notebooks."""
    periods = list(dataset.periods)
    report = coverage_report(periods, mode="all")
    frame = build_feature_frame(dataset)
    metadata = {
        "required_coverage_pct": report.required_pct,
        "optional_coverage_pct": report.optional_pct,
        "blocked": report.blocked,
        "missing_required": [issue.concept for issue in report.missing_required],
        "missing_optional": [issue.concept for issue in report.missing_optional],
        "raw_numeric_fields": list(NUMERIC_CONCEPT_FIELDS),
        "exposure_fields": [
            f"{parent}_{child}"
            for parent, children in _EXPOSURE_FIELDS.items()
            for child in children
        ],
    }
    return frame, metadata


def exposure_frame(periods: Iterable[Any]) -> pd.DataFrame:
    """Return only flattened raw exposure observations and period identity."""
    frame = numeric_financial_frame(periods)
    columns = ["period_start", "period_end", "frequency", "source", *_EXPOSURE_COLUMNS]
    return frame[[column for column in columns if column in frame.columns]]


_EXPOSURE_COLUMNS = [
    f"{parent}_{child}" for parent, children in _EXPOSURE_FIELDS.items() for child in children
]


# Clear names for callers and backwards-compatible discovery by notebooks.
financial_frame = numeric_financial_frame
financial_features = numeric_financial_frame
build_features = build_feature_frame
