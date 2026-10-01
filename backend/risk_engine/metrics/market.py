"""Market / External-Price Exposure Metrics (Spec §4 & §17.1).

Pure-function implementations for interest rate sensitivity, FX exposure,
commodity exposure, revenue volatility, equity volatility, Beta, VaR 95%, and Expected Shortfall.
"""

from __future__ import annotations

import math
from typing import Any

from backend.risk_engine.contracts import MetricResult, MetricStatus


def calc_rate_sensitivity(period: dict[str, Any]) -> MetricResult:
    rate_exp = period.get("rate_exposure") or {}
    floating_share = (
        rate_exp.get("floating_debt_share", 0.5)
        if isinstance(rate_exp, dict)
        else getattr(rate_exp, "floating_debt_share", 0.5)
    )
    total_debt = period.get("total_debt") or 0.0
    ebitda = period.get("ebitda")

    if ebitda is None:
        return MetricResult(
            metric_id="rate_sensitivity",
            name="Interest Rate Sensitivity",
            dimension="market",
            status=MetricStatus.MISSING_INPUT,
            message="Missing ebitda",
            unit="percent",
        )

    if ebitda <= 0:
        return MetricResult(
            metric_id="rate_sensitivity",
            name="Interest Rate Sensitivity",
            dimension="market",
            value=100.0,
            status=MetricStatus.FLAGGED,
            message="EBITDA is zero or negative (undefined sensitivity)",
            forced_score=100.0,
            unit="percent",
        )

    interest_increase = total_debt * floating_share * 0.01
    sensitivity_pct = (interest_increase / ebitda) * 100.0

    return MetricResult(
        metric_id="rate_sensitivity",
        name="Interest Rate Sensitivity",
        dimension="market",
        value=sensitivity_pct,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={
            "total_debt": total_debt,
            "floating_share": floating_share,
            "ebitda": ebitda,
        },
    )


def calc_fx_exposure_score(period: dict[str, Any], pass_through: float = 0.3) -> MetricResult:
    fx_exp = period.get("fx_exposure") or {}
    if isinstance(fx_exp, dict):
        import_share = fx_exp.get("import_cost_share", 0.0)
        foreign_rev_share = fx_exp.get("foreign_revenue_share", 0.0)
    else:
        import_share = getattr(fx_exp, "import_cost_share", 0.0)
        foreign_rev_share = getattr(fx_exp, "foreign_revenue_share", 0.0)

    score_val = 100.0 * (0.6 * import_share + 0.4 * foreign_rev_share) * (1.0 - pass_through)
    return MetricResult(
        metric_id="fx_exposure_score",
        name="FX Exposure Score",
        dimension="market",
        value=score_val,
        status=MetricStatus.VALID,
        unit="index",
        inputs_used={
            "import_cost_share": import_share,
            "foreign_revenue_share": foreign_rev_share,
            "pass_through": pass_through,
        },
    )


def calc_commodity_exposure_score(
    period: dict[str, Any], pass_through: float = 0.3
) -> MetricResult:
    comm_exp = period.get("commodity_exposure")
    if not comm_exp:
        return MetricResult(
            metric_id="commodity_exposure_score",
            name="Commodity Exposure Score",
            dimension="market",
            value=0.0,
            status=MetricStatus.VALID,
            message="No commodity exposure reported",
            unit="index",
        )

    if isinstance(comm_exp, dict):
        cost_share = comm_exp.get("cost_share", 0.0)
    else:
        cost_share = getattr(comm_exp, "cost_share", 0.0)

    score_val = 100.0 * cost_share * (1.0 - pass_through)
    return MetricResult(
        metric_id="commodity_exposure_score",
        name="Commodity Exposure Score",
        dimension="market",
        value=score_val,
        status=MetricStatus.VALID,
        unit="index",
        inputs_used={"cost_share": cost_share, "pass_through": pass_through},
    )


def calc_revenue_volatility(history: list[dict[str, Any]]) -> MetricResult:
    if not history or len(history) < 8:
        return MetricResult(
            metric_id="revenue_volatility",
            name="Revenue Volatility",
            dimension="market",
            status=MetricStatus.INSUFFICIENT_HISTORY,
            message="Requires at least 8 periods",
            unit="percent",
        )

    revenues: list[float] = [
        float(p["revenue"]) for p in history if p.get("revenue") is not None and p["revenue"] > 0
    ]
    if len(revenues) < 8:
        return MetricResult(
            metric_id="revenue_volatility",
            name="Revenue Volatility",
            dimension="market",
            status=MetricStatus.INSUFFICIENT_HISTORY,
            message="Insufficient positive revenue periods",
            unit="percent",
        )

    returns = [(revenues[i] - revenues[i - 1]) / revenues[i - 1] for i in range(1, len(revenues))]
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_dev = math.sqrt(variance)
    annualized_vol = std_dev * math.sqrt(12) * 100.0

    return MetricResult(
        metric_id="revenue_volatility",
        name="Revenue Volatility",
        dimension="market",
        value=annualized_vol,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={"obs_count": len(returns)},
    )


def calc_equity_volatility(daily_returns: list[float] | None) -> MetricResult:
    if not daily_returns or len(daily_returns) < 60:
        return MetricResult(
            metric_id="equity_volatility",
            name="Equity Volatility",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires at least 60 daily return observations",
            unit="percent",
        )

    clean_returns = [r for r in daily_returns if r is not None]
    if len(clean_returns) < 60:
        return MetricResult(
            metric_id="equity_volatility",
            name="Equity Volatility",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires at least 60 valid return observations",
            unit="percent",
        )

    mean_ret = sum(clean_returns) / len(clean_returns)
    variance = sum((r - mean_ret) ** 2 for r in clean_returns) / len(clean_returns)
    std_dev = math.sqrt(variance)
    annualized_vol = std_dev * math.sqrt(252) * 100.0

    return MetricResult(
        metric_id="equity_volatility",
        name="Equity Volatility",
        dimension="market",
        value=annualized_vol,
        status=MetricStatus.VALID,
        unit="percent",
    )


def calc_beta(
    asset_returns: list[float] | None, market_returns: list[float] | None
) -> MetricResult:
    if (
        not asset_returns
        or not market_returns
        or len(asset_returns) < 120
        or len(asset_returns) != len(market_returns)
    ):
        return MetricResult(
            metric_id="beta",
            name="Beta",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires matching asset and market series (min 120 obs)",
            unit="ratio",
        )

    clean_a = [r for r in asset_returns if r is not None]
    clean_m = [r for r in market_returns if r is not None]
    if len(clean_a) < 120 or len(clean_a) != len(clean_m):
        return MetricResult(
            metric_id="beta",
            name="Beta",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires matching asset and market series (min 120 obs)",
            unit="ratio",
        )

    n = len(clean_a)
    mean_a = sum(clean_a) / n
    mean_m = sum(clean_m) / n
    cov = sum((clean_a[i] - mean_a) * (clean_m[i] - mean_m) for i in range(n)) / n
    var_m = sum((clean_m[i] - mean_m) ** 2 for i in range(n)) / n

    if var_m == 0:
        return MetricResult(
            metric_id="beta",
            name="Beta",
            dimension="market",
            status=MetricStatus.INVALID_INPUT,
            message="Market variance is zero",
            unit="ratio",
        )

    beta_val = cov / var_m
    return MetricResult(
        metric_id="beta",
        name="Beta",
        dimension="market",
        value=beta_val,
        status=MetricStatus.VALID,
        unit="ratio",
    )


def calc_var_95(returns: list[float] | None) -> MetricResult:
    if not returns or len(returns) < 60:
        return MetricResult(
            metric_id="var_95",
            name="Value at Risk (VaR 95%)",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires daily returns series (min 60 obs)",
            unit="percent",
        )

    clean_returns = [r for r in returns if r is not None]
    if len(clean_returns) < 60:
        return MetricResult(
            metric_id="var_95",
            name="Value at Risk (VaR 95%)",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires daily returns series (min 60 obs)",
            unit="percent",
        )

    sorted_losses = sorted([-1.0 * r for r in clean_returns])
    index = int(0.95 * len(sorted_losses))
    var_val = sorted_losses[min(index, len(sorted_losses) - 1)] * 100.0

    return MetricResult(
        metric_id="var_95",
        name="Value at Risk (VaR 95%)",
        dimension="market",
        value=max(0.0, var_val),
        status=MetricStatus.VALID,
        unit="percent",
    )


def calc_es_95(returns: list[float] | None) -> MetricResult:
    if not returns or len(returns) < 60:
        return MetricResult(
            metric_id="es_95",
            name="Expected Shortfall (ES 95%)",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires daily returns series (min 60 obs)",
            unit="percent",
        )

    clean_returns = [r for r in returns if r is not None]
    if len(clean_returns) < 60:
        return MetricResult(
            metric_id="es_95",
            name="Expected Shortfall (ES 95%)",
            dimension="market",
            status=MetricStatus.UNAVAILABLE,
            message="Listed mode only; requires daily returns series (min 60 obs)",
            unit="percent",
        )

    sorted_losses = sorted([-1.0 * r for r in clean_returns])
    index = int(0.95 * len(sorted_losses))
    tail_losses = sorted_losses[index:]
    if not tail_losses:
        es_val = sorted_losses[-1] * 100.0
    else:
        es_val = (sum(tail_losses) / len(tail_losses)) * 100.0

    return MetricResult(
        metric_id="es_95",
        name="Expected Shortfall (ES 95%)",
        dimension="market",
        value=max(0.0, es_val),
        status=MetricStatus.VALID,
        unit="percent",
    )
