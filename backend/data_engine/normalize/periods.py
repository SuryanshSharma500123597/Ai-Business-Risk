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
    """Infer frequency from declarations and median calendar spacing."""
    if len(periods) < 2:
        return None
    declared = {Frequency(period.frequency) for period in periods}
    if len(declared) == 1 and next(iter(declared)) is not Frequency.MONTHLY:
        return next(iter(declared))
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


def find_gaps(
    periods: list[PeriodFinancials], frequency: Frequency | None = None
) -> list[tuple[date, date]]:
    """Missing spans between consecutive periods, respecting calendar frequency."""
    ordered = sort_periods(periods)
    if len(ordered) < 2:
        return []
    selected_frequency = (
        Frequency(frequency)
        if frequency is not None
        else (infer_frequency(ordered) or Frequency(ordered[0].frequency))
    )
    step = _STEP_BY_FREQUENCY[selected_frequency]
    gaps: list[tuple[date, date]] = []
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        month_index = prev.period_end.year * 12 + prev.period_end.month
        next_index = cur.period_end.year * 12 + cur.period_end.month
        if next_index != month_index + step:
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

    def sum_flow(field: str) -> float | None:
        values = [getattr(p, field) for p in chunk]
        # Missing observations are not zero observations. Preserve the missing
        # concept so coverage and downstream dimensions can degrade honestly.
        if any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    flows = {f: sum_flow(f) for f in FLOW_FIELDS}
    # recompute additive identity only when both operands are available
    if flows["revenue"] is not None and flows["cogs"] is not None:
        flows["gross_profit"] = flows["revenue"] - flows["cogs"]
    stocks = {f: getattr(last, f) for f in STOCK_FIELDS}
    fiscal_year = last.period_end.year if target is Frequency.ANNUAL else last.fiscal_year
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
    periods: list[PeriodFinancials], target: Frequency | str
) -> tuple[list[PeriodFinancials], list[str]]:
    """Normalize monthly periods to quarterly/annual (or pass through sorted).

    Returns (normalized, notes). Aggregation of higher-frequency data is not
    supported (a note records the request instead of inventing data).
    """
    notes: list[str] = []
    target = Frequency(target)
    ordered = sort_periods(periods)
    if not ordered:
        return [], notes
    source = infer_frequency(ordered) or Frequency(ordered[0].frequency)
    if target is Frequency.MONTHLY:
        if source is not Frequency.MONTHLY:
            notes.append(f"source frequency {source}: cannot expand to monthly without source data")
        return ordered, notes
    if source is target:
        if source is not Frequency.MONTHLY:
            notes.append(f"source frequency {source}: only monthly input is aggregated")
        return ordered, notes
    source_months = _STEP_BY_FREQUENCY[source]
    target_months = _STEP_BY_FREQUENCY[target]
    if source_months > target_months:
        notes.append(f"source frequency {source}: cannot expand to {target} without source data")
        return ordered, notes
    if target_months % source_months:
        notes.append(f"cannot align {source} periods to {target}")
        return ordered, notes

    # Group by calendar labels, not by arbitrary list position. This prevents
    # a missing month/quarter from shifting every subsequent fiscal bucket.
    keys: list[tuple[int, ...]]
    if target is Frequency.QUARTERLY:
        keys = [(p.period_end.year, (p.period_end.month - 1) // 3 + 1) for p in ordered]
    else:
        keys = [(p.period_end.year,) for p in ordered]
    grouped: list[list[PeriodFinancials]] = []
    current_key: tuple[int, ...] | None = None
    for key, period in zip(keys, ordered, strict=True):
        if key != current_key:
            grouped.append([])
            current_key = key
        grouped[-1].append(period)

    expected_count = target_months // source_months
    complete: list[list[PeriodFinancials]] = []
    for chunk in grouped:
        contiguous = all(
            (current.period_end.year * 12 + current.period_end.month)
            - (previous.period_end.year * 12 + previous.period_end.month)
            == source_months
            for previous, current in zip(chunk, chunk[1:], strict=False)
        )
        if len(chunk) != expected_count or not contiguous:
            notes.append(
                f"incomplete {target} bucket dropped ({len(chunk)} of "
                f"{expected_count} period(s)); trailing partial or gap"
            )
            continue
        complete.append(chunk)
    return [aggregate_chunk(chunk, target) for chunk in complete], notes


def trailing_window(periods: list[PeriodFinancials], months: int) -> list[PeriodFinancials]:
    """Most recent `months` periods (feature preparation helper)."""
    ordered = sort_periods(periods)
    return ordered[-months:]
