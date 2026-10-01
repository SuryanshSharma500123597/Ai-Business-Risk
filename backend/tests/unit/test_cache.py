"""Phase 3 cache integrity, TTL and offline behavior."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.data_engine.cache import (
    CacheCorruption,
    cache_get,
    cache_key,
    cache_put,
    cache_read,
    is_fresh,
)


def test_cache_roundtrip_and_metadata(tmp_path: Path) -> None:
    key = cache_key("fred", "FEDFUNDS", extension="csv")
    entry = cache_put(
        tmp_path, "fred", key, b"payload", "https://example.test", "attribution-required"
    )
    assert cache_get(tmp_path, "fred", key, 24) == b"payload"
    result = cache_read(tmp_path, "fred", key, 24)
    assert result.status == "hit"
    assert result.entry == entry
    assert entry.checksum
    assert is_fresh(entry, 24)


def test_corrupted_payload_is_reported(tmp_path: Path) -> None:
    key = "sample.bin"
    cache_put(tmp_path, "source", key, b"good", "https://example.test", "synthetic")
    (tmp_path / "raw" / "source" / key).write_bytes(b"tampered")
    result = cache_read(tmp_path, "source", key, 24)
    assert result.status == "corrupt"
    assert result.detail == "checksum mismatch"


def test_expired_entry_can_be_read_only_as_stale(tmp_path: Path) -> None:
    key = "old.bin"
    cache_put(tmp_path, "source", key, b"payload", "https://example.test", "synthetic")
    index_path = tmp_path / "raw" / "source" / "index.json"
    body = json.loads(index_path.read_text(encoding="utf-8"))
    body["entries"][key]["fetched_at"] = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    index_path.write_text(json.dumps(body), encoding="utf-8")
    assert cache_read(tmp_path, "source", key, 1).status == "stale"
    stale = cache_read(tmp_path, "source", key, 1, allow_stale=True)
    assert stale.status == "stale" and stale.payload == b"payload"


def test_invalid_index_is_explicitly_corrupt(tmp_path: Path) -> None:
    source_dir = tmp_path / "raw" / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "index.json").write_text("not json", encoding="utf-8")
    result = cache_read(tmp_path, "source", "x.bin", 24)
    assert result.status == "corrupt"
    with pytest.raises(CacheCorruption):
        cache_put(tmp_path, "source", "x.bin", b"x", "u", "synthetic")
