"""Assemble RiskEngineMarketInputs from loaded Phase 3 series (Stage 5 D18-D20).

The caller loads ``MarketSeries`` / ``MacroSeries`` objects first (HTTP, cache,
or SQL at the application boundary); this module only performs deterministic
transformations. The risk engine never imports this module's Phase 3 helpers —
it receives the built ``RiskEngineMarketInputs`` value instead (R3).
"""

from __future__ import annotations

from backend.data_engine.ingest.base import MacroSeries, MarketSeries
from backend.data_engine.macro_inputs import (
    cpi_change_24m,
    fedfunds_current_and_median,
    gross_margin_change_24m,
)
from backend.data_engine.market_inputs import (
    align_beta_legs,
    aligned_returns_from_closes,
    provenance_for_macro,
    provenance_for_market,
)
from backend.risk_engine.contracts import (
    AlignedSeries,
    RiskEngineMarketInputs,
    SeriesProvenance,
)

__all__ = ["build_market_inputs"]


def build_market_inputs(
    *,
    equity: MarketSeries | None = None,
    benchmark: MarketSeries | None = None,
    fx: MarketSeries | None = None,
    cpi: MacroSeries | None = None,
    fedfunds: MacroSeries | None = None,
    periods: list[dict[str, object]] | None = None,
    gdp_volatility: float | None = None,
) -> RiskEngineMarketInputs:
    """Build typed market/macro inputs from loaded Phase 3 series objects."""
    provenance: dict[str, SeriesProvenance] = {}
    equity_leg: AlignedSeries | None = None
    benchmark_leg: AlignedSeries | None = None
    fx_leg: AlignedSeries | None = None

    if equity is not None and benchmark is not None:
        equity_leg, benchmark_leg, _ = align_beta_legs(equity, benchmark)
        provenance["equity_returns"] = provenance_for_market(equity)
        provenance["benchmark_returns"] = provenance_for_market(benchmark)
    elif equity is not None:
        equity_leg = aligned_returns_from_closes(equity)
        provenance["equity_returns"] = provenance_for_market(equity)
    elif benchmark is not None:
        benchmark_leg = aligned_returns_from_closes(benchmark)
        provenance["benchmark_returns"] = provenance_for_market(benchmark)

    if fx is not None:
        fx_leg = aligned_returns_from_closes(fx)
        provenance["fx_returns"] = provenance_for_market(fx)

    cpi_change: float | None = None
    if cpi is not None:
        cpi_change = cpi_change_24m(cpi)
        provenance["cpi"] = provenance_for_macro(cpi)

    margin_change: float | None = None
    if periods is not None:
        margin_change = gross_margin_change_24m(periods)

    fed_current: float | None = None
    fed_median: float | None = None
    if fedfunds is not None:
        fed_current, fed_median = fedfunds_current_and_median(fedfunds)
        provenance["fedfunds"] = provenance_for_macro(fedfunds)

    return RiskEngineMarketInputs(
        equity_returns=equity_leg,
        benchmark_returns=benchmark_leg,
        fx_returns=fx_leg,
        cpi_change_pct_24m=cpi_change,
        gross_margin_change_pp_24m=margin_change,
        fedfunds_current=fed_current,
        fedfunds_trailing_5y_median=fed_median,
        gdp_volatility=gdp_volatility,
        provenance=provenance,
    )
