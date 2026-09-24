"""Calendarization: sorting, frequency aggregation, gap detection.

Aggregation rules (mirroring the synthetic generator's annual path so any
source normalizes identically):
- flows (income statement, cash flow) are summed;
- stocks (balance sheet, buckets, exposures) come from the last sub-period;
- derived identities are recomputed after aggregation (gross_profit) or hold
  by summation (assets = liabilities + equity holds per period, so it holds
  for summed flows too).
"""

from __future__ import annotations

from datetime import date

from backend.data_engine.contracts import Frequency, PeriodFinancials

FLOW_FIELDS: tuple[str, ...] = (
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
    "capex",
    "ocf",
    "fcf",
    "dividends",
)

STOCK_FIELDS: tuple[str, ...] = (
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
)

_STEP_BY_FREQUENCY: dict[Frequency, int] = {
    Frequency.MONTHLY: 1,
    Frequency.QUARTERLY: 3,
    Frequency.ANNUAL: 12,
}


def sort_periods(periods: list[PeriodFinancials]) -> list[PeriodFinancials]:
    return sorted(periods, key=lambda p: p.period_end)


def infer_frequency(periods: list[PeriodFinancials]) -> Frequency | None:
    """Infer frequency from median month gap between consecutive period ends."""
    if len(periods) < 2:
        return None
    gaps = sorted(
        (b.period_end.year - a.period_end.year) * 12 + (b.period_end.month - a.period_end.month)
        for a, b in zip(periods, periods[1:], strict=False)
    )
    median = gaps[len(gaps) // 2]
    if median <= 1:
        return Frequency.MONTHLY
    if median <= 3:
        return Frequency.QUARTERLY
    return Frequency.ANNUAL


def find_gaps(periods: list[PeriodFinancials]) -> list[tuple[date, date]]:
    """Missing spans between consecutive periods (for disclosure)."""
    gaps: list[tuple[date, date]] = []
    for prev, cur in zip(periods, periods[1:], strict=False):
        month_index = prev.period_end.year * 12 + prev.period_end.month
        next_index = cur.period_end.year * 12 + cur.period_end.month
        if next_index != month_index + 1:
            gaps.append((prev.period_end, cur.period_end))
    return gaps


def chunk_by_step(
    periods: list[PeriodFinancials], step_months: int
) -> list[list[PeriodFinancials]]:
    """Group sorted periods into consecutive chunks of `step_months` count."""
    chunks: list[list[PeriodFinancials]] = []
    current: list[PeriodFinancials] = []
    for p in periods:
        current.append(p)
        if len(current) == step_months:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)  # trailing partial chunk (disclosed by caller)
    return chunks


def aggregate_chunk(chunk: list[PeriodFinancials], target: Frequency) -> PeriodFinancials:
    """Aggregate a chunk of monthly periods to the target frequency."""
    last = chunk[-1]
    flows = {f: sum(getattr(p, f) or 0.0 for p in chunk) for f in FLOW_FIELDS}
    # recompute additive identity after summation
    flows["gross_profit"] = flows["revenue"] - flows["cogs"]
    stocks = {f: getattr(last, f) for f in STOCK_FIELDS}
    fiscal_year = last.period_end.year if target is Frequency.ANNUAL else None
    quarter = (last.period_end.month - 1) // 3 + 1 if target is Frequency.QUARTERLY else None
    return last.model_copy(
        update={
            "period_start": chunk[0].period_start,
            "period_end": last.period_end,
            "fiscal_year": fiscal_year or last.fiscal_year,
            "quarter": quarter,
            "frequency": target,
            **flows,
            **stocks,
        }
    )


def to_frequency(
    periods: list[PeriodFinancials], target: Frequency
) -> tuple[list[PeriodFinancials], list[str]]:
    """Normalize monthly periods to quarterly/annual (or pass through sorted).

    Returns (normalized, notes). Aggregation of higher-frequency data is not
    supported (a note records the request instead of inventing data).
    """
    notes: list[str] = []
    ordered = sort_periods(periods)
    source = infer_frequency(ordered)
    if source is not Frequency.MONTHLY:
        notes.append(f"source frequency {source}: only monthly input is aggregated")
        return ordered, notes
    if target is Frequency.MONTHLY:
        return ordered, notes

    step = _STEP_BY_FREQUENCY[target]
    chunks = chunk_by_step(ordered, step)
    if len(chunks[-1]) != step:
        notes.append(f"trailing partial chunk dropped ({len(chunks[-1])} period(s))")
        chunks = chunks[:-1]
    return [aggregate_chunk(c, target) for c in chunks], notes


def trailing_window(periods: list[PeriodFinancials], months: int) -> list[PeriodFinancials]:
    """Most recent `months` periods (feature preparation helper)."""
    ordered = sort_periods(periods)
    return ordered[-months:]
