"""Offline training and versioned artifact persistence (Phase 5)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from backend.ml_engine.contracts import ModelMetadata, Provenance
from backend.ml_engine.features import FEATURE_NAMES, fingerprint_frame
from backend.ml_engine.models import (
    IsolationForestConfig,
    fit_isolation_forest,
    threshold_from_expected_rate,
)

ARTIFACT_MODEL_FILENAME = "model.joblib"
ARTIFACT_METADATA_FILENAME = "metadata.json"


@dataclass
class TrainedArtifact:
    metadata: ModelMetadata
    model_path: Path
    metadata_path: Path


def train_artifact(
    frame: pd.DataFrame,
    *,
    output_dir: str | Path,
    expected_anomaly_rate: float,
    generator_seeds: list[int] | None = None,
    registry_version: str = "",
    random_state: int = 42,
    config: IsolationForestConfig | None = None,
) -> TrainedArtifact:
    """Fit on complete rows and persist a versioned joblib + JSON artifact."""
    if not 0.0 < expected_anomaly_rate < 1.0:
        raise ValueError("expected_anomaly_rate must be in (0, 1)")
    cfg = config or IsolationForestConfig(random_state=random_state)
    fitted = fit_isolation_forest(frame, config=cfg)
    threshold = threshold_from_expected_rate(fitted.train_decision, expected_anomaly_rate)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    build_config = {
        "expected_anomaly_rate": expected_anomaly_rate,
        "if_config": fitted.config,
        "threshold": threshold,
    }
    training_fingerprint = fingerprint_frame(frame, config=build_config)
    provenance = Provenance(
        generator_seeds=list(generator_seeds or []),
        registry_version=registry_version,
        random_state=fitted.random_state,
        input_fingerprint=training_fingerprint,
        detail={"complete_rows": int(frame.dropna().shape[0])},
    )
    metadata = ModelMetadata(
        feature_names=list(fitted.feature_names),
        config={**fitted.config, "threshold": threshold},
        random_state=fitted.random_state,
        threshold=threshold,
        training_fingerprint=training_fingerprint,
        provenance=provenance,
    )
    model_path = out / ARTIFACT_MODEL_FILENAME
    metadata_path = out / ARTIFACT_METADATA_FILENAME
    joblib.dump(
        {
            "model": fitted.model,
            "feature_names": fitted.feature_names,
            "medians": fitted.medians,
            "iqrs": fitted.iqrs,
            "train_decision": fitted.train_decision,
            "random_state": fitted.random_state,
            "config": fitted.config,
        },
        model_path,
    )
    metadata_path.write_text(
        json.dumps(json.loads(metadata.model_dump_json()), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return TrainedArtifact(metadata=metadata, model_path=model_path, metadata_path=metadata_path)


def load_artifact(directory: str | Path) -> tuple[Any, ModelMetadata]:
    """Load a persisted artifact; rejects schema-mismatched content."""
    from backend.ml_engine.models import FittedIsolationForest

    directory = Path(directory)
    payload: dict[str, Any] = joblib.load(directory / ARTIFACT_MODEL_FILENAME)
    metadata = ModelMetadata.model_validate_json(
        (directory / ARTIFACT_METADATA_FILENAME).read_text(encoding="utf-8")
    )
    if list(payload.get("feature_names", [])) != list(metadata.feature_names):
        raise ValueError("artifact model/metadata feature schema mismatch")
    if tuple(payload.get("feature_names", [])) != tuple(FEATURE_NAMES):
        raise ValueError("artifact feature schema does not match FEATURE_SCHEMA_VERSION")
    fitted = FittedIsolationForest(
        model=payload["model"],
        feature_names=list(payload["feature_names"]),
        medians=dict(payload["medians"]),
        iqrs=dict(payload["iqrs"]),
        train_decision=[float(v) for v in payload["train_decision"]],
        random_state=int(payload.get("random_state", 0)),
        config=dict(payload.get("config", {})),
    )
    return fitted, metadata


def checksum_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
