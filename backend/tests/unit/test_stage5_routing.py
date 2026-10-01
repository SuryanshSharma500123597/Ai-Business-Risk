"""Stage 5 D18 legacy-safety, VaR/ES, macro, provenance, WeightsRef tests."""

from __future__ import annotations

import math

import pytest

from backend.data_engine.risk_inputs import build_market_inputs
from backend.risk_engine.contracts import (
    AlignedSeries,
    MetricStatus,
    RiskEngineMarketInputs,
    WeightsRef,
)
from backend.risk_engine.engine import QuantitativeRiskEngine
from backend.risk_engine.metrics import calc_es_95, calc_var_95
from backend.tests.unit.stage5_helpers import (
    dataset,
    geometric_closes,
    macro_series,
    market_series,
    metric,
)


def test_stage5_beta_mixed_currency_rejected() -> None:
    asset = market_series("equity", geometric_closes(150, 0.01))
    benchmark = market_series("index", geometric_closes(150, 0.005))
    asset.metadata.detail["currency"] = "INR"
    benchmark.metadata.detail["currency"] = "USD"
    inputs = build_market_inputs(equity=asset, benchmark=benchmark)
    with pytest.raises(ValueError, match="currencies differ"):
        QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)


def test_stage5_legacy_market_series_never_forces_beta_one() -> None:
    returns = [0.01 if i % 2 == 0 else -0.01 for i in range(120)]
    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_series=returns)
    assert metric(report, "beta").status == MetricStatus.UNAVAILABLE


def test_stage5_market_inputs_and_legacy_mutually_exclusive() -> None:
    inputs = RiskEngineMarketInputs(equity_returns=AlignedSeries(returns=[0.01] * 60))
    with pytest.raises(ValueError, match="not both"):
        QuantitativeRiskEngine().evaluate_company(
            dataset(), market_series=[0.01] * 60, market_inputs=inputs
        )


def test_stage5_var_es_share_equity_leg() -> None:
    returns = [0.01] * 95 + [-0.05, -0.04, -0.03, -0.02, -0.01]
    assert calc_var_95(returns).value == pytest.approx(1.0, abs=1e-9)
    assert calc_es_95(returns).value == pytest.approx(3.0, abs=1e-9)

    prices = [100.0]
    for ret in returns:
        prices.append(prices[-1] * math.exp(ret))
    inputs = build_market_inputs(equity=market_series("equity", prices))
    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    assert metric(report, "var_95").status == MetricStatus.VALID
    assert metric(report, "es_95").status == MetricStatus.VALID
    assert metric(report, "var_95").value == pytest.approx(1.0, abs=1e-6)
    assert metric(report, "es_95").value == pytest.approx(3.0, abs=1e-6)


def test_stage5_var_es_insufficient_history_unavailable() -> None:
    inputs = build_market_inputs(equity=market_series("equity", geometric_closes(60, 0.01)))
    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    assert metric(report, "var_95").status == MetricStatus.UNAVAILABLE
    assert metric(report, "es_95").status == MetricStatus.UNAVAILABLE


def _periods_with_margin(start_margin: float, end_margin: float) -> list[dict]:
    periods: list[dict] = []
    for i in range(24):
        margin = start_margin + (end_margin - start_margin) * i / 23
        periods.append({"revenue": 1000.0, "gross_profit": 10.0 * margin})
    return periods


def test_stage5_inflation_passthrough_signed_gap() -> None:
    cpi = macro_series("CPIAUCSL", [300.0 + i for i in range(24)])
    periods = _periods_with_margin(40.0, 38.0)
    inputs = build_market_inputs(cpi=cpi, periods=periods)
    assert inputs.cpi_change_pct_24m == pytest.approx(23.0 / 300.0 * 100.0)

    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    checked = metric(report, "inflation_passthrough")
    assert checked.status == MetricStatus.VALID
    assert checked.value == pytest.approx(-2.0 - 23.0 / 300.0 * 100.0)


def test_stage5_rate_environment_current_vs_median() -> None:
    fedfunds = macro_series("FEDFUNDS", [2.0 + 0.05 * i for i in range(60)])
    inputs = build_market_inputs(fedfunds=fedfunds)
    assert inputs.fedfunds_current == pytest.approx(4.95)
    assert inputs.fedfunds_trailing_5y_median == pytest.approx(3.475)

    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    checked = metric(report, "rate_environment")
    assert checked.status == MetricStatus.VALID
    assert checked.value == pytest.approx(4.95 - 3.475)


def test_stage5_short_macro_history_is_missing_input() -> None:
    cpi = macro_series("CPIAUCSL", [300.0 + i for i in range(23)])
    fedfunds = macro_series("FEDFUNDS", [3.0] * 59)
    inputs = build_market_inputs(
        cpi=cpi, fedfunds=fedfunds, periods=_periods_with_margin(40.0, 40.0)
    )
    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    assert metric(report, "inflation_passthrough").status == MetricStatus.MISSING_INPUT
    assert metric(report, "rate_environment").status == MetricStatus.MISSING_INPUT


def test_stage5_missing_macro_inputs_are_missing_input() -> None:
    report = QuantitativeRiskEngine().evaluate_company(
        dataset(), market_inputs=RiskEngineMarketInputs()
    )
    assert metric(report, "inflation_passthrough").status == MetricStatus.MISSING_INPUT
    assert metric(report, "rate_environment").status == MetricStatus.MISSING_INPUT


def test_stage5_gdp_volatility_passthrough_and_default() -> None:
    default_report = QuantitativeRiskEngine().evaluate_company(
        dataset(), market_inputs=RiskEngineMarketInputs()
    )
    assert metric(default_report, "gdp_sensitivity").inputs_used["gdp_volatility"] == 1.0

    custom = RiskEngineMarketInputs(gdp_volatility=2.0)
    custom_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=custom)
    assert metric(custom_report, "gdp_sensitivity").inputs_used["gdp_volatility"] == 2.0
    assert metric(custom_report, "gdp_sensitivity").value == pytest.approx(1.2 * 2.0)


def test_stage5_provenance_preserved_on_routed_metrics() -> None:
    inputs = build_market_inputs(
        equity=market_series("equity", geometric_closes(150, 0.01)),
        benchmark=market_series("index", geometric_closes(150, 0.005)),
        fx=market_series("DEXINUS", geometric_closes(150, 0.01)),
    )
    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)

    fx_metric = metric(report, "fx_volatility")
    assert fx_metric.inputs_used.get("series_id") == "DEXINUS"
    assert fx_metric.inputs_used.get("source") == "fixture"

    beta = metric(report, "beta")
    assert beta.inputs_used.get("asset_symbol") == "equity"
    assert beta.inputs_used.get("benchmark_symbol") == "index"
    assert inputs.equity_returns is not None
    assert beta.inputs_used.get("joined_obs") == len(inputs.equity_returns.returns)


def test_stage5_weights_ref_contract_only() -> None:
    weights = {dim: 0.1 for dim in ("liquidity", "market", "credit", "operational")}
    weights.update({"financial_strength": 0.4, "concentration": 0.1, "macro": 0.1})
    ref = WeightsRef(weights_id="w-1", version="v1", weights=weights)
    report = QuantitativeRiskEngine().evaluate_company(dataset(), weights_ref=ref)
    dimensions = report.composite.dimensions
    assert dimensions["financial_strength"].weight == pytest.approx(0.4)
    assert sum(d.effective_weight for d in dimensions.values()) == pytest.approx(1.0)

    bad_weights = dict(weights)
    bad_weights["macro"] = 0.5
    with pytest.raises(ValueError, match="sum to 1"):
        WeightsRef(weights=bad_weights)
