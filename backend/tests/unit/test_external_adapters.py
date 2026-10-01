"""Fixture-only tests for Phase 3 external source adapters."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from backend.data_engine.ingest.edgar import EdgarAdapter
from backend.data_engine.ingest.fred import FredAdapter
from backend.data_engine.ingest.stooq import StooqAdapter
from backend.data_engine.ingest.world_bank import WorldBankAdapter
from backend.data_engine.ingest.yahoo import MarketSeriesProvider, YahooAdapter
from backend.database.models import SourceFetchLog

FIXTURES = Path(__file__).parents[1] / "fixtures"


def response(payload: bytes) -> httpx.Response:
    return httpx.Response(200, content=payload)


def test_fred_csv_fixture_is_normalized(tmp_path: Path) -> None:
    payload = (FIXTURES / "fred_series.csv").read_bytes()
    series = FredAdapter(throttle_seconds=0).fetch_series(
        "FEDFUNDS", cache_dir=str(tmp_path), request=lambda *args, **kwargs: response(payload)
    )
    assert [point.value for point in series.observations] == [3.5, 3.6]
    assert series.metadata.source == "fred"
    assert series.metadata.license_tag == "attribution-required"
    cached = FredAdapter(throttle_seconds=0).fetch_series(
        "FEDFUNDS", cache_dir=str(tmp_path), offline=True
    )
    assert cached.metadata.status.value == "cache_hit"


def test_fred_json_fixture_does_not_cache_api_key(tmp_path: Path) -> None:
    payload = b'{"observations":[{"date":"2026-01-01","value":"3.5"}]}'
    series = FredAdapter(api_key="secret", throttle_seconds=0).fetch_series(
        "FEDFUNDS", cache_dir=str(tmp_path), request=lambda *args, **kwargs: response(payload)
    )
    assert series.observations[0].date == date(2026, 1, 1)
    index = (tmp_path / "raw" / "fred" / "index.json").read_text(encoding="utf-8")
    assert "secret" not in index


def test_world_bank_fixture_is_normalized(tmp_path: Path) -> None:
    payload = (FIXTURES / "world_bank.json").read_bytes()
    series = WorldBankAdapter(throttle_seconds=0).fetch_indicator(
        "NY.GDP.MKTP.KD.ZG",
        country="IND",
        cache_dir=str(tmp_path),
        request=lambda *args, **kwargs: response(payload),
    )
    assert [point.date.year for point in series.observations] == [2023, 2024]
    assert series.metadata.license_tag == "CC-BY-4.0"


def test_stooq_fixture_is_normalized(tmp_path: Path) -> None:
    payload = (FIXTURES / "stooq.csv").read_bytes()
    series = StooqAdapter(throttle_seconds=0).fetch_series(
        "^spx", cache_dir=str(tmp_path), request=lambda *args, **kwargs: response(payload)
    )
    assert [point.close for point in series.observations] == [102.0, 103.5]
    assert series.metadata.license_tag == "personal-use-flagged"


def test_edgar_is_feature_flagged_and_maps_company_facts(tmp_path: Path) -> None:
    payload = (FIXTURES / "edgar_companyfacts.json").read_bytes()
    disabled = EdgarAdapter(enabled=False).fetch_company("3193", cache_dir=str(tmp_path))
    assert disabled.periods == []
    assert disabled.metadata.status.value == "unavailable"
    enabled = EdgarAdapter(enabled=True, throttle_seconds=0).fetch_company(
        "3193", cache_dir=str(tmp_path), request=lambda *args, **kwargs: response(payload)
    )
    assert enabled.cik == "0000003193"
    assert len(enabled.periods) == 2
    assert enabled.periods[0].source == "edgar"
    assert enabled.periods[0].gross_profit == 480000.0
    assert enabled.metadata.detail["mapping_version"]


def test_yahoo_fixture_and_primary_fallback(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {"Close": [10.0, 11.0]},
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    yahoo = YahooAdapter(throttle_seconds=0, download_fn=lambda *args, **kwargs: frame)
    primary = StooqAdapter(throttle_seconds=0)
    provider = MarketSeriesProvider(primary, yahoo)
    series = provider.fetch_series("^spx", cache_dir=str(tmp_path), offline=True)
    assert series.metadata.source == "yahoo"
    assert len(series.observations) == 0  # no cached Yahoo payload in offline mode
    series = yahoo.fetch_series("^spx", cache_dir=str(tmp_path))
    assert [point.close for point in series.observations] == [10.0, 11.0]
    cached = yahoo.fetch_series("^spx", cache_dir=str(tmp_path), offline=True)
    assert cached.metadata.status.value == "cache_hit"


def test_adapter_fetches_are_recorded_in_provenance(tmp_path: Path, db_session: Session) -> None:
    payload = (FIXTURES / "fred_series.csv").read_bytes()
    adapter = FredAdapter(throttle_seconds=0)
    adapter.fetch_series(
        "FEDFUNDS",
        cache_dir=str(tmp_path),
        session=db_session,
        request=lambda *args, **kwargs: response(payload),
    )
    adapter.fetch_series("FEDFUNDS", cache_dir=str(tmp_path), session=db_session, offline=True)
    db_session.commit()
    rows = db_session.query(SourceFetchLog).all()
    assert [row.status for row in rows] == ["fetched", "cache_hit"]
    assert rows[0].checksum


def test_external_failure_returns_explicit_unavailable(tmp_path: Path) -> None:
    def fail(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("offline")

    result = StooqAdapter(throttle_seconds=0).fetch_series(
        "x", cache_dir=str(tmp_path), request=fail
    )
    assert result.observations == []
    assert result.metadata.status.value == "unavailable"
    assert "offline" in json.dumps(result.metadata.detail)
