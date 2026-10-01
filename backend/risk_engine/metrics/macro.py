"""Macro Dimension Metrics (Spec §8 & §17.1).

Pure-function implementations for inflation pass-through, interest rate environment gap,
FX volatility, and sector GDP sensitivity.
"""

from __future__ import annotations

import math

from backend.risk_engine.contracts import MetricResult, MetricStatus


def calc_inflation_passthrough(
    gross_margin_change_pp: float | None,
    cpi_change_pct: float | None,
) -> MetricResult:
    if gross_margin_change_pp is None or cpi_change_pct is None:
        return MetricResult(
            metric_id="inflation_passthrough",
            name="Inflation Pass-Through",
            dimension="macro",
            status=MetricStatus.MISSING_INPUT,
            message="Missing gross margin change or CPI change data",
            unit="percentage_points",
        )

    # Margin gap = gross margin change minus inflation rate
    margin_gap = gross_margin_change_pp - cpi_change_pct
    return MetricResult(
        metric_id="inflation_passthrough",
        name="Inflation Pass-Through",
        dimension="macro",
        value=margin_gap,
        status=MetricStatus.VALID,
        unit="percentage_points",
        inputs_used={
            "gross_margin_change_pp": gross_margin_change_pp,
            "cpi_change_pct": cpi_change_pct,
        },
    )


def calc_rate_environment(
    current_rate: float | None, trailing_median_rate: float | None
) -> MetricResult:
    if current_rate is None or trailing_median_rate is None:
        return MetricResult(
            metric_id="rate_environment",
            name="Interest Rate Environment Gap",
            dimension="macro",
            status=MetricStatus.MISSING_INPUT,
            message="Missing rate series data",
            unit="percentage_points",
        )

    gap = max(0.0, current_rate - trailing_median_rate)
    return MetricResult(
        metric_id="rate_environment",
        name="Interest Rate Environment Gap",
        dimension="macro",
        value=gap,
        status=MetricStatus.VALID,
        unit="percentage_points",
        inputs_used={"current_rate": current_rate, "trailing_median": trailing_median_rate},
    )


def calc_macro_fx_volatility(fx_daily_returns: list[float] | None) -> MetricResult:
    if not fx_daily_returns or len(fx_daily_returns) < 30:
        return MetricResult(
            metric_id="fx_volatility",
            name="Macro FX Volatility",
            dimension="macro",
            status=MetricStatus.UNAVAILABLE,
            message="Requires daily FX series (min 30 obs)",
            unit="percent",
        )

    n = len(fx_daily_returns)
    mean_r = sum(fx_daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in fx_daily_returns) / n
    annualized_vol = math.sqrt(variance) * math.sqrt(252) * 100.0

    return MetricResult(
        metric_id="fx_volatility",
        name="Macro FX Volatility",
        dimension="macro",
        value=annualized_vol,
        status=MetricStatus.VALID,
        unit="percent",
    )


def calc_gdp_sensitivity(sector: str, gdp_volatility: float = 1.0) -> MetricResult:
    sector_lower = sector.lower()
    if "manufacturing" in sector_lower:
        elasticity = 1.2
    elif "retail" in sector_lower:
        elasticity = 1.0
    else:  # services/saas
        elasticity = 0.8

    sensitivity_score = elasticity * gdp_volatility
    return MetricResult(
        metric_id="gdp_sensitivity",
        name="GDP Sensitivity",
        dimension="macro",
        value=sensitivity_score,
        status=MetricStatus.VALID,
        unit="index",
        inputs_used={"sector": sector, "elasticity": elasticity, "gdp_volatility": gdp_volatility},
    )
