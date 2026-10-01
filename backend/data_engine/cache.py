"""Offline-first raw payload cache with integrity and provenance metadata.

The public helpers accept either ``data`` or ``data/raw`` as ``base_dir`` so
that the frozen environment contract and the documented directory layout are
both supported.  Payload writes use a temporary file followed by ``replace``
to avoid leaving partially-written cache files after an interrupted download.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

CacheStatus = Literal["hit", "stale", "miss", "corrupt"]
_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")


class CacheCorruption(ValueError):
    """Invalid cache metadata; never silently overwritten."""


class CacheEntry(BaseModel):
    source: str
    key: str
    url: str
    fetched_at: str  # ISO-8601 UTC
    checksum: str  # sha256 hex of payload bytes
    license_tag: str
    requested_params: dict[str, str] = Field(default_factory=dict)


class CacheIndex(BaseModel):
    entries: dict[str, CacheEntry] = Field(default_factory=dict)


class CacheRead(BaseModel):
    status: CacheStatus
    payload: bytes | None = None
    entry: CacheEntry | None = None
    detail: str | None = None


def cache_root(base_dir: str | Path, source: str) -> Path:
    """Return ``data/raw/<source>`` for both ``data`` and ``data/raw`` roots."""
    root = Path(base_dir)
    source = _safe_filename(source)
    raw_root = root if root.name.lower() == "raw" else root / "raw"
    directory = raw_root / source
    if directory.is_symlink():
        raise ValueError("cache source directory must not be a symlink")
    return directory


def checksum_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def cache_key(*parts: object, extension: str = "bin") -> str:
    """Build a deterministic, filesystem-safe cache key from request parts."""
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    label = _SAFE_KEY.sub("_", "_".join(str(part) for part in parts[:2])).strip("._")
    suffix = extension.lstrip(".") or "bin"
    return f"{label[:48] or 'payload'}-{digest}.{suffix}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _index_path(source_dir: Path) -> Path:
    return source_dir / "index.json"


def _read_index(source_dir: Path) -> CacheIndex:
    path = _index_path(source_dir)
    if not path.exists():
        return CacheIndex()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return CacheIndex.model_validate(raw)
    except ValueError as exc:
        raise CacheCorruption("invalid cache index; remove or repair explicitly") from exc


def _write_index(source_dir: Path, index: CacheIndex) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    payload = index.model_dump_json(indent=2).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix="index.", suffix=".tmp", dir=source_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, _index_path(source_dir))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _safe_filename(key: str) -> str:
    filename = Path(key).name
    if (
        filename != key
        or filename in {"", ".", "..", "index.json"}
        or any(char in key for char in '/\\\\:<>"|?*')
        or key.endswith((".", " "))
    ):
        raise ValueError(f"cache key must be a filename, got {key!r}")
    return filename


def cache_read(
    base_dir: str | Path,
    source: str,
    key: str,
    ttl_hours: float,
    *,
    allow_stale: bool = False,
) -> CacheRead:
    """Read a cache entry and explicitly report hit, miss, stale or corruption."""
    key = _safe_filename(key)
    source_dir = cache_root(base_dir, source)
    if not math.isfinite(ttl_hours) or ttl_hours < 0:
        raise ValueError("TTL must be finite and nonnegative")
    try:
        entry = _read_index(source_dir).entries.get(key)
    except (CacheCorruption, OSError):
        return CacheRead(status="corrupt", detail="unreadable or invalid cache index")
    if entry is None:
        return CacheRead(status="miss", detail="no index entry")
    if entry.key != key or entry.source != source:
        return CacheRead(status="corrupt", detail="cache metadata identity mismatch")
    path = source_dir / key
    if path.is_symlink():
        return CacheRead(status="corrupt", detail="cache payload must not be a symlink")
    if not path.exists():
        return CacheRead(status="corrupt", entry=entry, detail="payload file is missing")
    try:
        payload = path.read_bytes()
    except OSError as exc:
        return CacheRead(status="corrupt", entry=entry, detail=str(exc))
    if checksum_bytes(payload) != entry.checksum:
        return CacheRead(status="corrupt", entry=entry, detail="checksum mismatch")
    try:
        fetched = datetime.fromisoformat(entry.fetched_at)
        age = datetime.now(UTC) - fetched
        fresh = timedelta(0) <= age <= timedelta(hours=ttl_hours)
    except (ValueError, TypeError):
        fresh = False
    if fresh:
        return CacheRead(status="hit", payload=payload, entry=entry)
    if allow_stale:
        return CacheRead(status="stale", payload=payload, entry=entry, detail="TTL expired")
    return CacheRead(status="stale", entry=entry, detail="TTL expired")


def cache_get(base_dir: str | Path, source: str, key: str, ttl_hours: float) -> bytes | None:
    """Backward-compatible fresh-only cache read."""
    result = cache_read(base_dir, source, key, ttl_hours)
    return result.payload if result.status == "hit" else None


def cache_put(
    base_dir: str | Path,
    source: str,
    key: str,
    payload: bytes,
    url: str,
    license_tag: str,
    *,
    requested_params: dict[str, str] | None = None,
) -> CacheEntry:
    """Store a payload and atomically update the source index."""
    key = _safe_filename(key)
    source_dir = cache_root(base_dir, source)
    source_dir.mkdir(parents=True, exist_ok=True)
    payload_path = source_dir / key
    if payload_path.is_symlink():
        raise ValueError("cache payload must not be a symlink")
    index = _read_index(source_dir)
    fd, temporary = tempfile.mkstemp(prefix=f"{key}.", suffix=".tmp", dir=source_dir)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, payload_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    entry = CacheEntry(
        source=source,
        key=key,
        url=url,
        fetched_at=_now_iso(),
        checksum=checksum_bytes(payload),
        license_tag=license_tag,
        requested_params=requested_params or {},
    )
    index.entries[key] = entry
    _write_index(source_dir, index)
    return entry


def cache_entry(base_dir: str | Path, source: str, key: str) -> CacheEntry | None:
    return _read_index(cache_root(base_dir, source)).entries.get(_safe_filename(key))


def is_fresh(entry: CacheEntry, ttl_hours: float) -> bool:
    try:
        fetched = datetime.fromisoformat(entry.fetched_at)
        age = datetime.now(UTC) - fetched
        return timedelta(0) <= age <= timedelta(hours=ttl_hours)
    except (ValueError, TypeError):
        return False


def index_summary(base_dir: str | Path, source: str) -> list[dict[str, Any]]:
    index = _read_index(cache_root(base_dir, source))
    return [entry.model_dump() for entry in index.entries.values()]
