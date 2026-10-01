"""World Bank WDI adapter: a single country and indicator per canonical series.

Country is included in series_id to prevent overwriting different economies
in the frozen macro_cache primary key. Truncated responses are rejected.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.data_engine.ingest.base import (
    MacroObservation,
    MacroSeries,
    RateLimiter,
    fetch_payload,
    sorted_unique,
)

WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
LICENSE_TAG = "CC-BY-4.0"


class WorldBankAdapter:
    source = "worldbank"  # frozen source tag; module filename is world_bank.py

    def __init__(self, *, throttle_seconds: float = 1.0) -> None:
        self.throttle = RateLimiter(max(1.0, throttle_seconds))

    def fetch_indicator(
        self,
        indicator: str,
        *,
        session: Session | None = None,
        country: str = "IND",
        start_year: int | None = None,
        end_year: int | None = None,
        cache_dir: str = "data/raw",
        offline: bool = False,
        request: Callable[..., httpx.Response] | None = None,
    ) -> MacroSeries:
        indicator, country = indicator.strip().upper(), country.strip().upper()
        if not re.fullmatch(r"[A-Z0-9_.]{1,80}", indicator):
            raise ValueError("invalid World Bank indicator")
        if not re.fullmatch(r"[A-Z]{2,3}", country) or country == "ALL":
            raise ValueError("exactly one country code is required")
        if any(year is not None and not 1900 <= year <= 2100 for year in (start_year, end_year)):
            raise ValueError("year must be between 1900 and 2100")
        if start_year and end_year and start_year > end_year:
            raise ValueError("start_year must not exceed end_year")
        url = WORLD_BANK_URL.format(country=country, indicator=indicator)
        params: dict[str, Any] = {"format": "json", "per_page": 20000, "source": 2}
        if start_year or end_year:
            params["date"] = f"{start_year or 1900}:{end_year or 2100}"

        def parse(payload: bytes) -> list[MacroObservation]:
            body = json.loads(payload)
            if not isinstance(body, list) or len(body) != 2 or not isinstance(body[1], list):
                raise ValueError("World Bank returned an error/empty envelope")
            metadata, rows = body
            if int(metadata.get("pages", 1)) > 1 or int(metadata.get("total", len(rows))) > len(
                rows
            ):
                raise ValueError("World Bank response truncated")
            points: list[MacroObservation] = []
            for row in rows:
                returned_country = {
                    str(row.get("countryiso3code", "")).upper(),
                    str(row.get("country", {}).get("id", "")).upper(),
                }
                if country not in returned_country or row["indicator"]["id"] != indicator:
                    raise ValueError("World Bank observation has wrong country/indicator")
                year = int(row["date"])
                if (start_year and year < start_year) or (end_year and year > end_year):
                    continue
                if row["value"] is not None:
                    points.append(
                        MacroObservation(date=date(year, 1, 1), value=float(row["value"]))
                    )
            return sorted_unique(points)

        fetched = fetch_payload(
            source=self.source,
            url=url,
            cache_dir=cache_dir,
            cache_ttl_hours=720,
            license_tag=LICENSE_TAG,
            params=params,
            extension="json",
            throttle=self.throttle,
            offline=offline,
            session=session,
            request=request,
            validate=parse,
        )
        fetched.metadata.detail.update(
            {
                "country": country,
                "indicator": indicator,
                "frequency": "annual",
                "attribution": "World Bank WDI",
            }
        )
        return MacroSeries(
            series_id=f"{country}:{indicator}",
            observations=parse(fetched.payload) if fetched.payload else [],
            metadata=fetched.metadata,
        )
