"""Optional yfinance market fallback.

Yahoo is never required for the offline path and is only attempted after the
primary Stooq adapter has failed.  The data is cached locally and marked with
its terms-of-use caveat.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from io import StringIO
from typing import Any

import pandas as pd

from backend.data_engine.cache import cache_key, cache_put, cache_read
from backend.data_engine.ingest.base import (
    MarketObservation,
    MarketSeries,
    RateLimiter,
    SourceMetadata,
    SourceStatus,
    record_metadata,
    unavailable_market,
)

LICENSE_TAG = "tos-restricted-flagged"


class YahooAdapter:
    source = "yahoo"
    throttle = RateLimiter(5.0)

    def __init__(
        self,
        *,
        throttle_seconds: float | None = None,
        download_fn: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        if throttle_seconds is not None:
            self.throttle = RateLimiter(throttle_seconds)
        self.download_fn = download_fn

    def fetch_series(
        self,
        symbol: str,
        *,
        cache_dir: str = "data/raw",
        start: date | None = None,
        end: date | None = None,
        offline: bool = False,
        session: Any = None,
    ) -> MarketSeries:
        symbol = symbol.strip()
        if not symbol:
            raise ValueError("symbol must not be empty")
        url = "https://finance.yahoo.com/"
        params = {"symbol": symbol, "start": str(start or ""), "end": str(end or "")}
        key = cache_key(self.source, symbol, start or "", end or "", extension="csv")
        cached = cache_read(cache_dir, self.source, key, 24, allow_stale=True)

        def metadata(
            status: SourceStatus,
            cache_status: str,
            checksum: str | None,
            detail: dict[str, Any] | None = None,
        ) -> SourceMetadata:
            return SourceMetadata(
                source=self.source,
                url=url,
                license_tag=LICENSE_TAG,
                checksum=checksum,
                cache_status=cache_status,
                status=status,
                requested_params=params,
                detail=detail or {},
            )

        if cached.status == "hit" and cached.payload is not None and cached.entry is not None:
            result = self._from_csv(
                symbol,
                cached.payload,
                metadata(SourceStatus.CACHE_HIT, "hit", cached.entry.checksum),
            )
            record_metadata(session, result.metadata)
            return result
        if offline and cached.payload is not None and cached.entry is not None:
            result = self._from_csv(
                symbol,
                cached.payload,
                metadata(
                    SourceStatus.STALE_CACHE,
                    "stale",
                    cached.entry.checksum,
                    {"warning": "offline stale cache"},
                ),
            )
            record_metadata(session, result.metadata)
            return result
        if offline:
            result = unavailable_market(
                source=self.source,
                symbol=symbol,
                url=url,
                license_tag=LICENSE_TAG,
                detail={"error": "offline and no cache available"},
            )
            record_metadata(session, result.metadata)
            return result

        self.throttle.wait()
        try:
            frame = self._download(symbol, start=start, end=end)
            csv_payload = self._to_csv(frame)
            entry = cache_put(
                cache_dir, self.source, key, csv_payload, url, LICENSE_TAG, requested_params=params
            )
            result = self._from_csv(
                symbol, csv_payload, metadata(SourceStatus.FETCHED, "miss", entry.checksum)
            )
        except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
            if cached.payload is not None and cached.entry is not None:
                result = self._from_csv(
                    symbol,
                    cached.payload,
                    metadata(
                        SourceStatus.STALE_CACHE,
                        "stale",
                        cached.entry.checksum,
                        {"error": str(exc), "warning": "live request failed; stale cache used"},
                    ),
                )
            else:
                result = unavailable_market(
                    source=self.source,
                    symbol=symbol,
                    url=url,
                    license_tag=LICENSE_TAG,
                    detail={"error": str(exc)},
                )
        record_metadata(session, result.metadata)
        return result

    def _download(self, symbol: str, *, start: date | None, end: date | None) -> pd.DataFrame:
        if self.download_fn is not None:
            return self.download_fn(symbol, start=start, end=end)
        try:
            import yfinance as yf
        except ImportError as exc:
            raise ImportError("yfinance is optional; install ai-business-risk[market]") from exc
        frame = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False)
        if frame.empty:
            raise ValueError("Yahoo returned no observations")
        return frame

    @staticmethod
    def _to_csv(frame: pd.DataFrame) -> bytes:
        if frame.empty:
            raise ValueError("Yahoo returned no observations")
        close = frame["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        output = pd.DataFrame({"Date": pd.to_datetime(close.index), "Close": close.to_numpy()})
        return output.to_csv(index=False).encode("utf-8")

    @staticmethod
    def _from_csv(symbol: str, payload: bytes, metadata: SourceMetadata) -> MarketSeries:
        frame = pd.read_csv(StringIO(payload.decode("utf-8")))
        if "Date" not in frame.columns or "Close" not in frame.columns:
            raise ValueError("cached Yahoo payload must contain Date and Close")
        observations = [
            MarketObservation(date=pd.Timestamp(row[0]).date(), close=float(row[1]))
            for row in frame[["Date", "Close"]].itertuples(index=False)
            if pd.notna(row[0]) and pd.notna(row[1])
        ]
        observations.sort(key=lambda observation: observation.date)
        return MarketSeries(symbol=symbol, observations=observations, metadata=metadata)


class MarketSeriesProvider:
    """Stooq-primary/Yahoo-fallback consumer-facing market provider."""

    def __init__(self, stooq: Any, yahoo: YahooAdapter) -> None:
        self.stooq = stooq
        self.yahoo = yahoo

    def fetch_series(self, symbol: str, **kwargs: Any) -> MarketSeries:
        primary = self.stooq.fetch_series(symbol, **kwargs)
        if primary.observations:
            return primary
        return self.yahoo.fetch_series(symbol, **kwargs)
