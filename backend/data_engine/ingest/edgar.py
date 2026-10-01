"""Optional SEC EDGAR company-facts adapter.

The adapter is disabled by default and maps only structured company-facts into
canonical ``PeriodFinancials`` rows.  It never invents absent concepts; source
rows retain ``source='edgar'`` and missing values remain ``None``.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any

from backend.data_engine.contracts import Frequency, PeriodFinancials
from backend.data_engine.ingest.base import (
    EdgarDataset,
    RateLimiter,
    SourceMetadata,
    SourceStatus,
    fetch_payload,
    record_metadata,
)
from backend.data_engine.ingest.edgar_map import EDGAR_MAP_VERSION, US_GAAP_FIELD_TAGS

EDGAR_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
LICENSE_TAG = "public-domain"


class EdgarAdapter:
    source = "edgar"
    throttle = RateLimiter(0.125)  # hard cap 8 requests/second

    def __init__(
        self,
        *,
        enabled: bool = False,
        user_agent: str = "AI-Business-Risk-Research contact@example.com",
        throttle_seconds: float | None = None,
    ) -> None:
        self.enabled = enabled
        self.user_agent = user_agent
        if throttle_seconds is not None:
            self.throttle = RateLimiter(throttle_seconds)

    def fetch_company(
        self,
        cik: str,
        *,
        cache_dir: str = "data/raw",
        offline: bool = False,
        session: Any = None,
        request: Any = None,
    ) -> EdgarDataset:
        normalized_cik = self._normalize_cik(cik)
        url = EDGAR_URL.format(cik=normalized_cik)
        if not self.enabled:
            metadata = SourceMetadata(
                source=self.source,
                url=url,
                license_tag=LICENSE_TAG,
                cache_status="disabled",
                status=SourceStatus.UNAVAILABLE,
                requested_params={"cik": normalized_cik},
                detail={"error": "EDGAR adapter is disabled; set ENABLE_EDGAR=1 explicitly"},
            )
            record_metadata(session, metadata)
            return EdgarDataset(cik=normalized_cik, metadata=metadata)
        fetched = fetch_payload(
            source=self.source,
            url=url,
            cache_dir=cache_dir,
            cache_ttl_hours=24,
            license_tag=LICENSE_TAG,
            params={"cik": normalized_cik},
            extension="json",
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"},
            throttle=self.throttle,
            offline=offline,
            session=session,
            request=request,
        )
        if fetched.payload is None:
            return EdgarDataset(cik=normalized_cik, metadata=fetched.metadata)
        try:
            body = json.loads(fetched.payload.decode("utf-8"))
            periods = self._to_periods(body)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            metadata = fetched.metadata.model_copy(
                update={
                    "status": SourceStatus.UNAVAILABLE,
                    "detail": {"error": f"invalid EDGAR company-facts payload: {exc}"},
                }
            )
            record_metadata(session, metadata)
            return EdgarDataset(cik=normalized_cik, metadata=metadata)
        metadata = fetched.metadata.model_copy(
            update={"detail": {"mapping_version": EDGAR_MAP_VERSION}}
        )
        return EdgarDataset(cik=normalized_cik, periods=periods, metadata=metadata)

    @staticmethod
    def _normalize_cik(cik: str) -> str:
        digits = "".join(character for character in str(cik) if character.isdigit())
        if not digits or len(digits) > 10:
            raise ValueError("CIK must contain at most 10 digits")
        return digits.zfill(10)

    @staticmethod
    def _facts_by_field(body: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        facts = body.get("facts", {}).get("us-gaap", {})
        output: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for field, tags in US_GAAP_FIELD_TAGS.items():
            for tag in tags:
                tag_body = facts.get(tag)
                if not tag_body:
                    continue
                units = tag_body.get("units", {})
                unit_rows: list[dict[str, Any]] = (
                    units.get("USD") or units.get("shares") or next(iter(units.values()), [])
                )
                for row in unit_rows:
                    if row.get("end") and isinstance(row.get("val"), (int, float)):
                        output[field].append({**row, "tag": tag})
                if output[field]:
                    break
        return output

    @classmethod
    def _to_periods(cls, body: dict[str, Any]) -> list[PeriodFinancials]:
        facts = cls._facts_by_field(body)
        grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for field, rows in facts.items():
            for row in rows:
                end = row["end"]
                previous = grouped[end].get(field)
                if previous is None or cls._row_priority(row) >= cls._row_priority(previous):
                    grouped[end][field] = row
        periods: list[PeriodFinancials] = []
        for end_text, fields in sorted(grouped.items()):
            end = date.fromisoformat(end_text)
            frequency = cls._frequency(fields)
            start = cls._period_start(fields, end, frequency)
            values = {field: float(row["val"]) for field, row in fields.items()}
            if "capex" in values:
                values["capex"] = abs(values["capex"])
            if "gross_profit" not in values and {"revenue", "cogs"} <= values.keys():
                values["gross_profit"] = values["revenue"] - values["cogs"]
            if "total_debt" not in values and {"st_debt", "lt_debt"} & values.keys():
                values["total_debt"] = values.get("st_debt", 0.0) + values.get("lt_debt", 0.0)
            if "ebitda" not in values and {"ebit", "da"} <= values.keys():
                values["ebitda"] = values["ebit"] + values["da"]
            periods.append(
                PeriodFinancials(
                    period_start=start,
                    period_end=end,
                    fiscal_year=end.year,
                    quarter=((end.month - 1) // 3 + 1)
                    if frequency is Frequency.QUARTERLY
                    else None,
                    frequency=frequency,
                    source="edgar",
                    **values,
                )
            )
        return periods

    @staticmethod
    def _row_priority(row: dict[str, Any]) -> tuple[int, str]:
        form = str(row.get("form", ""))
        form_priority = 2 if form == "10-K" else 1 if form in {"10-Q", "10-K/A"} else 0
        return form_priority, str(row.get("filed", ""))

    @staticmethod
    def _frequency(fields: dict[str, dict[str, Any]]) -> Frequency:
        forms = {str(row.get("form", "")) for row in fields.values()}
        return Frequency.ANNUAL if "10-K" in forms or "10-K/A" in forms else Frequency.QUARTERLY

    @staticmethod
    def _period_start(fields: dict[str, dict[str, Any]], end: date, frequency: Frequency) -> date:
        starts = [
            date.fromisoformat(str(row["start"])) for row in fields.values() if row.get("start")
        ]
        if starts:
            return min(starts)
        if frequency is Frequency.ANNUAL:
            return date(end.year, 1, 1)
        month = max(1, end.month - 2)
        year = end.year if end.month > 2 else end.year - 1
        return date(year, month, 1)
