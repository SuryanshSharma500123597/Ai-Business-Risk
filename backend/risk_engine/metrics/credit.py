"""Credit Dimension Metrics & Reference Models (Spec §5, §9 & §17.1).

Pure-function implementations for DSO, receivables concentration, receivable trend,
Altman Z-score variants (Z, Z', Z''), and Merton Distance-to-Default/PD.
"""

from __future__ import annotations

import math
from typing import Any

from backend.risk_engine.contracts import MetricResult, MetricStatus
from backend.risk_engine.registry import interpolate_score

# Altman variant cutoffs (distress, safe) — risk-engine.md §5/§9. Variants are
# never mixed; the original Z cutoffs are not reused for Z'/Z''.
_ALTMAN_CUTOFFS: dict[str, tuple[float, float]] = {
    "Z": (1.81, 2.99),
    "Z'": (1.23, 2.675),
    "Z''": (1.1, 2.6),
}


def _altman_anchors(distress_cutoff: float, safe_cutoff: float) -> list[tuple[float, float]]:
    """Variant-specific score mapping (risk-engine.md §5).

    safe zone -> 10, distress cut-off -> 60, and linear to 100 as Z falls to 0.
    """
    return [(0.0, 100.0), (distress_cutoff, 60.0), (safe_cutoff, 10.0)]


def calc_dso(period: dict[str, Any]) -> MetricResult:
    receivables = period.get("receivables")
    revenue = period.get("revenue")

    if receivables is None or revenue is None:
        return MetricResult(
            metric_id="dso",
            name="Days Sales Outstanding (DSO)",
            dimension="credit",
            status=MetricStatus.MISSING_INPUT,
            message="Missing receivables or revenue",
            unit="days",
        )

    if revenue <= 0:
        return MetricResult(
            metric_id="dso",
            name="Days Sales Outstanding (DSO)",
            dimension="credit",
            value=365.0,
            status=MetricStatus.FLAGGED,
            message="Revenue is zero or negative",
            unit="days",
        )

    days = (receivables / revenue) * 365.0
    return MetricResult(
        metric_id="dso",
        name="Days Sales Outstanding (DSO)",
        dimension="credit",
        value=days,
        status=MetricStatus.VALID,
        unit="days",
        inputs_used={"receivables": receivables, "revenue": revenue},
    )


def calc_receivable_trend(history: list[dict[str, Any]]) -> MetricResult:
    if not history or len(history) < 8:
        return MetricResult(
            metric_id="receivable_trend",
            name="Receivable Trend (DSO Slope)",
            dimension="credit",
            status=MetricStatus.INSUFFICIENT_HISTORY,
            message="Requires at least 8 periods",
            unit="days_per_year",
        )

    dso_values = []
    for p in history:
        res = calc_dso(p)
        if res.status == MetricStatus.VALID and res.value is not None:
            dso_values.append(res.value)

    if len(dso_values) < 8:
        return MetricResult(
            metric_id="receivable_trend",
            name="Receivable Trend (DSO Slope)",
            dimension="credit",
            status=MetricStatus.INSUFFICIENT_HISTORY,
            message="Insufficient valid DSO periods",
            unit="days_per_year",
        )

    n = len(dso_values)
    x = list(range(n))
    mean_x = sum(x) / n
    mean_y = sum(dso_values) / n
    denom = sum((xi - mean_x) ** 2 for xi in x)
    if denom == 0:
        slope_per_period = 0.0
    else:
        slope_per_period = sum((x[i] - mean_x) * (dso_values[i] - mean_y) for i in range(n)) / denom

    slope_annual = slope_per_period * 12.0  # monthly periods scaled to annual days/year
    return MetricResult(
        metric_id="receivable_trend",
        name="Receivable Trend (DSO Slope)",
        dimension="credit",
        value=slope_annual,
        status=MetricStatus.VALID,
        unit="days_per_year",
        inputs_used={"obs_count": n, "slope_annual": slope_annual},
    )


def calc_altman_z(
    period: dict[str, Any],
    profile: dict[str, Any] | None = None,
    market_equity: float | None = None,
) -> MetricResult:
    """Calculate Altman Z-score with variant auto-selection per Spec §5/§9.

    - Public Manufacturer: Original Z (X4 = market_equity / total_liabilities)
    - Private Manufacturer: Z' (X4 = book_equity / total_liabilities)
    - Non-Manufacturer: Z'' (4-ratio model, X4 = book_equity / total_liabilities)
    """
    profile = profile or {}
    sector = str(profile.get("sector", "manufacturing")).lower()
    is_public = bool(profile.get("is_public", False) or market_equity is not None)

    ta = period.get("total_assets")
    tl = period.get("total_liabilities")
    ca = period.get("current_assets")
    cl = period.get("current_liabilities")
    re = period.get("net_income")  # proxy for retained earnings if not separate
    ebit = period.get("ebit")
    rev = period.get("revenue")
    equity = period.get("equity")

    if ta is None or tl is None or ca is None or cl is None or ebit is None:
        return MetricResult(
            metric_id="altman_z_distance",
            name="Altman Z-Score",
            dimension="credit",
            status=MetricStatus.MISSING_INPUT,
            message="Missing required balance sheet or income statement concepts",
            unit="score",
        )

    if ta <= 0 or tl <= 0:
        return MetricResult(
            metric_id="altman_z_distance",
            name="Altman Z-Score",
            dimension="credit",
            value=-5.0,
            status=MetricStatus.FLAGGED,
            message="Total assets or liabilities zero or negative",
            unit="score",
        )

    wc = ca - cl
    x1 = wc / ta
    x2 = (re or 0.0) / ta
    x3 = ebit / ta
    x4 = (market_equity if is_public and market_equity is not None else (equity or 0.0)) / tl
    x5 = (rev or 0.0) / ta

    if "manufacturing" in sector and is_public and market_equity is not None:
        variant = "Z (Public Manufacturer)"
        cutoff_key = "Z"
        z_val = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    elif "manufacturing" in sector:
        variant = "Z' (Private Manufacturer)"
        cutoff_key = "Z'"
        z_val = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5
    else:
        variant = "Z'' (Non-Manufacturer)"
        cutoff_key = "Z''"
        z_val = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4

    distress_cutoff, safe_cutoff = _ALTMAN_CUTOFFS[cutoff_key]
    altman_score = interpolate_score(z_val, _altman_anchors(distress_cutoff, safe_cutoff))

    return MetricResult(
        metric_id="altman_z_distance",
        name=f"Altman {variant}",
        dimension="credit",
        value=z_val,
        status=MetricStatus.VALID,
        forced_score=altman_score,
        unit="score",
        inputs_used={
            "variant": variant,
            "distress_cutoff": distress_cutoff,
            "safe_cutoff": safe_cutoff,
            "x1": x1,
            "x2": x2,
            "x3": x3,
            "x4": x4,
            "x5": x5,
        },
    )


def calc_merton_dd(
    asset_value: float | None,
    total_debt: float | None,
    volatility: float | None,
    rf_rate: float = 0.05,
    horizon: float = 1.0,
) -> MetricResult:
    """Merton Distance-to-Default (Listed mode reference model)."""
    if asset_value is None or total_debt is None or volatility is None:
        return MetricResult(
            metric_id="merton_dd",
            name="Merton Distance-to-Default",
            dimension="credit",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; unobservable asset value, debt, or volatility",
            unit="sigmas",
        )

    if asset_value <= 0 or total_debt <= 0 or volatility <= 0 or horizon <= 0:
        return MetricResult(
            metric_id="merton_dd",
            name="Merton Distance-to-Default",
            dimension="credit",
            status=MetricStatus.INVALID_INPUT,
            message="Asset value, debt, volatility, and horizon must be strictly positive",
            unit="sigmas",
        )

    numerator = math.log(asset_value / total_debt) + (rf_rate - 0.5 * (volatility**2)) * horizon
    denominator = volatility * math.sqrt(horizon)
    dd = numerator / denominator

    # Cumulative normal CDF approximation for Probability of Default: Phi(-DD)
    pd_approx = 0.5 * math.erfc(dd / math.sqrt(2))

    return MetricResult(
        metric_id="merton_dd",
        name="Merton Distance-to-Default",
        dimension="credit",
        value=dd,
        status=MetricStatus.VALID,
        unit="sigmas",
        inputs_used={
            "asset_value": asset_value,
            "total_debt": total_debt,
            "volatility": volatility,
            "pd": pd_approx,
        },
    )
