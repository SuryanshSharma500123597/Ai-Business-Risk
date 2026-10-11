"""Isolated loader/audit for the official UCI Taiwanese Bankruptcy Prediction
dataset (UCI dataset id 572, DOI 10.24432/C5004D, license CC BY 4.0).

This module is STRICTLY SEPARATED from the anonymized Kaggle Bankruptcy.csv.
It never joins, relabels, or infers labels for that file, and it never touches
frozen Risk Engine, Phase 5, Digital Twin, scenario, or stress code. The
dataset has no documented prediction horizon, no company identifiers, and no
observation dates; any claim about "years in advance" is therefore unsupported.

The loader is read-only with respect to the raw file: it never normalizes,
rewrites, or overwrites the downloaded bytes. It only loads and audits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# Official UCI 572 provenance. Retrieval and license verified from the primary
# UCI source (see docs/external-evaluation/dataset-provenance-and-licensing.md).
UCI_DATASET_ID = 572
UCI_DOI = "10.24432/C5004D"
UCI_LICENSE = "CC BY 4.0"
UCI_ATTRIBUTION = (
    "Taiwanese Bankruptcy Prediction, UCI Machine Learning Repository "
    "(id 572, DOI 10.24432/C5004D), CC BY 4.0. Collected from the Taiwan "
    "Economic Journal, 1999-2009."
)
UCI_LANDING_URL = "https://archive.ics.uci.edu/dataset/572/taiwanese+bankruptcy+prediction"
UCI_ZIP_URL = "https://archive.ics.uci.edu/static/public/572/taiwanese+bankruptcy+prediction.zip"

# Target column as published (exact header, including the '?').
TARGET_COLUMN = "Bankrupt?"

# Canonical raw filenames preserved under data/raw/uci/.
RAW_ZIP_NAME = "taiwanese-bankruptcy-prediction.zip"
RAW_CSV_NAME = "data.csv"


class UCIDataError(ValueError):
    """Raised when the UCI file does not match the expected published schema."""


@dataclass(frozen=True)
class UCIAudit:
    """Machine-readable audit of the UCI 572 dataset measured from real bytes.

    Every value here is measured, not assumed. ``n_features`` excludes the
    target column. ``prevalence`` is the measured positive-class rate. No
    horizon, company identity, or date is invented.
    """

    source: str
    csv_sha256: str
    zip_sha256: str
    retrieval_url: str
    n_rows: int
    n_columns: int
    n_features: int
    target_column: str
    feature_columns: tuple[str, ...]
    class_counts: dict[str, int]
    prevalence: float
    duplicate_rows: int
    total_missing_cells: int
    columns_with_missing: tuple[str, ...]
    constant_columns: tuple[str, ...]
    near_constant_columns: tuple[tuple[str, int], ...]
    nonfinite_cells: int
    dtypes: dict[str, int]
    id_like_columns: tuple[str, ...]
    leakage_notes: tuple[str, ...] = field(default_factory=tuple)




def audit_uci(csv_path: str | Path, zip_path: str | Path | None = None) -> UCIAudit:
    """Load and audit the UCI 572 CSV from actual bytes.

    Read-only: does not mutate, delete, or impute anything. Raises
    ``UCIDataError`` if the published schema (target + >=95 features) is not met.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise UCIDataError(f"UCI CSV not found at {csv_path}")
    df = pd.read_csv(csv_path)

    if TARGET_COLUMN not in df.columns:
        raise UCIDataError(
            f"expected target column {TARGET_COLUMN!r}; got columns {list(df.columns)[:3]}..."
        )
    feature_cols = tuple(c for c in df.columns if c != TARGET_COLUMN)
    if len(feature_cols) < 95:
        raise UCIDataError(f"expected >=95 features, found {len(feature_cols)}")

    n_rows = int(len(df))
    target = df[TARGET_COLUMN]
    if set(pd.unique(target)) - {0, 1}:
        raise UCIDataError(
            f"target {TARGET_COLUMN!r} is not binary 0/1: {sorted(set(pd.unique(target)))}"
        )
    counts = target.value_counts().sort_index()
    class_counts = {str(int(k)): int(v) for k, v in counts.items()}
    prevalence = float(counts.get(1, 0) / n_rows)

    missing_per_col = df.isna().sum()
    cols_with_missing = tuple(str(c) for c in missing_per_col[missing_per_col > 0].index)

    constant = tuple(str(c) for c in df.columns if df[c].nunique(dropna=False) <= 1)
    near_const: list[tuple[str, int]] = []
    for c in df.columns:
        if c in constant:
            continue
        vc = df[c].value_counts(dropna=False)
        if len(vc) > 1 and (vc.iloc[0] / n_rows) >= 0.995:
            near_const.append((str(c), int(vc.iloc[0])))

    numeric = df.select_dtypes(include=["number"])
    nonfinite = int(np.isinf(numeric.to_numpy(dtype="float64")).sum())

    dtype_counts: dict[str, int] = {}
    for dt in df.dtypes.astype(str):
        dtype_counts[dt] = dtype_counts.get(dt, 0) + 1

    id_like = tuple(str(c) for c in df.columns if _is_id_like(str(c), df[c], n_rows))

    zip_hash = sha256_file(zip_path) if zip_path and Path(zip_path).exists() else ""
    csv_hash = sha256_file(csv_path)

    leakage_notes = (
        "No prediction horizon is documented; a random split is NOT out-of-time validation.",
        "No company identifiers or observation dates are published; entity/temporal "
        "leakage cannot be ruled out from the file alone.",
        f"Constant column(s) {list(constant)} carry no signal and are dropped from features.",
        "Target 'Bankrupt?' must never be used as a model feature.",
        "This dataset is independent of the anonymized Kaggle Bankruptcy.csv; never joined.",
    )

    return UCIAudit(
        source=UCI_LANDING_URL,
        csv_sha256=csv_hash,
        zip_sha256=zip_hash,
        retrieval_url=UCI_ZIP_URL,
        n_rows=n_rows,
        n_columns=int(df.shape[1]),
        n_features=len(feature_cols),
        target_column=TARGET_COLUMN,
        feature_columns=feature_cols,
        class_counts=class_counts,
        prevalence=prevalence,
        duplicate_rows=int(df.duplicated().sum()),
        total_missing_cells=int(missing_per_col.sum()),
        columns_with_missing=cols_with_missing,
        constant_columns=constant,
        near_constant_columns=tuple(near_const),
        nonfinite_cells=nonfinite,
        dtypes=dtype_counts,
        id_like_columns=id_like,
        leakage_notes=leakage_notes,
    )


def load_feature_frame(csv_path: str | Path) -> tuple[pd.DataFrame, pd.Series]:
    """Return (X, y) with the target separated and constant columns removed.

    No imputation or scaling here -- those are training-fold responsibilities.
    y is the binary target as int; X excludes the target and any constant column.
    """
    df = pd.read_csv(csv_path)
    if TARGET_COLUMN not in df.columns:
        raise UCIDataError(f"missing target column {TARGET_COLUMN!r}")
    y = df[TARGET_COLUMN].astype(int)
    drop = [TARGET_COLUMN]
    drop += [c for c in df.columns if c != TARGET_COLUMN and df[c].nunique(dropna=False) <= 1]
    X = df.drop(columns=drop)
    return X, y

def sha256_file(path: str | Path) -> str:
    """Streamed SHA-256 of a file; used to pin raw bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_id_like(name: str, series: pd.Series, n_rows: int) -> bool:
    """Heuristic identifier detection: near-unique integer or named-id columns.

    Used only to flag potential leakage risk; flagged columns are reported,
    never silently dropped.
    """
    nunique = series.nunique(dropna=False)
    if nunique == n_rows and pd.api.types.is_integer_dtype(series):
        return True
    return name.strip().lower() in {"id", "index", "unnamed: 0", "company", "firm", "ticker"}
