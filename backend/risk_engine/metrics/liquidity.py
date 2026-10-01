"""Liquidity Dimension Metrics (Spec §3 & §17.1).

Pure-function implementations for liquidity, cash runway, and short-term obligation metrics.
"""

from __future__ import annotations

from typing import Any

from backend.risk_engine.contracts import MetricResult, MetricStatus


def calc_current_ratio(period: dict[str, Any]) -> MetricResult:
    ca = period.get("current_assets")
    cl = period.get("current_liabilities")

    if ca is None or cl is None:
        return MetricResult(
            metric_id="current_ratio",
            name="Current Ratio",
            dimension="liquidity",
            status=MetricStatus.MISSING_INPUT,
            message="Missing current_assets or current_liabilities",
            unit="ratio",
        )

    if cl <= 0:
        return MetricResult(
            metric_id="current_ratio",
            name="Current Ratio",
            dimension="liquidity",
            value=99.0 if ca > 0 else 1.0,
            status=MetricStatus.FLAGGED,
            message="Current liabilities is zero or negative (surplus)",
            forced_score=5.0,
            unit="ratio",
        )

    ratio = ca / cl
    return MetricResult(
        metric_id="current_ratio",
        name="Current Ratio",
        dimension="liquidity",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"current_assets": ca, "current_liabilities": cl},
    )


def calc_quick_ratio(period: dict[str, Any]) -> MetricResult:
    ca = period.get("current_assets")
    cl = period.get("current_liabilities")
    inv = period.get("inventory") or 0.0

    if ca is None or cl is None:
        return MetricResult(
            metric_id="quick_ratio",
            name="Quick Ratio",
            dimension="liquidity",
            status=MetricStatus.MISSING_INPUT,
            message="Missing current_assets or current_liabilities",
            unit="ratio",
        )

    if cl <= 0:
        return MetricResult(
            metric_id="quick_ratio",
            name="Quick Ratio",
            dimension="liquidity",
            value=99.0 if (ca - inv) > 0 else 1.0,
            status=MetricStatus.FLAGGED,
            message="Current liabilities is zero or negative (surplus)",
            forced_score=5.0,
            unit="ratio",
        )

    quick_assets = ca - inv
    ratio = quick_assets / cl
    return MetricResult(
        metric_id="quick_ratio",
        name="Quick Ratio",
        dimension="liquidity",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"current_assets": ca, "inventory": inv, "current_liabilities": cl},
    )


def calc_cash_ratio(period: dict[str, Any]) -> MetricResult:
    cash = period.get("cash")
    cl = period.get("current_liabilities")

    if cash is None or cl is None:
        return MetricResult(
            metric_id="cash_ratio",
            name="Cash Ratio",
            dimension="liquidity",
            status=MetricStatus.MISSING_INPUT,
            message="Missing cash or current_liabilities",
            unit="ratio",
        )

    if cl <= 0:
        return MetricResult(
            metric_id="cash_ratio",
            name="Cash Ratio",
            dimension="liquidity",
            value=99.0 if cash > 0 else 1.0,
            status=MetricStatus.FLAGGED,
            message="Current liabilities is zero or negative (surplus)",
            forced_score=5.0,
            unit="ratio",
        )

    ratio = cash / cl
    return MetricResult(
        metric_id="cash_ratio",
        name="Cash Ratio",
        dimension="liquidity",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"cash": cash, "current_liabilities": cl},
    )


def calc_cash_runway_months(
    period: dict[str, Any], history: list[dict[str, Any]] | None = None
) -> MetricResult:
    cash = period.get("cash")
    ocf = period.get("ocf")

    if cash is None:
        return MetricResult(
            metric_id="cash_runway_months",
            name="Cash Runway (Months)",
            dimension="liquidity",
            status=MetricStatus.MISSING_INPUT,
            message="Missing cash balance",
            unit="months",
        )

    # Determine monthly burn from trend or current period OCF
    if history and len(history) >= 2:
        ocfs: list[float] = [float(p["ocf"]) for p in history if p.get("ocf") is not None]
        avg_ocf = sum(ocfs) / len(ocfs) if ocfs else (ocf or 0.0)
    else:
        avg_ocf = ocf or 0.0

    if avg_ocf >= 0:
        return MetricResult(
            metric_id="cash_runway_months",
            name="Cash Runway (Months)",
            dimension="liquidity",
            value=999.0,
            status=MetricStatus.FLAGGED,
            message="n/a - positive operating cash flow (runway not constrained)",
            forced_score=5.0,
            unit="months",
        )

    monthly_burn = max(0.0, -avg_ocf / (12.0 if period.get("frequency") == "annual" else 1.0))
    if monthly_burn == 0:
        runway = 999.0
    else:
        runway = cash / monthly_burn

    return MetricResult(
        metric_id="cash_runway_months",
        name="Cash Runway (Months)",
        dimension="liquidity",
        value=runway,
        status=MetricStatus.VALID,
        unit="months",
        inputs_used={"cash": cash, "monthly_burn": monthly_burn},
    )


def calc_st_obligation_coverage(period: dict[str, Any]) -> MetricResult:
    cash = period.get("cash")
    cl = period.get("current_liabilities")
    st_debt = period.get("st_debt") or cl

    if cash is None or st_debt is None:
        return MetricResult(
            metric_id="st_obligation_coverage",
            name="Short-Term Obligation Coverage",
            dimension="liquidity",
            status=MetricStatus.MISSING_INPUT,
            message="Missing cash or short-term obligations",
            unit="ratio",
        )

    if st_debt <= 0:
        return MetricResult(
            metric_id="st_obligation_coverage",
            name="Short-Term Obligation Coverage",
            dimension="liquidity",
            value=99.0 if cash > 0 else 1.0,
            status=MetricStatus.FLAGGED,
            message="Short term debt obligation is zero",
            unit="ratio",
        )

    coverage = cash / st_debt
    return MetricResult(
        metric_id="st_obligation_coverage",
        name="Short-Term Obligation Coverage",
        dimension="liquidity",
        value=coverage,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"cash": cash, "st_debt": st_debt},
    )
