"""Currency handling and FX application (frozen data.md FD-1).

Synthetic default INR; currency is a per-company attribute. FX translation
applies only when mixing sources (e.g., USD EDGAR company shown in INR) using
an as-of-period rate — and is always disclosed via a note the caller attaches
to the coverage report.
"""

from __future__ import annotations

import math
from datetime import date

from backend.data_engine.contracts import DebtScheduleEntry, PeriodFinancials

# Fields scaled by the FX rate. Flow and stock money fields only —
# shares/ratios/exposures are dimensionless and never converted.
from backend.data_engine.normalize.periods import FLOW_FIELDS, STOCK_FIELDS  # noqa: E402

SUPPORTED_CURRENCIES = ("INR", "USD", "EUR")


def validate_currency(code: str) -> str:
    upper = code.upper()
    if upper not in SUPPORTED_CURRENCIES:
        raise ValueError(f"unsupported currency {code!r}; expected one of {SUPPORTED_CURRENCIES}")
    return upper


def _validate_rates(fx_series: dict[date, float]) -> None:
    for observed_date, rate in fx_series.items():
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError(f"fx rate on {observed_date} must be finite and positive")


def as_of_rate(fx_series: dict[date, float], on: date, *, fill: str = "previous") -> float | None:
    """Rate for the latest series date ≤ `on` (previous-carry default).

    fx_series maps date → rate quoted as TARGET currency per 1 unit of BASE
    currency (e.g., DEXINUS: INR per USD).
    """
    _validate_rates(fx_series)
    if not fx_series:
        return None
    eligible = [d for d in fx_series if d <= on]
    if not eligible:
        if fill == "previous":
            earliest = min(fx_series)
            return fx_series[earliest]  # carry-back disclosure handled by caller
        return None
    return fx_series[max(eligible)]


def convert_period(period: PeriodFinancials, rate: float) -> PeriodFinancials:
    """Scale all money fields by `rate` (target-per-base quote)."""
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError(f"fx rate must be finite and positive, got {rate}")
    updates: dict[str, float] = {}
    for field in (*FLOW_FIELDS, *STOCK_FIELDS):
        value = getattr(period, field)
        if value is not None:
            updates[field] = value * rate
    # Debt schedules are monetary amounts too; do not leave them in the base
    # currency while the scalar debt fields are translated.
    converted_schedule = None
    if period.debt_schedule is not None:
        converted_schedule = [
            DebtScheduleEntry(bucket=entry.bucket, amount=entry.amount * rate)
            for entry in period.debt_schedule
        ]
    # gross margin identity is scale-invariant but recompute for exactness
    if "revenue" in updates and "cogs" in updates:
        updates["gross_profit"] = updates["revenue"] - updates["cogs"]
    if converted_schedule is not None:
        return period.model_copy(update={**updates, "debt_schedule": converted_schedule})
    return period.model_copy(update=updates)


def convert_series(
    periods: list[PeriodFinancials],
    fx_series: dict[date, float],
) -> tuple[list[PeriodFinancials], list[str]]:
    """Convert every period using its as-of rate; returns (converted, notes).

    A note is recorded for carry-back (period predating the series) so the
    coverage report can disclose it (frozen FD-1).
    """
    notes: list[str] = []
    converted: list[PeriodFinancials] = []
    if not fx_series:
        return list(periods), ["empty fx series: no conversion applied"]
    _validate_rates(fx_series)
    earliest = min(fx_series)
    for p in periods:
        rate = as_of_rate(fx_series, p.period_end)
        if rate is None:
            converted.append(p)
            continue
        if p.period_end < earliest:
            notes.append(f"carry-back rate used for {p.period_end}")
        converted.append(convert_period(p, rate))
    return converted, notes
