"""Accounting identity checks (frozen data.md §3 rule 2, 0.5% tolerance)."""

from __future__ import annotations

from backend.data_engine.contracts import (
    IDENTITY_TOLERANCE,
    SHARE_SUM_TOLERANCE,
    PeriodFinancials,
    ShareEntry,
)

FlowFields = tuple[str, ...]


def _rel_ok(a: float, b: float, tolerance: float = IDENTITY_TOLERANCE) -> bool:
    """Relative comparison against the larger magnitude (0.5% frozen)."""
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= tolerance * scale


def balance_sheet_identity(p: PeriodFinancials) -> bool:
    if p.total_assets is None or p.total_liabilities is None or p.equity is None:
        return False
    return _rel_ok(p.total_assets, p.total_liabilities + p.equity)


def gross_profit_identity(p: PeriodFinancials) -> bool:
    if p.gross_profit is None or p.revenue is None or p.cogs is None:
        return False
    return _rel_ok(p.gross_profit, p.revenue - p.cogs)


def current_assets_composition(p: PeriodFinancials) -> bool:
    if p.current_assets is None or p.cash is None or p.receivables is None or p.inventory is None:
        return False
    return _rel_ok(p.current_assets, p.cash + p.receivables + p.inventory)


def current_assets_floor(p: PeriodFinancials) -> bool:
    """current_assets ≥ cash and ≥ receivables (frozen rule)."""
    if p.current_assets is None or p.cash is None or p.receivables is None:
        return False
    return p.current_assets >= p.cash - 1e-9 and p.current_assets >= p.receivables - 1e-9


def debt_composition(p: PeriodFinancials) -> bool:
    if p.total_debt is None or p.st_debt is None or p.lt_debt is None:
        return True  # not asserted when components are unknown
    return _rel_ok(p.total_debt, p.st_debt + p.lt_debt)


def bucket_sums_to_one(bucket: list[ShareEntry] | None) -> bool:
    if bucket is None:
        return True  # absence is a coverage issue, not an identity violation
    return abs(sum(e.share for e in bucket) - 1.0) <= SHARE_SUM_TOLERANCE


def check_period(p: PeriodFinancials) -> list[str]:
    """All frozen identity checks for one period; returns violation labels."""
    violations: list[str] = []
    if not balance_sheet_identity(p):
        violations.append("assets != liabilities + equity")
    if not gross_profit_identity(p):
        violations.append("gross_profit != revenue - cogs")
    if not current_assets_composition(p):
        violations.append("current_assets != cash + receivables + inventory")
    if not current_assets_floor(p):
        violations.append("current_assets below cash or receivables")
    for label, bucket in (
        ("customers", p.customers),
        ("suppliers", p.suppliers),
        ("products", p.products),
        ("regions", p.regions),
    ):
        if not bucket_sums_to_one(bucket):
            violations.append(f"{label} shares do not sum to 1")
    return violations


def check_all_periods(periods: list[PeriodFinancials]) -> dict[int, list[str]]:
    """Violation map keyed by period index (0-based)."""
    return {i: v for i, v in enumerate(check_period(p) for p in periods) if v}
