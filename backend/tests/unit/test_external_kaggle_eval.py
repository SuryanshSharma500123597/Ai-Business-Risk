"""Tests for the external Kaggle evaluation layer (``backend.external_data``).

Covers loaders, schema validation, provenance hashing, deterministic
preprocessing, the leakage audit, label-unavailable fallback behavior, frozen
seed behavior of the anomaly runner, Risk Engine mapping, cross-dataset
comparison outputs, and figure generation. Never modifies raw files or
frozen-phase code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from backend.external_data.bankruptcy import (
    BankruptcySchemaError,
    feature_frame,
    load_bankruptcy,
    target_columns,
)
from backend.external_data.contracts import RANDOM_SEED
from backend.external_data.evaluation import run_isolation_forest, unavailable_evaluation
from backend.external_data.figures import unavailable_notice
from backend.external_data.financial_statements import load_financial_statements, panel_summary
from backend.external_data.preprocessing import build_feature_matrix, leakage_audit
from backend.external_data.provenance import sha256_file
from backend.external_data.risk_mapping import availability_summary, evaluate_companies
from backend.external_data.run_experiment import run_cross_dataset

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_BANKRUPTCY = REPO_ROOT / "data" / "raw" / "kaggle" / "bankruptcy" / "Bankruptcy.csv"
RAW_FS = (
    REPO_ROOT
    / "data"
    / "raw"
    / "kaggle"
    / "financial statements"
    / "Financial Statements.csv"
)

# Recorded in data/processed/kaggle/*/provenance.json (verified before/after run).
EXPECTED_BANKRUPTCY_SHA256 = (
    "4d3c07357112cd3839d3c813363743777be032f2899604ba01219a9936eeba64"
)
EXPECTED_FS_SHA256 = (
    "32e38512643a626340b43a4255bf79d45a7afc66ffe9058326507cc2885cb1b5"
)


def _synthetic_features(n_rows: int = 60, n_features: int = 5) -> pd.DataFrame:
    """Deterministic complete feature frame for seed/determinism tests."""
    rng = np.random.default_rng(RANDOM_SEED)
    data = rng.normal(size=(n_rows, n_features))
    return pd.DataFrame(data, columns=[f"X{i}" for i in range(n_features)])


def test_load_bankruptcy_schema_and_shape() -> None:
    frame = load_bankruptcy(RAW_BANKRUPTCY)
    assert frame.shape == (5000, 65)
    assert list(frame.columns)[:2] == ["ID", "Attr1"]
    assert str(frame["ID"].dtype).startswith("int")
    assert target_columns(frame) == []
    features = feature_frame(frame)
    assert features.shape == (5000, 64)
    assert "ID" not in features.columns


def test_load_bankruptcy_rejects_bad_schema(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    pd.DataFrame({"a": [1], "b": [2]}).to_csv(bad, index=False)
    try:
        load_bankruptcy(bad)
    except BankruptcySchemaError:
        pass
    else:  # pragma: no cover - failure path
        raise AssertionError("BankruptcySchemaError not raised for wrong schema")


def test_load_financial_statements_normalizes_header() -> None:
    frame = load_financial_statements(RAW_FS)
    assert frame.shape[0] == 161
    # raw header has a trailing space on 'Company '; loader must strip it
    assert "Company" in frame.columns
    assert "Company " not in frame.columns
    assert frame["Year"].between(1900, 2100).all()
    panel = panel_summary(frame)
    assert panel["companies"] == 12
    assert panel["frequency"] == "annual"
    years = cast(list[int], panel["years"])
    assert years[0] == 2009
    assert years[-1] == 2023


def test_raw_files_match_recorded_sha256() -> None:
    assert sha256_file(RAW_BANKRUPTCY) == EXPECTED_BANKRUPTCY_SHA256
    assert sha256_file(RAW_FS) == EXPECTED_FS_SHA256


def test_sha256_file_is_stable(tmp_path: Path) -> None:
    payload = tmp_path / "x.bin"
    payload.write_bytes(b"abc")
    first = sha256_file(payload)
    second = sha256_file(payload)
    assert first == second
    assert len(first) == 64


def test_feature_matrix_rejects_forbidden_columns() -> None:
    frame = pd.DataFrame({"ID": [1], "Revenue": [10.0]})
    try:
        build_feature_matrix(frame, ["ID", "Revenue"], dataset_id="toy")
    except ValueError as exc:
        assert "forbidden" in str(exc)
    else:  # pragma: no cover - failure path
        raise AssertionError("forbidden column was not rejected")


def test_leakage_audit_clean_when_target_absent() -> None:
    report = leakage_audit(
        dataset_id="toy",
        feature_columns=["Attr1", "Attr2"],
        target_columns=[],
        forbidden_columns=["ID"],
        preprocessing_uses_target=False,
        duplicate_cross_split=None,
        time_order_leakage=None,
    )
    assert report.clean is True
    assert len(report.checks) == 5


def test_leakage_audit_detects_target_in_features() -> None:
    report = leakage_audit(
        dataset_id="toy",
        feature_columns=["Attr1", "Class"],
        target_columns=["Class"],
        forbidden_columns=["ID"],
        preprocessing_uses_target=True,
        duplicate_cross_split=True,
        time_order_leakage=True,
    )
    assert report.clean is False
    failed = [c.name for c in report.checks if not c.passed]
    assert "target_not_in_features" in failed
    assert "preprocessing_independent_of_target" in failed


def test_unavailable_evaluation_records_explicit_reason() -> None:
    outcome = unavailable_evaluation("bankruptcy", "no genuine labels exist")
    assert outcome.available is False
    payload = outcome.to_dict()
    assert payload["metrics"] == {}
    assert payload["reason"] == "no genuine labels exist"
    json.dumps(payload)  # must be JSON-serializable


def test_run_isolation_forest_deterministic_across_runs() -> None:
    features = _synthetic_features()
    fitted_a, run_a, scores_a, flags_a = run_isolation_forest(features, dataset_id="toy")
    fitted_b, run_b, scores_b, flags_b = run_isolation_forest(features, dataset_id="toy")
    assert scores_a == scores_b
    assert flags_a == flags_b
    assert run_a.threshold == run_b.threshold
    assert run_a.dataset_fingerprint == run_b.dataset_fingerprint
    assert run_a.parameters["random_state"] == RANDOM_SEED
    assert run_a.parameters["n_estimators"] == 200
    assert fitted_a.feature_names == fitted_b.feature_names
    assert 0.0 <= float(np.mean(flags_a)) <= 0.5


def test_run_isolation_forest_drops_incomplete_rows() -> None:
    features = _synthetic_features()
    features.loc[0, "X0"] = np.nan
    _, run, scores, flags = run_isolation_forest(features, dataset_id="toy")
    assert run.n_observations == len(features) - 1
    assert len(scores) == len(features) - 1
    assert len(flags) == len(features) - 1


def test_risk_engine_mapping_on_financial_statements() -> None:
    frame = load_financial_statements(RAW_FS)
    evaluation = evaluate_companies(frame)
    assert set(evaluation["raw"]) == set(frame["Company"].unique())
    summary = availability_summary(evaluation)
    # real coverage: a partial metric subset is computable, the rest is missing
    assert 0 < summary["metrics_computable"] <= summary["metrics_total"]
    assert set(summary["dimension_scores"]) == {
        "concentration",
        "credit",
        "financial_strength",
        "liquidity",
        "macro",
        "market",
        "operational",
    }
    # liquidity inputs (current assets/liabilities) are absent -> no fabricated scores
    assert all(
        value is None for value in summary["dimension_scores"]["liquidity"].values()
    )
    assert len(summary["composite_scores"]) == 12


def test_run_cross_dataset_writes_independent_outputs(tmp_path: Path) -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    bankruptcy = {
        "flags": list(rng.random(50) < 0.16),
        "preprocessing": {"features": [f"Attr{i}" for i in range(1, 65)]},
        "global_importance": {f"Attr{i}": 1.0 / (i + 1) for i in range(1, 65)},
    }
    financial_statements = {
        "flags": list(rng.random(40) < 0.16),
        "preprocessing": {"features": [f"F{i}" for i in range(20)]},
        "global_importance": {f"F{i}": 1.0 / (i + 1) for i in range(20)},
    }
    summary = run_cross_dataset(
        bankruptcy=bankruptcy,
        financial_statements=financial_statements,
        figures_dir=tmp_path,
    )
    assert summary["datasets_compared"] == ["bankruptcy", "financial-statements"]
    assert summary["merging"].startswith("none")
    comparison = pd.read_csv(tmp_path / "model-performance-comparison.csv")
    assert sorted(comparison["dataset"].tolist()) == ["bankruptcy", "financial-statements"]
    loaded = json.loads((tmp_path / "comparison-summary.json").read_text(encoding="utf-8"))
    assert loaded["label_gated_metrics"].startswith("unavailable")
    for name in (
        "model-performance-comparison.png",
        "risk-dimension-comparison.png",
        "feature-importance-comparison.png",
    ):
        payload = (tmp_path / name).read_bytes()
        assert payload[:8] == b"\x89PNG\r\n\x1a\n"


def test_unavailable_notice_writes_real_png(tmp_path: Path) -> None:
    target = tmp_path / "notice.png"
    result = unavailable_notice(
        target,
        title="PR curve unavailable (no labels)",
        lines=["Label-gated outputs require genuine labels."],
    )
    assert result == target
    assert target.exists()
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert target.stat().st_size > 1000


def test_processed_run_artifacts_contract() -> None:
    """If the experiment has been executed, its artifacts must satisfy contracts."""
    summary_path = REPO_ROOT / "data" / "processed" / "kaggle" / "run_summary.json"
    if not summary_path.exists():  # pragma: no cover - run-dependent
        import pytest

        pytest.skip("experiment outputs not present")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["random_seed"] == 42
    assert summary["bankruptcy"]["evaluation_available"] is False
    assert summary["financial_statements"]["evaluation_available"] is False
    assert summary["bankruptcy"]["raw_sha256"] == EXPECTED_BANKRUPTCY_SHA256
    assert summary["financial_statements"]["raw_sha256"] == EXPECTED_FS_SHA256
    for dataset in ("bankruptcy", "financial-statements"):
        base = REPO_ROOT / "data" / "processed" / "kaggle" / dataset
        evaluation = json.loads((base / "evaluation.json").read_text(encoding="utf-8"))
        assert evaluation["available"] is False
        assert evaluation["reason"]
        leakage = json.loads((base / "leakage.json").read_text(encoding="utf-8"))
        assert leakage["clean"] is True
