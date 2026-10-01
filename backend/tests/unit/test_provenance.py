"""Provenance persistence tests."""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.data_engine.provenance import recent_fetches, record_fetch


def test_fetch_provenance_records_success_failure_and_cache(db_session: Session) -> None:
    record_fetch(
        db_session,
        source="fred",
        url="https://example.test/fred",
        license_tag="attribution-required",
        status="cache_hit",
        checksum="abc",
        detail={"cache_status": "hit"},
    )
    record_fetch(
        db_session,
        source="fred",
        url="https://example.test/fred",
        license_tag="attribution-required",
        status="error",
        detail={"error": "offline"},
    )
    db_session.commit()
    rows = recent_fetches(db_session, "fred")
    assert len(rows) == 2
    assert rows[0].status == "error"
    assert rows[1].checksum == "abc"
    assert rows[1].detail == {"cache_status": "hit"}
