"""Formula Registry for Quantitative Risk Engine (Spec §1, §17.1).

Central repository of metric definitions, band anchors, dimension assignments,
and piecewise-linear score interpolation functions.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from backend.risk_engine.contracts import REGISTRY_VERSION, MetricResult

__all__ = [
    "DEFAULT_DIMENSION_WEIGHTS",
    "DIMENSIONS",
    "REGISTRY_VERSION",
    "FormulaRegistry",
    "MetricDefinition",
    "build_default_registry",
    "interpolate_score",
]


_SCORE_MIN = 0.0
_SCORE_MAX = 100.0


def _clamp_score(score: float) -> float:
    """Clamp an interpolation result into the frozen 0-100 score range."""
    return max(_SCORE_MIN, min(_SCORE_MAX, float(score)))


def interpolate_score(value: float | None, anchors: list[tuple[float, float]]) -> float | None:
    """Piecewise-linear interpolation mapping metric raw value to 0-100 risk score.

    Clamped at endpoints. Higher score = higher risk.
    """
    if value is None or not math.isfinite(value):
        return None

    if not anchors:
        return 50.0

    sorted_anchors = sorted(anchors, key=lambda x: x[0])

    if value <= sorted_anchors[0][0]:
        return _clamp_score(sorted_anchors[0][1])
    if value >= sorted_anchors[-1][0]:
        return _clamp_score(sorted_anchors[-1][1])

    for i in range(len(sorted_anchors) - 1):
        x0, y0 = sorted_anchors[i]
        x1, y1 = sorted_anchors[i + 1]
        if x0 <= value <= x1:
            if x1 == x0:
                return _clamp_score(y0)
            t = (value - x0) / (x1 - x0)
            return _clamp_score(y0 + t * (y1 - y0))

    return _clamp_score(sorted_anchors[-1][1])


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    name: str
    dimension: str
    unit: str
    anchors: list[tuple[float, float]]
    calculator: Callable[..., MetricResult]
    default_weight: float = 1.0
    description: str = ""


# ``REGISTRY_VERSION`` is re-exported from contracts (single definition site).

# --- Dimension Metadata ---
DIMENSIONS: dict[str, str] = {
    "financial_strength": "Financial Strength",
    "liquidity": "Liquidity",
    "market": "Market / External-Price Exposure",
    "credit": "Credit",
    "operational": "Operational",
    "concentration": "Concentration",
    "macro": "Macroeconomic Exposure",
}

DEFAULT_DIMENSION_WEIGHTS: dict[str, float] = {
    "financial_strength": 1.0 / 7.0,
    "liquidity": 1.0 / 7.0,
    "market": 1.0 / 7.0,
    "credit": 1.0 / 7.0,
    "operational": 1.0 / 7.0,
    "concentration": 1.0 / 7.0,
    "macro": 1.0 / 7.0,
}


class FormulaRegistry:
    """Central registry holding all metric definitions and scoring anchors."""

    def __init__(self) -> None:
        self._definitions: dict[str, MetricDefinition] = {}

    def register(self, definition: MetricDefinition) -> None:
        self._definitions[definition.metric_id] = definition

    def get(self, metric_id: str) -> MetricDefinition | None:
        return self._definitions.get(metric_id)

    def list_metrics(self) -> list[MetricDefinition]:
        return list(self._definitions.values())

    def list_by_dimension(self, dimension: str) -> list[MetricDefinition]:
        return [d for d in self._definitions.values() if d.dimension == dimension]


def build_default_registry() -> FormulaRegistry:
    from backend.risk_engine.metrics import (
        calc_altman_z,
        calc_beta,
        calc_cash_ratio,
        calc_cash_runway_months,
        calc_ccc,
        calc_commodity_exposure_score,
        calc_cr1,
        calc_cr3,
        calc_current_ratio,
        calc_debt_to_ebitda,
        calc_debt_to_equity,
        calc_dio,
        calc_dpo,
        calc_dscr,
        calc_dso,
        calc_equity_volatility,
        calc_es_95,
        calc_fx_exposure_score,
        calc_gdp_sensitivity,
        calc_gross_margin,
        calc_hhi,
        calc_inflation_passthrough,
        calc_interest_coverage,
        calc_macro_fx_volatility,
        calc_merton_dd,
        calc_net_margin,
        calc_operating_margin,
        calc_opex_rigidity,
        calc_quick_ratio,
        calc_rate_environment,
        calc_rate_sensitivity,
        calc_receivable_trend,
        calc_revenue_volatility,
        calc_roa,
        calc_roe,
        calc_single_source_flags,
        calc_st_obligation_coverage,
        calc_var_95,
    )

    reg = FormulaRegistry()

    # Financial Strength
    reg.register(
        MetricDefinition(
            "gross_margin",
            "Gross Margin",
            "financial_strength",
            "percent",
            [(10.0, 90.0), (20.0, 65.0), (30.0, 45.0), (40.0, 25.0)],
            calc_gross_margin,
        )
    )
    reg.register(
        MetricDefinition(
            "operating_margin",
            "Operating Margin",
            "financial_strength",
            "percent",
            [(2.0, 90.0), (5.0, 70.0), (10.0, 45.0), (15.0, 25.0), (20.0, 15.0)],
            calc_operating_margin,
        )
    )
    reg.register(
        MetricDefinition(
            "net_margin",
            "Net Margin",
            "financial_strength",
            "percent",
            [(-10.0, 100.0), (0.0, 85.0), (3.0, 65.0), (6.0, 45.0), (10.0, 25.0), (15.0, 15.0)],
            calc_net_margin,
        )
    )
    reg.register(
        MetricDefinition(
            "roa",
            "Return on Assets",
            "financial_strength",
            "percent",
            [(-5.0, 95.0), (0.0, 80.0), (3.0, 55.0), (6.0, 35.0), (10.0, 15.0)],
            calc_roa,
        )
    )
    reg.register(
        MetricDefinition(
            "roe",
            "Return on Equity",
            "financial_strength",
            "percent",
            [(-10.0, 95.0), (0.0, 80.0), (8.0, 55.0), (15.0, 35.0), (25.0, 15.0)],
            calc_roe,
        )
    )
    reg.register(
        MetricDefinition(
            "debt_to_equity",
            "Debt to Equity",
            "financial_strength",
            "ratio",
            [(0.5, 15.0), (1.0, 30.0), (2.0, 55.0), (3.0, 75.0), (4.0, 90.0)],
            calc_debt_to_equity,
        )
    )
    reg.register(
        MetricDefinition(
            "debt_to_ebitda",
            "Debt to EBITDA",
            "financial_strength",
            "ratio",
            [(1.0, 15.0), (3.0, 35.0), (5.0, 60.0), (7.0, 85.0)],
            calc_debt_to_ebitda,
        )
    )
    reg.register(
        MetricDefinition(
            "interest_coverage",
            "Interest Coverage",
            "financial_strength",
            "ratio",
            [(1.0, 95.0), (2.0, 70.0), (3.0, 45.0), (5.0, 20.0), (8.0, 10.0)],
            calc_interest_coverage,
        )
    )
    reg.register(
        MetricDefinition(
            "dscr",
            "Debt Service Coverage Ratio",
            "financial_strength",
            "ratio",
            [(0.8, 95.0), (1.1, 75.0), (1.4, 45.0), (1.8, 20.0), (2.5, 10.0)],
            calc_dscr,
        )
    )

    # Liquidity
    reg.register(
        MetricDefinition(
            "current_ratio",
            "Current Ratio",
            "liquidity",
            "ratio",
            [(0.5, 95.0), (1.0, 75.0), (1.5, 45.0), (2.0, 25.0), (3.0, 10.0)],
            calc_current_ratio,
        )
    )
    reg.register(
        MetricDefinition(
            "quick_ratio",
            "Quick Ratio",
            "liquidity",
            "ratio",
            [(0.3, 95.0), (0.8, 70.0), (1.2, 40.0), (1.5, 20.0)],
            calc_quick_ratio,
        )
    )
    reg.register(
        MetricDefinition(
            "cash_ratio",
            "Cash Ratio",
            "liquidity",
            "ratio",
            [(0.1, 95.0), (0.3, 70.0), (0.5, 45.0), (1.0, 15.0)],
            calc_cash_ratio,
        )
    )
    reg.register(
        MetricDefinition(
            "cash_runway_months",
            "Cash Runway",
            "liquidity",
            "months",
            [(0.0, 100.0), (3.0, 90.0), (6.0, 70.0), (12.0, 45.0), (24.0, 20.0)],
            calc_cash_runway_months,
        )
    )
    reg.register(
        MetricDefinition(
            "st_obligation_coverage",
            "ST Obligation Coverage",
            "liquidity",
            "ratio",
            [(0.2, 95.0), (0.5, 75.0), (1.0, 50.0), (1.5, 30.0), (2.0, 15.0)],
            calc_st_obligation_coverage,
        )
    )

    # Market Risk
    reg.register(
        MetricDefinition(
            "rate_sensitivity",
            "Rate Sensitivity",
            "market",
            "percent",
            [(2.0, 20.0), (5.0, 40.0), (10.0, 65.0), (15.0, 85.0)],
            calc_rate_sensitivity,
        )
    )
    reg.register(
        MetricDefinition(
            "fx_exposure_score",
            "FX Exposure Score",
            "market",
            "index",
            [(10.0, 20.0), (25.0, 40.0), (40.0, 60.0), (60.0, 85.0)],
            calc_fx_exposure_score,
        )
    )
    reg.register(
        MetricDefinition(
            "commodity_exposure_score",
            "Commodity Exposure",
            "market",
            "index",
            [(10.0, 20.0), (25.0, 40.0), (40.0, 60.0), (60.0, 85.0)],
            calc_commodity_exposure_score,
        )
    )
    reg.register(
        MetricDefinition(
            "revenue_volatility",
            "Revenue Volatility",
            "market",
            "percent",
            [(5.0, 20.0), (10.0, 35.0), (20.0, 55.0), (30.0, 75.0)],
            calc_revenue_volatility,
        )
    )
    reg.register(
        MetricDefinition(
            "equity_volatility",
            "Equity Volatility",
            "market",
            "percent",
            [(15.0, 15.0), (25.0, 30.0), (40.0, 50.0), (60.0, 70.0), (80.0, 85.0)],
            calc_equity_volatility,
        )
    )
    reg.register(
        MetricDefinition(
            "beta",
            "Beta",
            "market",
            "ratio",
            [(0.5, 20.0), (1.0, 30.0), (1.5, 50.0), (2.0, 70.0)],
            calc_beta,
        )
    )
    reg.register(
        MetricDefinition(
            "var_95",
            "VaR 95%",
            "market",
            "percent",
            [(2.0, 20.0), (5.0, 40.0), (10.0, 65.0), (15.0, 85.0)],
            calc_var_95,
        )
    )
    reg.register(
        MetricDefinition(
            "es_95",
            "Expected Shortfall 95%",
            "market",
            "percent",
            [(2.0, 20.0), (5.0, 40.0), (10.0, 65.0), (15.0, 85.0)],
            calc_es_95,
        )
    )

    # Credit
    reg.register(
        MetricDefinition(
            "dso",
            "Days Sales Outstanding",
            "credit",
            "days",
            [(30.0, 20.0), (45.0, 35.0), (60.0, 50.0), (90.0, 70.0), (120.0, 85.0)],
            calc_dso,
        )
    )
    reg.register(
        MetricDefinition(
            "receivables_concentration",
            "Receivables Concentration",
            "credit",
            "ratio",
            [(0.15, 15.0), (0.25, 35.0), (0.45, 60.0), (0.6, 80.0)],
            calc_hhi,
        )
    )
    reg.register(
        MetricDefinition(
            "receivable_trend",
            "Receivable Trend",
            "credit",
            "days_per_year",
            [(0.0, 25.0), (10.0, 40.0), (20.0, 55.0), (30.0, 70.0)],
            calc_receivable_trend,
        )
    )
    reg.register(
        MetricDefinition(
            "altman_z_distance",
            "Altman Z-Score",
            "credit",
            "score",
            # Frozen original-Z mapping (risk-engine.md §5): Z>=2.99 -> 10; Z=1.81 -> 60;
            # below 1.81 linear to 100 (reaching 100 at Z=0). Z'/Z'' use their own
            # cutoffs mapped proportionally; the calculator applies those via forced_score.
            [(0.0, 100.0), (1.81, 60.0), (2.99, 10.0)],
            calc_altman_z,
            description=(
                "Original Z for public manufacturers; Z' (cutoffs 2.675/1.23) for private "
                "manufacturers; Z'' (cutoffs 2.6/1.1) for non-manufacturers. Never mixed."
            ),
        )
    )
    reg.register(
        MetricDefinition(
            "merton_dd",
            "Merton DD",
            "credit",
            "sigmas",
            [(0.5, 90.0), (1.0, 70.0), (2.0, 45.0), (3.0, 20.0)],
            calc_merton_dd,
        )
    )

    # Operational
    reg.register(
        MetricDefinition(
            "dio",
            "Days Inventory Outstanding",
            "operational",
            "days",
            [(30.0, 20.0), (60.0, 40.0), (90.0, 60.0), (120.0, 75.0)],
            calc_dio,
        )
    )
    reg.register(
        MetricDefinition(
            "dpo",
            "Days Payables Outstanding",
            "operational",
            "days",
            [(15.0, 60.0), (30.0, 40.0), (45.0, 25.0), (60.0, 20.0), (90.0, 35.0), (120.0, 50.0)],
            calc_dpo,
        )
    )
    reg.register(
        MetricDefinition(
            "ccc",
            "Cash Conversion Cycle",
            "operational",
            "days",
            [(15.0, 20.0), (30.0, 30.0), (45.0, 45.0), (60.0, 60.0), (90.0, 80.0), (120.0, 90.0)],
            calc_ccc,
        )
    )
    reg.register(
        MetricDefinition(
            "supplier_concentration",
            "Supplier Concentration",
            "operational",
            "ratio",
            [(0.15, 15.0), (0.25, 35.0), (0.45, 60.0), (0.6, 80.0)],
            calc_hhi,
        )
    )
    reg.register(
        MetricDefinition(
            "opex_rigidity",
            "Opex Rigidity",
            "operational",
            "ratio",
            [(0.3, 20.0), (0.5, 40.0), (0.7, 60.0), (0.85, 80.0)],
            calc_opex_rigidity,
        )
    )
    reg.register(
        MetricDefinition(
            "single_source_flags",
            "Single Source Flags",
            "operational",
            "count",
            [(0.0, 10.0), (1.0, 55.0), (2.0, 80.0), (3.0, 95.0)],
            calc_single_source_flags,
        )
    )

    # Concentration
    reg.register(
        MetricDefinition(
            "hhi",
            "HHI Concentration",
            "concentration",
            "ratio",
            [(0.15, 15.0), (0.25, 35.0), (0.45, 60.0), (0.6, 80.0)],
            calc_hhi,
        )
    )
    reg.register(
        MetricDefinition(
            "cr1",
            "Top-1 Concentration",
            "concentration",
            "ratio",
            [(0.3, 20.0), (0.5, 45.0), (0.7, 70.0), (0.9, 90.0)],
            calc_cr1,
        )
    )
    reg.register(
        MetricDefinition(
            "cr3",
            "Top-3 Concentration",
            "concentration",
            "ratio",
            [(0.5, 20.0), (0.7, 40.0), (0.9, 65.0), (1.0, 75.0)],
            calc_cr3,
        )
    )

    # Macro
    reg.register(
        MetricDefinition(
            "inflation_passthrough",
            "Inflation Pass-Through",
            "macro",
            "percentage_points",
            [(-5.0, 75.0), (-2.0, 45.0), (0.0, 15.0)],
            calc_inflation_passthrough,
        )
    )
    reg.register(
        MetricDefinition(
            "rate_environment",
            "Rate Environment Gap",
            "macro",
            "percentage_points",
            [(0.0, 15.0), (2.0, 35.0), (4.0, 60.0), (6.0, 80.0)],
            calc_rate_environment,
        )
    )
    reg.register(
        MetricDefinition(
            "fx_volatility",
            "FX Volatility",
            "macro",
            "percent",
            [(3.0, 20.0), (6.0, 40.0), (10.0, 65.0)],
            calc_macro_fx_volatility,
        )
    )
    reg.register(
        MetricDefinition(
            "gdp_sensitivity",
            "GDP Sensitivity",
            "macro",
            "index",
            [(0.5, 20.0), (1.0, 45.0), (1.5, 70.0)],
            calc_gdp_sensitivity,
        )
    )

    return reg
