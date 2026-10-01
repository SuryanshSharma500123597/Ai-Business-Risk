"""Macro scalar helpers for the Stage 5 market-inputs adapter (D20)."""

from __future__ import annotations

import math
import statistics

from backend.data_engine.ingest.base import MacroSeries
from backend.risk_engine.contracts import MIN_CPI_MONTHS, MIN_FEDFUNDS_MONTHS

__all__ = [
    "cpi_change_24m",
    "fedfunds_current_and_median",
    "gross_margin_change_24m",
]


def cpi_change_24m(cpi: MacroSeries) -> float | None:
    """24-month percentage change of CPI levels (strict Q-C2: needs 24 months)."""
    observations = sorted(cpi.observations, key=lambda point: point.date)
    if len(observations) < MIN_CPI_MONTHS:
        return None
    first = observations[-MIN_CPI_MONTHS].value
    last = observations[-1].value
    if not math.isfinite(first) or not math.isfinite(last) or first == 0:
        raise ValueError("CPI observations must be finite and non-zero")
    return (last - first) / abs(first) * 100.0


def gross_margin_change_24m(periods: list[dict[str, object]]) -> float | None:
    """24-month gross-margin percentage-point change from canonical periods."""
    margins: list[float] = []
    for period in periods[-MIN_CPI_MONTHS:]:
        revenue = period.get("revenue")
        gross_profit = period.get("gross_profit")
        if (
            isinstance(revenue, (int, float))
            and isinstance(gross_profit, (int, float))
            and math.isfinite(revenue)
            and math.isfinite(gross_profit)
            and revenue != 0
        ):
            margins.append(float(gross_profit) / float(revenue) * 100.0)
    if len(margins) < MIN_CPI_MONTHS:
        return None
    return margins[-1] - margins[0]


def fedfunds_current_and_median(fedfunds: MacroSeries) -> tuple[float | None, float | None]:
    """Current FEDFUNDS level and trailing 5-year median (strict: 60 obs)."""
    observations = sorted(fedfunds.observations, key=lambda point: point.date)
    if len(observations) < MIN_FEDFUNDS_MONTHS:
        return None, None
    values = [point.value for point in observations[-MIN_FEDFUNDS_MONTHS:]]
    if any(not math.isfinite(value) for value in values):
        raise ValueError("FEDFUNDS observations must be finite")
    return values[-1], float(statistics.median(values))
