"""Isolated supervised benchmark for the official UCI Taiwanese Bankruptcy
Prediction dataset (UCI 572, DOI 10.24432/C5004D, CC BY 4.0).

This is Workstream D of the external-evaluation research program. It is a
fully independent experiment, run on its own dataset under data/raw/uci and
data/processed/uci-bankruptcy. It NEVER joins, relabels, or imports the
anonymized Kaggle Bankruptcy.csv, and it never modifies frozen Risk Engine,
Phase 5 ML, Digital Twin, scenario, or stress code.

Scientific framing (honest and enforced throughout):

- The dataset has NO documented prediction horizon, company identifiers, or
  observation dates. Therefore a stratified random split is reported as a
  reproducible benchmark only -- it is NOT out-of-time validation and does NOT
  establish years-in-advance prediction.
- Average Precision (PR-AUC) is the primary metric (imbalanced 3.23% positive
  class), reported alongside ROC-AUC, precision, recall, F1, balanced accuracy,
  confusion matrix, and positive-class prevalence.
- All preprocessing is fit inside training folds only; the held-out test set is
  untouched until final evaluation; the operating threshold is chosen by
  cross-validation on the training partition, never on the test set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.external_data.uci_bankruptcy import (
    UCI_ATTRIBUTION,
    UCI_DOI,
    UCI_LICENSE,
    audit_uci,
    load_feature_frame,
)

# Fixed, documented seed for the split and any stochastic estimator.
RANDOM_SEED = 42
TEST_SIZE = 0.20
CV_FOLDS = 5

# Repo layout (isolated from the Kaggle evaluation outputs).
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_CSV = REPO_ROOT / "data" / "raw" / "uci" / "data.csv"
RAW_ZIP = REPO_ROOT / "data" / "raw" / "uci" / "taiwanese-bankruptcy-prediction.zip"
OUT_DIR = REPO_ROOT / "data" / "processed" / "uci-bankruptcy"


@dataclass(frozen=True)
class SplitReport:
    """Class balance of a partition -- measured, not assumed."""

    name: str
    n_rows: int
    class_counts: dict[str, int]
    prevalence: float


@dataclass(frozen=True)
class ModelResult:
    """Measured metrics for one model on the held-out test set."""

    model: str
    average_precision: float
    roc_auc: float
    precision: float
    recall: float
    f1: float
    balanced_accuracy: float
    confusion_matrix: list[list[int]]
    prevalence: float
    threshold: float
    cv_average_precision_mean: float | None = None
    cv_average_precision_std: float | None = None
    config: dict[str, Any] = field(default_factory=dict)


def build_models() -> dict[str, Any]:
    """Four approved estimators with documented configs and a fixed seed.

    Logistic Regression uses training-fold standardization (a Pipeline so the
    scaler is fit inside each fold). No XGBoost (dependency not present) and no
    frozen Phase 5 model is used or modified.
    """
    return {
        "DummyClassifier(stratified)": DummyClassifier(
            strategy="stratified", random_state=RANDOM_SEED
        ),
        "LogisticRegression": Pipeline(
            steps=[
                ("scale", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=RANDOM_SEED,
                    ),
                ),
            ]
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=300, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1
        ),
        "HistGradientBoosting": HistGradientBoostingClassifier(random_state=RANDOM_SEED),
    }


def select_threshold_cv(
    pipeline_or_clf: Any, X: np.ndarray, y: np.ndarray
) -> tuple[float, float, float]:
    """Pick the classification threshold by CV strictly inside the training set.

    Uses predicted probabilities from out-of-fold predictions and chooses the
    threshold that maximizes F1 on the training data only. Returns
    (threshold, cv_mean_ap, cv_std_ap). The held-out test set is never used here.
    """
    skf = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    oof = np.zeros(len(y), dtype=float)
    aps: list[float] = []
    for tr, va in skf.split(X, y):
        model = pipeline_or_clf
        model.fit(X[tr], y[tr])
        p = model.predict_proba(X[va])[:, 1]
        oof[va] = p
        aps.append(average_precision_score(y[va], p))
    prec, rec, thr = precision_recall_curve(y, oof)
    f1 = np.divide(2 * prec * rec, prec + rec, out=np.zeros_like(prec), where=(prec + rec) > 0)
    best = int(np.argmax(f1[: len(thr)])) if len(thr) else 0
    threshold = float(thr[best]) if len(thr) else 0.5
    return threshold, float(np.mean(aps)), float(np.std(aps))


def evaluate_model(
    name: str,
    model: Any,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> ModelResult:
    """Train on the training partition and evaluate once on the held-out set.

    The threshold is chosen by CV on training only; metrics are then computed a
    single time on the untouched test partition.
    """
    threshold, cv_ap_mean, cv_ap_std = select_threshold_cv(model, X_train, y_train)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    pred = (proba >= threshold).astype(int)
    cm = confusion_matrix(y_test, pred, labels=[0, 1])
    return ModelResult(
        model=name,
        average_precision=float(average_precision_score(y_test, proba)),
        roc_auc=float(roc_auc_score(y_test, proba)),
        precision=float(precision_score(y_test, pred, zero_division=0)),
        recall=float(recall_score(y_test, pred, zero_division=0)),
        f1=float(f1_score(y_test, pred, zero_division=0)),
        balanced_accuracy=float(balanced_accuracy_score(y_test, pred)),
        confusion_matrix=cm.tolist(),
        prevalence=float(np.mean(y_test)),
        threshold=threshold,
        cv_average_precision_mean=cv_ap_mean,
        cv_average_precision_std=cv_ap_std,
        config={"seed": RANDOM_SEED, "test_size": TEST_SIZE, "cv_folds": CV_FOLDS},
    )


def _split_report(name: str, y: np.ndarray) -> SplitReport:
    counts = np.asarray(y)
    n = int(len(counts))
    n_pos = int(counts.sum())
    return SplitReport(
        name=name,
        n_rows=n,
        class_counts={"0": n - n_pos, "1": n_pos},
        prevalence=float(n_pos / n) if n else 0.0,
    )


def run_benchmark(csv_path: str | Path = RAW_CSV, out_dir: str | Path = OUT_DIR) -> dict[str, Any]:
    """Run the full supervised benchmark and persist JSON evidence.

    Returns a JSON-serializable dict with the audit, split reports, per-model
    metrics, the no-skill reference (positive prevalence), and provenance. The
    held-out test set is touched exactly once per model (final evaluation only).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_uci(csv_path, RAW_ZIP if Path(RAW_ZIP).exists() else None)
    X_df, y_s = load_feature_frame(csv_path)
    X = X_df.to_numpy(dtype="float64")
    y = y_s.to_numpy()

    # Single fixed-seed stratified split. Reported as a benchmark split only.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
    )

    split_reports = [_split_report("train", y_train), _split_report("test", y_test)]
    results: list[ModelResult] = []
    for name, model in build_models().items():
        results.append(evaluate_model(name, model, X_train, y_train, X_test, y_test))

    # No-skill reference for average precision equals the positive prevalence.
    no_skill_ap = float(np.mean(y_test))

    summary = {
        "provenance": {
            "dataset": "UCI Taiwanese Bankruptcy Prediction",
            "dataset_id": 572,
            "doi": UCI_DOI,
            "license": UCI_LICENSE,
            "license_verified": True,
            "attribution": UCI_ATTRIBUTION,
            "csv_sha256": audit.csv_sha256,
            "zip_sha256": audit.zip_sha256,
        },
        "audit": {
            "n_rows": audit.n_rows,
            "n_columns": audit.n_columns,
            "n_features": audit.n_features,
            "target_column": audit.target_column,
            "class_counts": audit.class_counts,
            "prevalence": audit.prevalence,
            "duplicate_rows": audit.duplicate_rows,
            "total_missing_cells": audit.total_missing_cells,
            "constant_columns": list(audit.constant_columns),
            "nonfinite_cells": audit.nonfinite_cells,
            "id_like_columns": list(audit.id_like_columns),
            "leakage_notes": list(audit.leakage_notes),
        },
        "config": {"seed": RANDOM_SEED, "test_size": TEST_SIZE, "cv_folds": CV_FOLDS},
        "splits": [
            {
                "name": s.name,
                "n_rows": s.n_rows,
                "class_counts": s.class_counts,
                "prevalence": s.prevalence,
            }
            for s in split_reports
        ],
        "no_skill_average_precision": no_skill_ap,
        "results": [r.__dict__ for r in results],
    }

    out_path = out_dir / "benchmark_results.json"
    out_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    out = run_benchmark()
    print(json.dumps({"n_models": len(out["results"]), "prevalence": out["audit"]["prevalence"]}))
