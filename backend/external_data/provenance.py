"""Provenance records for external datasets and experiment runs (Phase 20).

Hashes, row/column counts, versions, seeds, and configurations are recorded so
every published number can be traced back to a specific raw file and setup.
Timestamps appear only as documentation metadata; they are never used as
computational inputs.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

TRACKED_PACKAGES = (
    "pandas",
    "numpy",
    "scikit-learn",
    "shap",
    "matplotlib",
    "pydantic",
    "scipy",
    "joblib",
)


@dataclass(frozen=True)
class SourceRef:
    """Where a raw file came from, if verifiable."""

    name: str
    url: str
    kaggle_ref: str | None
    license: str
    license_verified: bool
    verification: str


def sha256_file(path: str | Path) -> str:
    """Streamed SHA-256 of a file (raw files are never modified)."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str]:
    """Versions of the packages that materially affect results."""
    versions: dict[str, str] = {}
    for name in TRACKED_PACKAGES:
        try:
            versions[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def environment_record() -> dict[str, Any]:
    """Python + package environment for reproducibility (metadata only)."""
    return {
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "packages": package_versions(),
    }


def build_provenance(
    *,
    dataset_id: str,
    file_path: str | Path,
    source: SourceRef,
    rows: int,
    columns: int,
    seeds: dict[str, int],
    configuration: dict[str, Any],
    recorded_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble a provenance record for one raw dataset + experiment setup."""
    path = Path(file_path)
    stamp = recorded_at or datetime.now(UTC)
    return {
        "dataset_id": dataset_id,
        "file_name": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": rows,
        "columns": columns,
        "source": {
            "name": source.name,
            "url": source.url,
            "kaggle_ref": source.kaggle_ref,
            "license": source.license,
            "license_verified": source.license_verified,
            "verification": source.verification,
        },
        "seeds": seeds,
        "configuration": configuration,
        "environment": environment_record(),
        # Documentation metadata only; never consumed by any computation.
        "recorded_at_utc": stamp.isoformat(),
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> Path:
    """Persist an artifact as sorted, UTF-8 JSON (deterministic bytes)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return target


def read_json(path: str | Path) -> dict[str, Any]:
    """Load a previously written JSON artifact."""
    return json.loads(Path(path).read_text(encoding="utf-8"))
