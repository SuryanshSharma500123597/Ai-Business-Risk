"""Stage 5 D19 series-separation tests (FX vs equity legs)."""

from __future__ import annotations

import pytest

from backend.data_engine.risk_inputs import build_market_inputs
from backend.risk_engine.contracts import RiskEngineMarketInputs
from backend.risk_engine.engine import QuantitativeRiskEngine
from backend.tests.unit.stage5_helpers import dataset, geometric_closes, market_series, metric


def _separation_inputs(*, fx_drift: float, equity_drift: float) -> RiskEngineMarketInputs:
    return build_market_inputs(
        equity=market_series("equity", geometric_closes(150, equity_drift)),
        benchmark=market_series("index", geometric_closes(150, 0.005)),
        fx=market_series("DEXINUS", geometric_closes(150, fx_drift)),
    )


def test_stage5_fx_change_moves_only_fx_volatility() -> None:
    base = _separation_inputs(fx_drift=0.001, equity_drift=0.01)
    shocked = _separation_inputs(fx_drift=0.05, equity_drift=0.01)
    base_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=base)
    shocked_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=shocked)

    assert metric(shocked_report, "fx_volatility").value != pytest.approx(
        metric(base_report, "fx_volatility").value
    )
    for metric_id in ("equity_volatility", "var_95", "es_95", "beta"):
        assert metric(shocked_report, metric_id).value == pytest.approx(
            metric(base_report, metric_id).value
        )


def test_stage5_equity_change_moves_equity_metrics_not_fx() -> None:
    base = _separation_inputs(fx_drift=0.001, equity_drift=0.01)
    shocked = _separation_inputs(fx_drift=0.001, equity_drift=0.04)
    base_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=base)
    shocked_report = QuantitativeRiskEngine().evaluate_company(dataset(), market_inputs=shocked)

    assert metric(shocked_report, "fx_volatility").value == pytest.approx(
        metric(base_report, "fx_volatility").value
    )
    for metric_id in ("equity_volatility", "var_95", "es_95"):
        assert metric(shocked_report, metric_id).value != pytest.approx(
            metric(base_report, metric_id).value
        )
