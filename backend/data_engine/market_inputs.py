"""Deterministic Phase 3 -> Phase 4 market/macro adapter (Stage 5: D18-D20)."""

from __future__ import annotations

import math
from datetime import date

from backend.data_engine.ingest.base import MacroSeries, MarketSeries
from backend.risk_engine.contracts import (
    AlignedSeries,
    SeriesProvenance,
)

__all__ = [
    "aligned_returns_from_closes",
    "align_beta_legs",
]


def _series_currency(metadata_detail: dict[str, object] | None) -> str | None:
    if not metadata_detail:
        return None
    currency = metadata_detail.get("currency")
    return str(currency) if currency is not None else None


def provenance_for_market(series: MarketSeries) -> SeriesProvenance:
    observations = series.observations
    return SeriesProvenance(
        symbol_or_series_id=series.symbol,
        source=series.metadata.source,
        as_of=observations[-1].date if observations else None,
        observation_count=len(observations),
        checksum=series.metadata.checksum,
        license_tag=series.metadata.license_tag,
    )


def provenance_for_macro(series: MacroSeries) -> SeriesProvenance:
    observations = series.observations
    return SeriesProvenance(
        symbol_or_series_id=series.series_id,
        source=series.metadata.source,
        as_of=observations[-1].date if observations else None,
        observation_count=len(observations),
        checksum=series.metadata.checksum,
        license_tag=series.metadata.license_tag,
    )


def _checked_closes(series: MarketSeries) -> dict[date, float]:
    closes_by_date: dict[date, float] = {}
    for point in series.observations:
        if not math.isfinite(point.close):
            raise ValueError(f"non-finite close for {series.symbol} on {point.date}")
        if point.close <= 0:
            raise ValueError(f"non-positive close for {series.symbol} on {point.date}")
        closes_by_date[point.date] = point.close
    return closes_by_date


def aligned_returns_from_closes(series: MarketSeries) -> AlignedSeries:
    """Convert one MarketSeries of closes to decimal daily log returns."""
    closes_by_date = _checked_closes(series)
    ordered_dates = sorted(closes_by_date)
    returns: list[float] = []
    return_dates: list[date] = []
    for prev_day, day in zip(ordered_dates, ordered_dates[1:], strict=False):
        returns.append(math.log(closes_by_date[day] / closes_by_date[prev_day]))
        return_dates.append(day)
    return AlignedSeries(
        dates=return_dates,
        returns=returns,
        symbol_or_series_id=series.symbol,
        source=series.metadata.source,
        as_of=ordered_dates[-1] if ordered_dates else None,
        currency=_series_currency(series.metadata.detail),
    )


def align_beta_legs(
    asset: MarketSeries,
    benchmark: MarketSeries,
) -> tuple[AlignedSeries, AlignedSeries, int]:
    """Inner-join two close series on dates, then log returns per leg."""
    asset_closes = _checked_closes(asset)
    benchmark_closes = _checked_closes(benchmark)
    common_dates = sorted(set(asset_closes) & set(benchmark_closes))
    asset_returns: list[float] = []
    benchmark_returns: list[float] = []
    return_dates: list[date] = []
    for prev_day, day in zip(common_dates, common_dates[1:], strict=False):
        asset_returns.append(math.log(asset_closes[day] / asset_closes[prev_day]))
        benchmark_returns.append(math.log(benchmark_closes[day] / benchmark_closes[prev_day]))
        return_dates.append(day)
    as_of = common_dates[-1] if common_dates else None
    asset_leg = AlignedSeries(
        dates=list(return_dates),
        returns=asset_returns,
        symbol_or_series_id=asset.symbol,
        source=asset.metadata.source,
        as_of=as_of,
        currency=_series_currency(asset.metadata.detail),
    )
    benchmark_leg = AlignedSeries(
        dates=list(return_dates),
        returns=benchmark_returns,
        symbol_or_series_id=benchmark.symbol,
        source=benchmark.metadata.source,
        as_of=as_of,
        currency=_series_currency(benchmark.metadata.detail),
    )
    return asset_leg, benchmark_leg, len(common_dates)
