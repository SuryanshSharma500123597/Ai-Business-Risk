"""Stooq CSV market adapter.

Stooq is intentionally marked as personal-use/terms-risk flagged.  The
adapter caches locally and never redistributes downloaded payloads.
"""

from __future__ import annotations

from datetime import date
from io import StringIO
from typing import Any

import pandas as pd

from backend.data_engine.ingest.base import (
    MarketObservation,
    MarketSeries,
    RateLimiter,
    SourceStatus,
    fetch_payload,
    record_metadata,
    unavailable_market,
)

STOOQ_URL = "https://stooq.com/q/d/l/"
LICENSE_TAG = "personal-use-flagged"


class StooqAdapter:
    source = "stooq"
    throttle = RateLimiter(2.0)

    def __init__(self, *, throttle_seconds: float | None = None) -> None:
        if throttle_seconds is not None:
            self.throttle = RateLimiter(throttle_seconds)

    def fetch_series(
        self,
        symbol: str,
        *,
        cache_dir: str = "data/raw",
        start: date | None = None,
        end: date | None = None,
        offline: bool = False,
        session: Any = None,
        request: Any = None,
    ) -> MarketSeries:
        symbol = symbol.strip().lower()
        if not symbol:
            raise ValueError("symbol must not be empty")
        params: dict[str, Any] = {"s": symbol, "i": "d"}
        if start is not None:
            params["d1"] = start.strftime("%Y%m%d")
        if end is not None:
            params["d2"] = end.strftime("%Y%m%d")
        fetched = fetch_payload(
            source=self.source,
            url=STOOQ_URL,
            cache_dir=cache_dir,
            cache_ttl_hours=24,
            license_tag=LICENSE_TAG,
            params=params,
            extension="csv",
            throttle=self.throttle,
            offline=offline,
            session=session,
            request=request,
            validate=self._parse_payload,
        )
        if fetched.payload is None:
            return unavailable_market(
                source=self.source,
                symbol=symbol,
                url=STOOQ_URL,
                license_tag=LICENSE_TAG,
                detail=fetched.metadata.detail,
            )
        try:
            observations = self._parse_payload(fetched.payload)
        except (ValueError, TypeError, pd.errors.ParserError) as exc:
            metadata = fetched.metadata.model_copy(
                update={
                    "status": SourceStatus.UNAVAILABLE,
                    "detail": {"error": f"invalid Stooq payload: {exc}"},
                }
            )
            record_metadata(session, metadata)
            return MarketSeries(symbol=symbol, metadata=metadata)
        observations.sort(key=lambda observation: observation.date)
        return MarketSeries(symbol=symbol, observations=observations, metadata=fetched.metadata)

    @staticmethod
    def _parse_payload(payload: bytes) -> list[MarketObservation]:
        frame = pd.read_csv(StringIO(payload.decode("utf-8")))
        date_column = next((c for c in frame.columns if c.lower() == "date"), None)
        close_column = next((c for c in frame.columns if c.lower() == "close"), None)
        if date_column is None or close_column is None:
            raise ValueError("Stooq CSV must contain Date and Close columns")
        return [
            MarketObservation(date=pd.Timestamp(row[0]).date(), close=float(row[1]))
            for row in frame[[date_column, close_column]].itertuples(index=False)
            if pd.notna(row[0]) and pd.notna(row[1])
        ]
