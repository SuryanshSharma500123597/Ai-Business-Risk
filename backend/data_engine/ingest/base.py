"""Typed source contracts and bounded, audited transport for Phase 3.

Callers own the SQLAlchemy transaction: every adapter attempt is flushed to
source_fetch_log, and callers must commit even an unavailable result if they
want to retain its audit trail. No adapters commit or perform SQL themselves.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from backend.data_engine.cache import cache_key, cache_put, cache_read, checksum_bytes
from backend.data_engine.contracts import PeriodFinancials
from backend.data_engine.provenance import record_fetch

MAX_PAYLOAD_BYTES = 32 * 1024 * 1024


class SourceStatus(StrEnum):
    FETCHED = "fetched"
    CACHE_HIT = "cache_hit"
    STALE_CACHE = "stale_cache"
    UNAVAILABLE = "unavailable"


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    url: str
    retrieved_at: datetime | None = None  # original payload time; None when no payload
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    license_tag: str
    checksum: str | None = None
    cache_status: str
    status: SourceStatus
    requested_params: dict[str, str] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)


class MacroObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    date: date
    value: float


class MacroSeries(BaseModel):
    series_id: str
    observations: list[MacroObservation] = Field(default_factory=list)
    metadata: SourceMetadata

    @model_validator(mode="after")
    def unique_dates(self) -> MacroSeries:
        dates = [point.date for point in self.observations]
        if len(set(dates)) != len(dates):
            raise ValueError("duplicate macro observation dates")
        return self


class MarketObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    date: date
    close: float  # signed prices are allowed (e.g. WTI); finiteness is mandatory


class MarketSeries(BaseModel):
    symbol: str
    observations: list[MarketObservation] = Field(default_factory=list)
    metadata: SourceMetadata

    @model_validator(mode="after")
    def unique_dates(self) -> MarketSeries:
        dates = [point.date for point in self.observations]
        if len(set(dates)) != len(dates):
            raise ValueError("duplicate market observation dates")
        return self


class EdgarDataset(BaseModel):
    cik: str
    periods: list[PeriodFinancials] = Field(default_factory=list)
    metadata: SourceMetadata


@dataclass(frozen=True)
class FetchedPayload:
    payload: bytes | None
    metadata: SourceMetadata


class RateLimiter:
    """Explicit reusable limiter with injectable clock/sleep for offline tests."""

    def __init__(
        self,
        minimum_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not math.isfinite(minimum_interval_seconds) or minimum_interval_seconds < 0:
            raise ValueError("rate limit interval must be finite and nonnegative")
        self.minimum_interval_seconds = minimum_interval_seconds
        self._clock, self._sleep = clock, sleep
        self._last_request: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            if self._last_request is not None:
                delay = self.minimum_interval_seconds - (self._clock() - self._last_request)
                if delay > 0:
                    self._sleep(delay)
            self._last_request = self._clock()


def record_metadata(session: Session | None, metadata: SourceMetadata) -> None:
    """Persist provenance without taking ownership of the caller's transaction."""
    if session is None:
        return
    record_fetch(
        session,
        source=metadata.source,
        url=metadata.url,
        license_tag=metadata.license_tag,
        status=metadata.status.value,
        checksum=metadata.checksum,
        detail={
            "cache_status": metadata.cache_status,
            "requested_params": metadata.requested_params,
            "retrieved_at": metadata.retrieved_at.isoformat() if metadata.retrieved_at else None,
            **metadata.detail,
        },
    )


def safe_error(exc: Exception) -> str:
    """Keep useful errors while removing credentials and URL query values."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    message = str(exc) or type(exc).__name__
    for secret in ("api_key", "apikey", "token", "authorization", "password"):
        message = message.replace(secret, "redacted")
    return message[:300]


def _bounded_get(url: str, **kwargs: Any) -> httpx.Response:
    """Bound response size and elapsed time as well as per-I/O timeouts."""
    timeout = float(kwargs.get("timeout", 30.0))
    started = time.monotonic()
    with httpx.Client() as client, client.stream("GET", url, **kwargs) as response:
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_PAYLOAD_BYTES or time.monotonic() - started > timeout:
                raise ValueError("source response exceeded size/time budget")
            chunks.append(chunk)
        return httpx.Response(
            response.status_code, content=b"".join(chunks), request=response.request
        )


def fetch_payload(
    *,
    source: str,
    url: str,
    cache_dir: str,
    cache_ttl_hours: float,
    license_tag: str,
    session: Session | None,
    params: dict[str, Any] | None = None,
    cache_params: dict[str, Any] | None = None,
    extension: str = "bin",
    headers: dict[str, str] | None = None,
    throttle: RateLimiter,
    offline: bool = False,
    request: Callable[..., httpx.Response] | None = None,
    validate: Callable[[bytes], object] | None = None,
    unavailable_reason: str | None = None,
    disabled: bool = False,
) -> FetchedPayload:
    """Cache-first, audited fetch; stale data is always explicitly degraded."""
    public_params = {
        str(key): str(value)
        for key, value in (cache_params if cache_params is not None else params or {}).items()
        if key.lower() not in {"api_key", "apikey", "token", "authorization", "password"}
    }
    key = cache_key(source, url, *sorted(public_params.items()), extension=extension)
    metadata = SourceMetadata(
        source=source,
        url=url,
        license_tag=license_tag,
        cache_status="miss",
        status=SourceStatus.UNAVAILABLE,
        requested_params=public_params,
    )

    def finish(payload: bytes | None, result_metadata: SourceMetadata) -> FetchedPayload:
        record_metadata(session, result_metadata)
        return FetchedPayload(payload, result_metadata)

    if disabled:
        metadata.cache_status = "disabled"
        metadata.detail = {"error": unavailable_reason or "source disabled"}
        return finish(None, metadata)

    cached = cache_read(cache_dir, source, key, cache_ttl_hours, allow_stale=True)
    metadata.cache_status = cached.status
    cached_payload = cached.payload
    if cached_payload is not None:
        try:
            if validate is not None:
                validate(cached_payload)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, UnicodeError) as exc:
            cached_payload = None
            metadata.cache_status = "corrupt"
            metadata.detail = {"error": f"invalid cached payload: {safe_error(exc)}"}
    if cached_payload is not None and cached.entry is not None:
        metadata.checksum = cached.entry.checksum
        metadata.retrieved_at = datetime.fromisoformat(cached.entry.fetched_at)
        if cached.status == "hit":
            metadata.status = SourceStatus.CACHE_HIT
            return finish(cached_payload, metadata)

    if offline or unavailable_reason:
        if cached_payload is not None:
            metadata.status = SourceStatus.STALE_CACHE
            metadata.detail["warning"] = "expired cache used; source is degraded"
            return finish(cached_payload, metadata)
        metadata.detail["error"] = unavailable_reason or cached.detail or "offline cache miss"
        return finish(None, metadata)

    try:
        throttle.wait()
        response = (request or _bounded_get)(
            url,
            params=params,
            headers=headers,
            timeout=30.0,
            follow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError(f"unexpected HTTP status {response.status_code}")
        payload = response.content
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise ValueError("response exceeded size budget")
        metadata.checksum = checksum_bytes(payload)
        metadata.retrieved_at = datetime.now(UTC)
        if validate is not None:
            validate(payload)
        entry = cache_put(
            cache_dir,
            source,
            key,
            payload,
            url,
            license_tag,
            requested_params=public_params,
        )
        metadata.status = SourceStatus.FETCHED
        metadata.retrieved_at = datetime.fromisoformat(entry.fetched_at)
        metadata.detail["http_status"] = response.status_code
        return finish(payload, metadata)
    except (
        httpx.HTTPError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        UnicodeError,
    ) as exc:
        metadata.detail["error"] = safe_error(exc)
        # Retain the failed attempt even when stale-cache recovery succeeds.
        record_metadata(session, metadata)
        if cached_payload is not None and cached.entry is not None:
            stale_metadata = metadata.model_copy(deep=True)
            stale_metadata.status = SourceStatus.STALE_CACHE
            stale_metadata.cache_status = "stale"
            stale_metadata.checksum = cached.entry.checksum
            stale_metadata.retrieved_at = datetime.fromisoformat(cached.entry.fetched_at)
            stale_metadata.detail["warning"] = (
                "live fetch failed; expired cache used; source degraded"
            )
            return finish(cached_payload, stale_metadata)
        return FetchedPayload(None, metadata)


def check_dates(start: date | None, end: date | None) -> None:
    if start and end and start > end:
        raise ValueError("start date must not be after end date")


def sorted_unique(points: list[Any]) -> list[Any]:
    if not points:
        raise ValueError("source returned no usable observations")
    points.sort(key=lambda point: point.date)
    if len({point.date for point in points}) != len(points):
        raise ValueError("source returned duplicate observation dates")
    return points


def unavailable_macro(
    *, source: str, series_id: str, url: str, license_tag: str, detail: dict[str, Any]
) -> MacroSeries:
    return MacroSeries(
        series_id=series_id,
        metadata=SourceMetadata(
            source=source,
            url=url,
            license_tag=license_tag,
            cache_status="unavailable",
            status=SourceStatus.UNAVAILABLE,
            detail=detail,
        ),
    )


def unavailable_market(
    *, source: str, symbol: str, url: str, license_tag: str, detail: dict[str, Any]
) -> MarketSeries:
    return MarketSeries(
        symbol=symbol,
        metadata=SourceMetadata(
            source=source,
            url=url,
            license_tag=license_tag,
            cache_status="unavailable",
            status=SourceStatus.UNAVAILABLE,
            detail=detail,
        ),
    )
