"""Unit tests for Phase 5 artifact training, loading, and checksums."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.ml_engine.features import FEATURE_NAMES, build_feature_frame
from backend.ml_engine.models import fit_isolation_forest
from backend.ml_engine.train import (
    ARTIFACT_METADATA_FILENAME,
    ARTIFACT_MODEL_FILENAME,
    checksum_file,
    load_artifact,
    train_artifact,
)


def _frame() -> pd.DataFrame:
    company = generate_company(SyntheticCompanyConfig(seed=3001, periods=24))
    return build_feature_frame(company.periods)


def test_train_and_load_roundtrip(tmp_path: Path) -> None:
    artifact = train_artifact(
        _frame(),
        output_dir=tmp_path,
        expected_anomaly_rate=0.1,
        generator_seeds=[3001],
        registry_version="phase5",
    )
    assert artifact.model_path.exists()
    assert artifact.metadata_path.exists()
    assert artifact.metadata.threshold > 0.0
    assert list(artifact.metadata.feature_names) == list(FEATURE_NAMES)
    assert artifact.metadata.provenance.generator_seeds == [3001]
    assert artifact.metadata.provenance.registry_version == "phase5"
    assert artifact.metadata.provenance.detail["complete_rows"] > 0

    fitted, metadata = load_artifact(tmp_path)
    assert list(fitted.feature_names) == list(FEATURE_NAMES)
    assert metadata.threshold == artifact.metadata.threshold
    fresh = fit_isolation_forest(_frame())
    assert fitted.decision_values(_frame()) == fresh.decision_values(_frame())


def test_metadata_json_written_and_checksum_matches(tmp_path: Path) -> None:
    artifact = train_artifact(_frame(), output_dir=tmp_path, expected_anomaly_rate=0.1)
    payload = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    assert payload["feature_names"] == list(FEATURE_NAMES)
    digest = checksum_file(artifact.model_path)
    assert len(digest) == 64
    assert digest == hashlib.sha256(artifact.model_path.read_bytes()).hexdigest()


@pytest.mark.parametrize("rate", [0.0, 1.0, -0.5, 1.5])
def test_invalid_expected_rate_rejected(tmp_path: Path, rate: float) -> None:
    with pytest.raises(ValueError, match="expected_anomaly_rate"):
        train_artifact(_frame(), output_dir=tmp_path, expected_anomaly_rate=rate)


def test_load_rejects_metadata_schema_mismatch(tmp_path: Path) -> None:
    artifact = train_artifact(_frame(), output_dir=tmp_path, expected_anomaly_rate=0.1)
    meta = json.loads(artifact.metadata_path.read_text(encoding="utf-8"))
    meta["feature_names"] = ["tampered_feature"]
    artifact.metadata_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="model/metadata feature schema mismatch"):
        load_artifact(tmp_path)


def test_load_rejects_unknown_feature_schema(tmp_path: Path) -> None:
    train_artifact(_frame(), output_dir=tmp_path, expected_anomaly_rate=0.1)
    model_path = tmp_path / ARTIFACT_MODEL_FILENAME
    metadata_path = tmp_path / ARTIFACT_METADATA_FILENAME
    payload = joblib.load(model_path)
    renamed = ["renamed_feature"] * len(payload["feature_names"])
    payload["feature_names"] = renamed
    joblib.dump(payload, model_path)
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    meta["feature_names"] = renamed
    metadata_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="FEATURE_SCHEMA_VERSION"):
        load_artifact(tmp_path)
