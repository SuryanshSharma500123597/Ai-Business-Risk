"""Source fetch provenance: appends to the frozen source_fetch_log table.

Ingestion adapters call `record_fetch` after every download attempt
(success or failure) so the audit trail covers failures too (data.md §2).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.database.models import SourceFetchLog


def record_fetch(
    session: Session,
    *,
    source: str,
    url: str,
    license_tag: str,
    status: str,
    checksum: str | None = None,
    detail: dict[str, Any] | None = None,
) -> SourceFetchLog:
    """Append one fetch record. status: ok | error | cache_hit."""
    row = SourceFetchLog(
        url=url,
        source=source,
        license_tag=license_tag,
        fetched_at=datetime.now(UTC),
        checksum=checksum,
        status=status,
        detail=detail or {},
    )
    session.add(row)
    session.flush()
    return row


def recent_fetches(session: Session, source: str, limit: int = 20) -> list[SourceFetchLog]:
    return (
        session.query(SourceFetchLog)
        .filter(SourceFetchLog.source == source)
        .order_by(SourceFetchLog.id.desc())
        .limit(limit)
        .all()
    )
