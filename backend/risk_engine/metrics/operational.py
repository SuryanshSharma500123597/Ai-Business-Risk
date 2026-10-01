"""Operational Dimension Metrics (Spec §6 & §17.1).

Pure-function implementations for DIO, DPO, Cash Conversion Cycle (CCC),
supplier concentration, opex rigidity, and single-source supplier flags.
"""

from __future__ import annotations

from typing import Any

from backend.risk_engine.contracts import MetricResult, MetricStatus


def calc_dio(period: dict[str, Any]) -> MetricResult:
    inv = period.get("inventory")
    cogs = period.get("cogs")

    if inv is None or cogs is None:
        return MetricResult(
            metric_id="dio",
            name="Days Inventory Outstanding (DIO)",
            dimension="operational",
            status=MetricStatus.MISSING_INPUT,
            message="Missing inventory or cogs",
            unit="days",
        )

    if cogs <= 0:
        # Frozen spec (risk-engine.md §6): cogs=0 -> skip. The metric is not
        # computable rather than risky, so it is excluded from the dimension mean
        # instead of scoring a sentinel value.
        return MetricResult(
            metric_id="dio",
            name="Days Inventory Outstanding (DIO)",
            dimension="operational",
            value=None,
            status=MetricStatus.UNAVAILABLE,
            message="COGS is zero or negative - metric skipped",
            unit="days",
        )

    days = (inv / cogs) * 365.0
    return MetricResult(
        metric_id="dio",
        name="Days Inventory Outstanding (DIO)",
        dimension="operational",
        value=days,
        status=MetricStatus.VALID,
        unit="days",
        inputs_used={"inventory": inv, "cogs": cogs},
    )


def calc_dpo(period: dict[str, Any]) -> MetricResult:
    payables = period.get("payables")
    cogs = period.get("cogs")

    if payables is None or cogs is None:
        return MetricResult(
            metric_id="dpo",
            name="Days Payables Outstanding (DPO)",
            dimension="operational",
            status=MetricStatus.MISSING_INPUT,
            message="Missing payables or cogs",
            unit="days",
        )

    if cogs <= 0:
        return MetricResult(
            metric_id="dpo",
            name="Days Payables Outstanding (DPO)",
            dimension="operational",
            value=0.0,
            status=MetricStatus.FLAGGED,
            message="COGS is zero or negative",
            unit="days",
        )

    days = (payables / cogs) * 365.0
    return MetricResult(
        metric_id="dpo",
        name="Days Payables Outstanding (DPO)",
        dimension="operational",
        value=days,
        status=MetricStatus.VALID,
        unit="days",
        inputs_used={"payables": payables, "cogs": cogs},
    )


def calc_ccc(dso: float | None, dio: float | None, dpo: float | None) -> MetricResult:
    if dso is None or dio is None or dpo is None:
        return MetricResult(
            metric_id="ccc",
            name="Cash Conversion Cycle (CCC)",
            dimension="operational",
            status=MetricStatus.MISSING_INPUT,
            message="Missing DSO, DIO, or DPO",
            unit="days",
        )

    ccc_val = dso + dio - dpo
    return MetricResult(
        metric_id="ccc",
        name="Cash Conversion Cycle (CCC)",
        dimension="operational",
        value=ccc_val,
        status=MetricStatus.VALID,
        unit="days",
        inputs_used={"dso": dso, "dio": dio, "dpo": dpo},
    )


def calc_opex_rigidity(period: dict[str, Any]) -> MetricResult:
    opex = period.get("opex")

    if opex is None:
        return MetricResult(
            metric_id="opex_rigidity",
            name="Opex Rigidity",
            dimension="operational",
            status=MetricStatus.MISSING_INPUT,
            message="Missing opex",
            unit="ratio",
        )

    # Fixed share of opex (default baseline assumption 0.5 unless explicitly specified)
    fixed_share = period.get("fixed_opex_share", 0.5)
    return MetricResult(
        metric_id="opex_rigidity",
        name="Opex Rigidity",
        dimension="operational",
        value=fixed_share,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"fixed_share": fixed_share, "opex": opex},
    )


def calc_single_source_flags(period: dict[str, Any]) -> MetricResult:
    suppliers = period.get("suppliers") or []
    if not suppliers:
        return MetricResult(
            metric_id="single_source_flags",
            name="Single Source Supplier Flags",
            dimension="operational",
            value=0.0,
            status=MetricStatus.VALID,
            unit="count",
        )

    count = 0
    for s in suppliers:
        share = s.get("share", 0.0) if isinstance(s, dict) else getattr(s, "share", 0.0)
        if share > 0.60:
            count += 1

    return MetricResult(
        metric_id="single_source_flags",
        name="Single Source Supplier Flags",
        dimension="operational",
        value=float(count),
        status=MetricStatus.VALID,
        unit="count",
        inputs_used={"single_source_count": count},
    )
