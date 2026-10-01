"""Quantitative Risk Engine Pipeline Coordinator (Spec §17).

High-level interface connecting canonical dataset inputs to formula calculations,
scoring, dimension aggregation, additive contribution tracking, and sensitivity analysis.
"""

from __future__ import annotations

from typing import Any

from backend.risk_engine.contracts import (
    AlignedSeries,
    DimensionResult,
    MetricResult,
    RiskAssessmentReport,
    RiskEngineMarketInputs,
    SeriesProvenance,
    WeightsRef,
)
from backend.risk_engine.registry import (
    REGISTRY_VERSION,
    FormulaRegistry,
    build_default_registry,
)
from backend.risk_engine.scoring import (
    aggregate_composite,
    aggregate_dimension,
    score_metric,
)
from backend.risk_engine.sensitivity import run_sensitivity_analysis


class QuantitativeRiskEngine:
    """Deterministic Quantitative Risk Engine."""

    _MARKET_PROVENANCE_KEYS: dict[str, str] = {
        "equity_volatility": "equity_returns",
        "var_95": "equity_returns",
        "es_95": "equity_returns",
        "beta": "benchmark_returns",
        "fx_volatility": "fx_returns",
        "inflation_passthrough": "cpi",
        "rate_environment": "fedfunds",
    }

    def __init__(self, registry: FormulaRegistry | None = None) -> None:
        self.registry = registry or build_default_registry()

    @staticmethod
    def _check_leg_currencies(market_inputs: RiskEngineMarketInputs) -> None:
        """Reject mixed-currency beta legs explicitly (approved Q-B4)."""
        equity = market_inputs.equity_returns
        benchmark = market_inputs.benchmark_returns
        if equity is None or benchmark is None:
            return
        if (
            equity.currency is not None
            and benchmark.currency is not None
            and equity.currency != benchmark.currency
        ):
            raise ValueError(
                "asset and benchmark series currencies differ; "
                "no silent FX conversion inside risk calculations"
            )

    @classmethod
    def _stamp_market_provenance(
        cls,
        scored_res: MetricResult,
        metric_id: str,
        market_provenance: dict[str, SeriesProvenance],
        joined_obs: int | None = None,
    ) -> None:
        """Record Stage 5 input provenance in ``inputs_used`` (no overwrite)."""
        key = cls._MARKET_PROVENANCE_KEYS.get(metric_id)
        if key is None:
            return
        provenance = market_provenance.get(key)
        if provenance is None:
            return
        info = scored_res.inputs_used
        if metric_id == "beta":
            asset = market_provenance.get("equity_returns")
            if asset is not None:
                info.setdefault("asset_symbol", asset.symbol_or_series_id)
                info.setdefault("asset_source", asset.source)
            info.setdefault("benchmark_symbol", provenance.symbol_or_series_id)
            info.setdefault("benchmark_source", provenance.source)
            if joined_obs is not None:
                info.setdefault("joined_obs", joined_obs)
        else:
            info.setdefault("series_id", provenance.symbol_or_series_id)
            info.setdefault("source", provenance.source)
        if provenance.as_of is not None:
            info.setdefault("as_of", provenance.as_of.isoformat())
        info.setdefault("observation_count", provenance.observation_count)

    def evaluate_company(
        self,
        dataset: Any,
        custom_weights: dict[str, float] | None = None,
        market_series: list[float] | None = None,
        market_inputs: RiskEngineMarketInputs | None = None,
        weights_ref: WeightsRef | None = None,
    ) -> RiskAssessmentReport:
        """Run full quantitative risk evaluation on a canonical company dataset.

        Stage 5 routing (D18-D20): ``market_inputs`` carries the typed
        equity/benchmark/FX return legs plus pre-aggregated macro scalars.
        ``market_series`` is a deprecated legacy alias: it feeds the equity-leg
        metrics only (never beta — a caller-supplied benchmark is required, so
        the old ``calc_beta(market_series, market_series)`` defect cannot recur).
        ``weights_ref`` is contract preparation for Phase 10 persistence only.
        """
        if market_inputs is not None and market_series is not None:
            raise ValueError("pass market_inputs or market_series, not both")
        if hasattr(dataset, "model_dump"):
            data_dict = dataset.model_dump(mode="python")
        elif isinstance(dataset, dict):
            data_dict = dataset
        else:
            raise TypeError("dataset must be a CompanyDataset object or dictionary")

        profile = data_dict.get("profile", {})
        periods = data_dict.get("periods", [])

        if not periods:
            raise ValueError("Company dataset contains no financial periods")

        if market_inputs is None and market_series is not None:
            market_inputs = RiskEngineMarketInputs(
                equity_returns=AlignedSeries(returns=list(market_series)),
            )

        equity_returns = (
            market_inputs.equity_returns.returns
            if market_inputs is not None and market_inputs.equity_returns is not None
            else None
        )
        benchmark_returns = (
            market_inputs.benchmark_returns.returns
            if market_inputs is not None and market_inputs.benchmark_returns is not None
            else None
        )
        fx_returns = (
            market_inputs.fx_returns.returns
            if market_inputs is not None and market_inputs.fx_returns is not None
            else None
        )
        if market_inputs is not None:
            self._check_leg_currencies(market_inputs)
        market_provenance = market_inputs.provenance if market_inputs is not None else {}
        cpi_change = market_inputs.cpi_change_pct_24m if market_inputs is not None else None
        margin_change = (
            market_inputs.gross_margin_change_pp_24m if market_inputs is not None else None
        )
        fed_current = market_inputs.fedfunds_current if market_inputs is not None else None
        fed_median = (
            market_inputs.fedfunds_trailing_5y_median if market_inputs is not None else None
        )
        gdp_volatility = market_inputs.gdp_volatility if market_inputs is not None else None
        joined_beta_obs: int | None = None
        if (
            market_inputs is not None
            and market_inputs.equity_returns is not None
            and market_inputs.benchmark_returns is not None
        ):
            joined_beta_obs = len(market_inputs.equity_returns.returns)

        if weights_ref is not None and weights_ref.weights and custom_weights is None:
            custom_weights = dict(weights_ref.weights)

        latest_period = periods[-1]
        as_of_date = str(latest_period.get("period_end", "unknown"))
        company_name = profile.get("name", "Unknown Company")
        company_id = str(profile.get("id", "")) or None

        # Execute metric calculators by dimension
        dimension_metrics: dict[str, list[MetricResult]] = {}
        all_metrics: list[MetricResult] = []

        dso_def = self.registry.get("dso")
        dio_def = self.registry.get("dio")
        dpo_def = self.registry.get("dpo")

        dso_val = dso_def.calculator(latest_period).value if dso_def else None
        dio_val = dio_def.calculator(latest_period).value if dio_def else None
        dpo_val = dpo_def.calculator(latest_period).value if dpo_def else None

        for metric_def in self.registry.list_metrics():
            m_id = metric_def.metric_id
            dim = metric_def.dimension

            # Route calculator inputs cleanly based on metric requirements
            # Stage 5 (D18-D20): each listed/macro metric consumes its own typed
            # leg. FX data never reaches equity metrics; benchmark data never
            # becomes company VaR/ES; beta needs both legs (no same-series call).
            if m_id in ("revenue_volatility", "receivable_trend"):
                raw_res = metric_def.calculator(periods)
            elif m_id == "equity_volatility":
                raw_res = metric_def.calculator(equity_returns)
            elif m_id == "fx_volatility":
                raw_res = metric_def.calculator(fx_returns)
            elif m_id in ("var_95", "es_95"):
                # Q-M2: company equity returns feed VaR and ES (same leg).
                raw_res = metric_def.calculator(equity_returns)
            elif m_id == "beta":
                raw_res = metric_def.calculator(equity_returns, benchmark_returns)
            elif m_id == "cash_runway_months":
                raw_res = metric_def.calculator(latest_period, history=periods)
            elif m_id == "altman_z_distance":
                raw_res = metric_def.calculator(latest_period, profile=profile)
            elif m_id == "merton_dd":
                raw_res = metric_def.calculator(
                    latest_period.get("total_assets"),
                    latest_period.get("total_debt"),
                    None,
                )
            elif m_id == "ccc":
                raw_res = metric_def.calculator(dso_val, dio_val, dpo_val)
            elif m_id == "inflation_passthrough":
                raw_res = metric_def.calculator(margin_change, cpi_change)
            elif m_id == "rate_environment":
                raw_res = metric_def.calculator(fed_current, fed_median)
            elif m_id == "gdp_sensitivity":
                sector = profile.get("sector", "manufacturing")
                if gdp_volatility is None:
                    raw_res = metric_def.calculator(sector)
                else:
                    raw_res = metric_def.calculator(sector, gdp_volatility)
            else:
                raw_res = metric_def.calculator(latest_period)

            # Score metric raw result
            scored_res = score_metric(raw_res, metric_def.anchors)
            self._stamp_market_provenance(
                scored_res,
                m_id,
                market_provenance,
                joined_obs=joined_beta_obs if m_id == "beta" else None,
            )
            dimension_metrics.setdefault(dim, []).append(scored_res)
            all_metrics.append(scored_res)

        # Aggregate dimension scores
        dimension_results: dict[str, DimensionResult] = {}
        for dim_id, metrics_list in dimension_metrics.items():
            dim_res = aggregate_dimension(dim_id, metrics_list)
            dimension_results[dim_id] = dim_res

        # Aggregate composite score
        composite = aggregate_composite(dimension_results, custom_weights=custom_weights)

        # Run weight sensitivity analysis
        sensitivity = run_sensitivity_analysis(dimension_results, base_weights=custom_weights)

        return RiskAssessmentReport(
            company_id=company_id,
            company_name=company_name,
            as_of_date=as_of_date,
            registry_version=REGISTRY_VERSION,
            composite=composite,
            sensitivity=sensitivity,
            metrics=all_metrics,
        )
