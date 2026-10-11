"""Adapter for ``data/raw/kaggle/bankruptcy/Bankruptcy.csv`` (Phase 4).

Verified provenance (see ``provenance_record`` in ``run_experiment``): the file
is byte-identical (SHA-256) to ``bankruptcy_Test_X.csv`` of the Kaggle dataset
``lupitaastari/bankruptcy`` — an unlabeled competition *test* feature matrix
(``ID + Attr1..Attr64``). The companion labeled ``bankruptcy_Train.csv``
(10,000 rows, no ID) is a *different* row set: only 55/5000 of our rows are
content-identical to it, so no complete label set exists for the provided
file. Supervised and label-gated evaluations are therefore structurally
unavailable and must be reported as such — never fabricated.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.external_data.contracts import DatasetAudit
from backend.external_data.preprocessing import audit_frame, build_feature_matrix

BANKRUPTCY_ID_COLUMN = "ID"
BANKRUPTCY_FEATURE_COLUMNS: tuple[str, ...] = tuple(f"Attr{i}" for i in range(1, 65))
BANKRUPTCY_HEADER: tuple[str, ...] = (BANKRUPTCY_ID_COLUMN, *BANKRUPTCY_FEATURE_COLUMNS)


class BankruptcySchemaError(ValueError):
    """Raised when the raw bankruptcy file does not match the verified schema."""


def load_bankruptcy(path: str | Path) -> pd.DataFrame:
    """Load and strictly validate the raw bankruptcy CSV (never modified)."""
    frame = pd.read_csv(path)
    header = tuple(str(c) for c in frame.columns)
    if header == BANKRUPTCY_HEADER:
        pass
    elif len(header) == len(BANKRUPTCY_HEADER) + 1 and header[-1].lower() == "class":
        # A 66-column upstream variant would carry the label; keep it visible
        # but out of the feature block.
        pass
    else:
        raise BankruptcySchemaError(
            "Bankruptcy.csv schema mismatch: expected ID + Attr1..Attr64 "
            f"(+ optional Class); got {len(header)} columns"
        )
    if frame.empty:
        raise BankruptcySchemaError("Bankruptcy.csv contains no data rows")
    try:
        ids = pd.to_numeric(frame[BANKRUPTCY_ID_COLUMN], errors="raise").astype("int64")
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise BankruptcySchemaError(f"ID column is not integral: {exc}") from exc
    if ids.duplicated().any():
        raise BankruptcySchemaError("ID column contains duplicates")
    frame = frame.copy()
    frame[BANKRUPTCY_ID_COLUMN] = ids
    for column in BANKRUPTCY_FEATURE_COLUMNS:
        if column not in frame.columns:
            raise BankruptcySchemaError(f"missing feature column {column}")
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def target_columns(frame: pd.DataFrame) -> list[str]:
    """Return label columns if present; empty for the provided (test) file."""
    return [c for c in frame.columns if str(c).lower() == "class"]


def feature_columns(frame: pd.DataFrame) -> list[str]:
    """Feature block: Attr1..Attr64 only (ID and any label excluded)."""
    missing = [c for c in BANKRUPTCY_FEATURE_COLUMNS if c not in frame.columns]
    if missing:
        raise BankruptcySchemaError(f"missing feature columns: {missing}")
    return list(BANKRUPTCY_FEATURE_COLUMNS)


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Numeric feature matrix (64 anonymized ratios), deterministic order."""
    return build_feature_matrix(
        frame,
        feature_columns(frame),
        dataset_id="bankruptcy",
    )


def audit(path: str | Path) -> DatasetAudit:
    """Phase 1 audit for the bankruptcy dataset."""
    frame = pd.read_csv(path)
    return audit_frame(
        frame,
        dataset_id="bankruptcy",
        file_name=Path(path).name,
        identifier_columns=["ID"],
        date_columns=[],
        duplicate_id_column="ID",
    )
