"""Metrics Package Init.

Exports metric functions across all 7 risk dimensions.
"""

from backend.risk_engine.metrics.concentration import calc_cr1, calc_cr3, calc_hhi
from backend.risk_engine.metrics.credit import (
    calc_altman_z,
    calc_dso,
    calc_merton_dd,
    calc_receivable_trend,
)
from backend.risk_engine.metrics.financial_strength import (
    calc_debt_to_ebitda,
    calc_debt_to_equity,
    calc_dscr,
    calc_gross_margin,
    calc_interest_coverage,
    calc_net_margin,
    calc_operating_margin,
    calc_roa,
    calc_roe,
)
from backend.risk_engine.metrics.liquidity import (
    calc_cash_ratio,
    calc_cash_runway_months,
    calc_current_ratio,
    calc_quick_ratio,
    calc_st_obligation_coverage,
)
from backend.risk_engine.metrics.macro import (
    calc_gdp_sensitivity,
    calc_inflation_passthrough,
    calc_macro_fx_volatility,
    calc_rate_environment,
)
from backend.risk_engine.metrics.market import (
    calc_beta,
    calc_commodity_exposure_score,
    calc_equity_volatility,
    calc_es_95,
    calc_fx_exposure_score,
    calc_rate_sensitivity,
    calc_revenue_volatility,
    calc_var_95,
)
from backend.risk_engine.metrics.operational import (
    calc_ccc,
    calc_dio,
    calc_dpo,
    calc_opex_rigidity,
    calc_single_source_flags,
)

__all__ = [
    "calc_gross_margin",
    "calc_operating_margin",
    "calc_net_margin",
    "calc_roa",
    "calc_roe",
    "calc_debt_to_equity",
    "calc_debt_to_ebitda",
    "calc_interest_coverage",
    "calc_dscr",
    "calc_current_ratio",
    "calc_quick_ratio",
    "calc_cash_ratio",
    "calc_cash_runway_months",
    "calc_st_obligation_coverage",
    "calc_rate_sensitivity",
    "calc_fx_exposure_score",
    "calc_commodity_exposure_score",
    "calc_revenue_volatility",
    "calc_equity_volatility",
    "calc_beta",
    "calc_var_95",
    "calc_es_95",
    "calc_dso",
    "calc_receivable_trend",
    "calc_altman_z",
    "calc_merton_dd",
    "calc_dio",
    "calc_dpo",
    "calc_ccc",
    "calc_opex_rigidity",
    "calc_single_source_flags",
    "calc_hhi",
    "calc_cr1",
    "calc_cr3",
    "calc_inflation_passthrough",
    "calc_rate_environment",
    "calc_macro_fx_volatility",
    "calc_gdp_sensitivity",
]
