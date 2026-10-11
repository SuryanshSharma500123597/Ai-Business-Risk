"""Tests for Workstream D: the isolated UCI 572 supervised benchmark.

Covers input validation, target separation, class-imbalance audit, leakage
safeguards, split integrity, determinism, and metric reproducibility. The
heavy numeric tests run on the real downloaded dataset only when it is present;
the schema/leakage/determinism tests use small synthetic fixtures and require
no network access.

This suite never modifies frozen Phase 4-8 code, the anonymized Kaggle dataset,
or the raw UCI bytes. It is a separate, self-contained benchmark.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.external_data.uci_bankruptcy import (
    TARGET_COLUMN,
    UCIDataError,
    audit_uci,
    load_feature_frame,
)
from backend.external_data.uci_benchmark import (
    RANDOM_SEED,
    TEST_SIZE,
    build_models,
    run_benchmark,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_CSV = REPO_ROOT / "data" / "raw" / "uci" / "data.csv"
REAL_ZIP = REPO_ROOT / "data" / "raw" / "uci" / "taiwanese-bankruptcy-prediction.zip"

requires_real_data = pytest.mark.skipif(
    not REAL_CSV.exists(), reason="UCI raw CSV not downloaded"
)


def _synth_uci(tmp_path: Path, n: int = 400, seed: int = 0) -> Path:
    """Write a small synthetic CSV that mimics the UCI 572 schema.

    95 float features + a binary 'Bankrupt?' target with the target in the
    FIRST column (matching the real file) and a ~3% positive rate.
    """
    rng = np.random.default_rng(seed)
    n_pos = max(2, int(round(n * 0.03)))
    n_neg = n - n_pos
    y = np.array([1] * n_pos + [0] * n_neg)
    rng.shuffle(y)
    feats = {f"f{i}": rng.normal(size=n) for i in range(95)}
    df = pd.DataFrame({TARGET_COLUMN: y, **feats})
    p = tmp_path / "uci_synth.csv"
    df.to_csv(p, index=False)
    return p


# --------------------------------------------------------------------------- #
# Schema validation and target separation
# --------------------------------------------------------------------------- #
def test_audit_rejects_missing_target(tmp_path: Path) -> None:
    df = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
    p = tmp_path / "no_target.csv"
    df.to_csv(p, index=False)
    with pytest.raises(UCIDataError, match="target"):
        audit_uci(p)


def test_audit_rejects_too_few_features(tmp_path: Path) -> None:
    df = pd.DataFrame({TARGET_COLUMN: [0, 1, 0], "a": [1.0, 2.0, 3.0]})
    p = tmp_path / "few.csv"
    df.to_csv(p, index=False)
    with pytest.raises(UCIDataError, match="features"):
        audit_uci(p)


def test_audit_rejects_non_binary_target(tmp_path: Path) -> None:
    feats = {f"f{i}": np.arange(4.0) for i in range(95)}
    df = pd.DataFrame({TARGET_COLUMN: [0, 1, 2, 3], **feats})
    p = tmp_path / "multiclass.csv"
    df.to_csv(p, index=False)
    with pytest.raises(UCIDataError, match="binary"):
        audit_uci(p)


def test_load_feature_frame_separates_target_and_drops_constant(tmp_path: Path) -> None:
    feats = {f"f{i}": np.arange(6.0) for i in range(94)}
    feats["const"] = np.full(6, 5.0)  # a constant column must be dropped
    df = pd.DataFrame({TARGET_COLUMN: [0, 0, 0, 0, 1, 1], **feats})
    p = tmp_path / "sep.csv"
    df.to_csv(p, index=False)
    X, y = load_feature_frame(p)
    assert TARGET_COLUMN not in X.columns
    assert "const" not in X.columns
    assert list(pd.unique(y)) == [0, 1]
    assert len(X.columns) == 94


# --------------------------------------------------------------------------- #
# Audit measurements on synthetic data
# --------------------------------------------------------------------------- #
def test_audit_measures_class_balance_and_constant(tmp_path: Path) -> None:
    p = _synth_uci(tmp_path, n=400, seed=1)
    audit = audit_uci(p)
    assert audit.n_features == 95
    assert audit.n_rows == 400
    assert audit.prevalence == pytest.approx(audit.class_counts["1"] / 400, abs=1e-9)
    assert audit.duplicate_rows == 0
    assert audit.total_missing_cells == 0
    # target must be flagged in the leakage notes
    assert any("never be used as a model feature" in n for n in audit.leakage_notes)
    # honesty notes about horizon and identity
    assert any("NOT out-of-time" in n for n in audit.leakage_notes)


# --------------------------------------------------------------------------- #
# Leakage safeguards: test set untouched; threshold chosen on training only
# --------------------------------------------------------------------------- #
def test_select_threshold_uses_only_training(tmp_path: Path) -> None:
    """The CV threshold must be computable from training data alone and must be
    reproducible. We verify determinism and that it never touches a passed-in
    test set by construction (it takes no test argument)."""
    from backend.external_data.uci_benchmark import select_threshold_cv

    rng = np.random.default_rng(3)
    X = rng.normal(size=(300, 10))
    y = (rng.random(300) < 0.1).astype(int)
    model = build_models()["LogisticRegression"]
    thr1, ap1, _ = select_threshold_cv(model, X, y)
    model2 = build_models()["LogisticRegression"]
    thr2, ap2, _ = select_threshold_cv(model2, X, y)
    assert thr1 == thr2
    assert ap1 == pytest.approx(ap2)
    assert 0.0 <= thr1 <= 1.0


def test_split_stratification_preserves_prevalence(tmp_path: Path) -> None:
    """A stratified split must keep class prevalence ~constant across partitions."""
    from sklearn.model_selection import train_test_split

    rng = np.random.default_rng(11)
    y = np.array([1] * 60 + [0] * 540)
    rng.shuffle(y)
    X = rng.normal(size=(len(y), 5))
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )
    assert y_tr.mean() == pytest.approx(y.mean(), abs=0.01)
    assert y_te.mean() == pytest.approx(y.mean(), abs=0.01)
    # determinism of the documented seed
    _, _, y_tr2, y_te2 = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )
    assert np.array_equal(y_tr, y_tr2)
    assert np.array_equal(y_te, y_te2)


# --------------------------------------------------------------------------- #
# Model reproducibility on synthetic data (no network)
# --------------------------------------------------------------------------- #
def test_benchmark_reproducible_on_synthetic(tmp_path: Path) -> None:
    """Two runs on the same synthetic file must produce identical metrics."""
    from sklearn.model_selection import train_test_split

    p = _synth_uci(tmp_path, n=500, seed=5)
    X, y = load_feature_frame(p)
    y = y.to_numpy()
    X_tr, X_te, y_tr, y_te = train_test_split(
        X.to_numpy(dtype="float64"), y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )
    aps = []
    for _ in range(2):
        row = {}
        for name, model in build_models().items():
            from backend.external_data.uci_benchmark import evaluate_model

            res = evaluate_model(name, model, X_tr, y_tr, X_te, y_te)
            row[name] = res.average_precision
        aps.append(row)
    assert aps[0] == pytest.approx(aps[1])


# --------------------------------------------------------------------------- #
# Real-dataset numeric tests (run only when the official CSV is present)
# --------------------------------------------------------------------------- #
@requires_real_data
def test_real_audit_schema() -> None:
    audit = audit_uci(REAL_CSV, REAL_ZIP)
    assert audit.n_rows == 6819
    assert audit.n_features == 95
    assert audit.target_column == TARGET_COLUMN
    assert audit.class_counts["1"] == 220
    assert audit.prevalence == pytest.approx(220 / 6819, abs=1e-9)
    assert audit.duplicate_rows == 0
    assert audit.total_missing_cells == 0
    assert " Net Income Flag" in audit.constant_columns
    assert audit.csv_sha256 != ""


@requires_real_data
def test_real_benchmark_beats_no_skill() -> None:
    """Every real model's average precision must exceed the no-skill reference
    (positive prevalence); the dummy baseline must sit at ~no-skill."""
    summary = run_benchmark(REAL_CSV)
    no_skill = summary["no_skill_average_precision"]
    assert no_skill == pytest.approx(220 / 6819, abs=1e-3)
    by_model = {r["model"]: r["average_precision"] for r in summary["results"]}
    dummy = by_model["DummyClassifier(stratified)"]
    assert dummy == pytest.approx(no_skill, abs=0.02)
    for name, ap in by_model.items():
        if name == "DummyClassifier(stratified)":
            continue
        assert ap > no_skill, f"{name} did not beat no-skill"


@requires_real_data
def test_real_benchmark_split_balance() -> None:
    summary = run_benchmark(REAL_CSV)
    tr = next(s for s in summary["splits"] if s["name"] == "train")
    te = next(s for s in summary["splits"] if s["name"] == "test")
    assert tr["n_rows"] + te["n_rows"] == 6819
    assert tr["class_counts"]["1"] + te["class_counts"]["1"] == 220
    # stratified: prevalence roughly constant across partitions
    assert tr["prevalence"] == pytest.approx(te["prevalence"], abs=0.01)
