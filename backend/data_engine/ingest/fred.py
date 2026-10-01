"""Official FRED API (environment key) and explicit official graph CSV fallback."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.data_engine.ingest.base import (
    MacroObservation,
    MacroSeries,
    RateLimiter,
    check_dates,
    fetch_payload,
    sorted_unique,
)

FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
LICENSE_TAG = "attribution-required"


class FredAdapter:
    source = "fred"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        csv_fallback: bool = True,
        throttle_seconds: float = 1.0,
    ) -> None:
        self.api_key = get_settings().fred_api_key if api_key is None else api_key
        self.csv_fallback = csv_fallback
        self.throttle = RateLimiter(max(1.0, throttle_seconds))

    def fetch_series(
        self,
        series_id: str,
        *,
        session: Session | None = None,
        cache_dir: str = "data/raw",
        start: date | None = None,
        end: date | None = None,
        offline: bool = False,
        request: Callable[..., httpx.Response] | None = None,
    ) -> MacroSeries:
        series_id = series_id.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_]{1,80}", series_id):
            raise ValueError("invalid FRED series identifier")
        check_dates(start, end)
        use_csv = self.csv_fallback and not self.api_key
        params: dict[str, Any]
        if use_csv:
            url = FRED_CSV_URL
            params = {"id": series_id}
            if start:
                params["cosd"] = start.isoformat()
            if end:
                params["coed"] = end.isoformat()
        else:
            url = FRED_API_URL
            params = {"series_id": series_id, "file_type": "json", "limit": 100000}
            if start:
                params["observation_start"] = start.isoformat()
            if end:
                params["observation_end"] = end.isoformat()
        public = dict(params)
        if self.api_key and not use_csv:
            params["api_key"] = self.api_key

        def parse(payload: bytes) -> list[MacroObservation]:
            points = self._parse_csv(payload, series_id) if use_csv else self._parse_json(payload)
            # Sources may ignore their date parameters: enforce the requested bounds.
            return sorted_unique(
                [
                    point
                    for point in points
                    if (start is None or point.date >= start) and (end is None or point.date <= end)
                ]
            )

        fetched = fetch_payload(
            source=self.source,
            url=url,
            session=session,
            cache_dir=cache_dir,
            cache_ttl_hours=168,
            license_tag=LICENSE_TAG,
            params=params,
            cache_params=public,
            extension="csv" if use_csv else "json",
            throttle=self.throttle,
            offline=offline,
            request=request,
            validate=parse,
            unavailable_reason=(None if self.api_key or use_csv else "FRED API key not configured"),
        )
        fetched.metadata.detail.update(
            {
                "series_id": series_id,
                "series_url": f"https://fred.stlouisfed.org/series/{series_id}",
                "attribution": "Federal Reserve Bank of St. Louis / original series publisher",
                "units": "native series units; see series metadata",
                "access": "csv" if use_csv else "api",
            }
        )
        return MacroSeries(
            series_id=series_id,
            observations=parse(fetched.payload) if fetched.payload else [],
            metadata=fetched.metadata,
        )

    @staticmethod
    def _parse_csv(payload: bytes, series_id: str) -> list[MacroObservation]:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
        columns = reader.fieldnames or []
        date_column = next((c for c in columns if c.upper() in {"DATE", "OBSERVATION_DATE"}), None)
        if date_column is None or series_id not in columns:
            raise ValueError("missing FRED CSV columns")
        return [
            MacroObservation(date=date.fromisoformat(row[date_column]), value=float(row[series_id]))
            for row in reader
            if row[series_id] not in {"", "."}
        ]

    @staticmethod
    def _parse_json(payload: bytes) -> list[MacroObservation]:
        body = json.loads(payload)
        rows = body["observations"]
        if int(body.get("count", len(rows))) > len(rows):
            raise ValueError("FRED response truncated; request a narrower date range")
        return [
            MacroObservation(date=date.fromisoformat(row["date"]), value=float(row["value"]))
            for row in rows
            if row["value"] != "."
        ]
