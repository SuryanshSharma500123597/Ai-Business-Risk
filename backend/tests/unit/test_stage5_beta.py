"""Stage 5 D18 beta tests (distinct legs, boundaries, legacy safety)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.data_engine.risk_inputs import build_market_inputs
from backend.risk_engine.contracts import MetricStatus
from backend.risk_engine.engine import QuantitativeRiskEngine
from backend.risk_engine.metrics import calc_beta
from backend.tests.unit.stage5_helpers import dataset, geometric_closes, market_series, metric


def test_stage5_beta_divergent_legs_not_one() -> None:
    asset = market_series("equity", geometric_closes(150, 0.02))
    benchmark = market_series("index", geometric_closes(150, 0.005))
    inputs = build_market_inputs(equity=asset, benchmark=benchmark)
    assert inputs.equity_returns is not None and inputs.benchmark_returns is not None

    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    beta = metric(report, "beta")
    assert beta.status == MetricStatus.VALID
    assert beta.value is not None and beta.value != pytest.approx(1.0, abs=1e-6)


def test_stage5_beta_hand_computed_covariance_variance() -> None:
    market = [0.01 if i % 2 == 0 else -0.01 for i in range(120)]
    asset = [2.0 * r for r in market]
    result = calc_beta(asset, market)
    assert result.status == MetricStatus.VALID
    assert result.value == pytest.approx(2.0, abs=1e-9)


def test_stage5_beta_perfect_correlation_is_one() -> None:
    market = [0.01 if i % 2 == 0 else -0.01 for i in range(120)]
    result = calc_beta(list(market), list(market))
    assert result.status == MetricStatus.VALID
    assert result.value == pytest.approx(1.0, abs=1e-9)


def test_stage5_beta_zero_benchmark_variance_invalid() -> None:
    result = calc_beta([0.01 if i % 2 == 0 else -0.01 for i in range(120)], [0.0] * 120)
    assert result.status == MetricStatus.INVALID_INPUT


def test_stage5_beta_minimum_history_boundary() -> None:
    # 121 closes -> 120 aligned returns (VALID); 120 closes -> 119 (UNAVAILABLE).
    ok_inputs = build_market_inputs(
        equity=market_series("equity", geometric_closes(121, 0.01)),
        benchmark=market_series("index", geometric_closes(121, 0.005)),
    )
    ok_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=ok_inputs)
    assert metric(ok_report, "beta").status == MetricStatus.VALID

    short_inputs = build_market_inputs(
        equity=market_series("equity", geometric_closes(120, 0.01)),
        benchmark=market_series("index", geometric_closes(120, 0.005)),
    )
    short_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=short_inputs)
    assert metric(short_report, "beta").status == MetricStatus.UNAVAILABLE


def test_stage5_beta_inner_join_and_joined_count() -> None:
    asset = market_series("equity", geometric_closes(150, 0.01))
    benchmark = market_series("index", geometric_closes(150, 0.005), start=date(2026, 1, 11))
    inputs = build_market_inputs(equity=asset, benchmark=benchmark)
    assert inputs.equity_returns is not None and inputs.benchmark_returns is not None
    assert inputs.equity_returns.dates == inputs.benchmark_returns.dates
    assert len(inputs.equity_returns.returns) == 139

    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=inputs)
    beta = metric(report, "beta")
    assert beta.status == MetricStatus.VALID
    assert beta.inputs_used.get("joined_obs") == 139


def test_stage5_beta_missing_legs_unavailable() -> None:
    equity_only = build_market_inputs(equity=market_series("e", geometric_closes(150, 0.01)))
    report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=equity_only)
    assert metric(report, "beta").status == MetricStatus.UNAVAILABLE

    bench_only = build_market_inputs(benchmark=market_series("i", geometric_closes(150, 0.005)))
    bench_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=bench_only)
    assert metric(bench_report, "beta").status == MetricStatus.UNAVAILABLE
