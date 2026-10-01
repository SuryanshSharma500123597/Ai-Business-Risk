"""Stage 5 shared fixtures (D18-D20). Local synthetic data only."""

from __future__ import annotations

import math
from datetime import date, timedelta

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.base import (
    MacroObservation,
    MacroSeries,
    MarketObservation,
    MarketSeries,
    SourceMetadata,
    SourceStatus,
)
from backend.data_engine.ingest.synthetic import generate_company
from backend.risk_engine.contracts import MetricResult, RiskAssessmentReport


def market_series(
    symbol: str, closes: list[float], *, start: date = date(2026, 1, 1)
) -> MarketSeries:
    observations = [
        MarketObservation(date=start + timedelta(days=i), close=close)
        for i, close in enumerate(closes)
    ]
    return MarketSeries(
        symbol=symbol,
        observations=observations,
        metadata=SourceMetadata(
            source="fixture",
            url="fixture://stage5",
            license_tag="synthetic",
            cache_status="test",
            status=SourceStatus.FETCHED,
        ),
    )


def macro_series(series_id: str, values: list[float]) -> MacroSeries:
    observations = [
        MacroObservation(date=date(2021, 1, 1) + timedelta(days=30 * i), value=value)
        for i, value in enumerate(values)
    ]
    return MacroSeries(
        series_id=series_id,
        observations=observations,
        metadata=SourceMetadata(
            source="fixture",
            url="fixture://stage5",
            license_tag="synthetic",
            cache_status="test",
            status=SourceStatus.FETCHED,
        ),
    )


def geometric_closes(count: int, drift: float, start: float = 100.0) -> list[float]:
    closes = [start]
    for i in range(1, count):
        closes.append(closes[-1] * math.exp(drift if i % 2 == 0 else -drift))
    return closes


def metric(report: RiskAssessmentReport, metric_id: str) -> MetricResult:
    return next(m for m in report.metrics if m.metric_id == metric_id)


def dataset() -> object:
    return generate_company(SyntheticCompanyConfig(seed=1001, periods=24))
