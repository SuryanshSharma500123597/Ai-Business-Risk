"""Deterministic preprocessing, dataset audit, and leakage controls (Phases 1, 6, 7).

Design rules:
- Every transformation is deterministic and recorded in ``PreprocessingConfig``.
- Target labels never influence preprocessing parameters (no target exists in
  either external dataset, and the guards below fail loudly if one appears in
  the feature list).
- Missing values are never silently imputed: rows with missing features are
  dropped exactly where the frozen ``fit_isolation_forest`` contract drops them
  (``frame.dropna()``), and the row filter is recorded.
- Outliers are not removed: no methodological justification exists for
  trimming external observations, and trimming would bias anomaly detection.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.external_data.contracts import (
    ColumnAudit,
    DatasetAudit,
    LeakageCheck,
    LeakageReport,
    PreprocessingConfig,
)

TARGET_NAME_PATTERN = re.compile(
    r"(^class$|bankrupt|target|label|failed|failure|default|outcome|y$|ground.?truth)",
    re.IGNORECASE,
)
ROLE_OVERRIDE: dict[str, str] = {
    "id": "identifier",
    "company": "metadata",
    "category": "categorical",
    "year": "date",
    "status_label": "target",
}
# Metadata columns that must never become model features (mirrors the frozen
# Phase 5 FORBIDDEN_COLUMNS policy: identifiers, time, labels, metadata).
FORBIDDEN_FEATURE_COLUMNS = frozenset(
    {"ID", "id", "Company", "Company ", "Category", "Year", "class", "Class"}
)


def _role_for(name: str, series: pd.Series) -> str:
    stripped = name.strip().lower()
    override = ROLE_OVERRIDE.get(stripped)
    if override is not None:
        return override
    if TARGET_NAME_PATTERN.search(stripped):
        return "target"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"
    return "categorical"


def audit_frame(
    frame: pd.DataFrame,
    *,
    dataset_id: str,
    file_name: str,
    identifier_columns: list[str],
    date_columns: list[str],
    duplicate_id_column: str | None = None,
) -> DatasetAudit:
    """Compute the full Phase 1 audit facts for one dataframe."""
    columns = [str(c) for c in frame.columns]
    audits: list[ColumnAudit] = []
    constant_columns: list[str] = []
    near_constant_columns: list[str] = []
    identifier_cols: list[str] = []
    categorical_cols: list[str] = []
    numerical_cols: list[str] = []
    date_cols: list[str] = []
    target_candidates: list[str] = []
    class_distribution: dict[str, int] | None = None
    notes: list[str] = []

    rows = len(frame)
    for name in columns:
        series = frame[name]
        role = _role_for(name, series)
        missing = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        min_v: float | None = None
        max_v: float | None = None
        negative_count = 0
        zero_count = 0
        nonfinite_count = 0
        if pd.api.types.is_numeric_dtype(series):
            raw = series.to_numpy(dtype=float)
            finite = raw[np.isfinite(raw)]
            min_v = float(finite.min()) if finite.size else None
            max_v = float(finite.max()) if finite.size else None
            negative_count = int(np.sum(raw < 0))
            zero_count = int(np.sum(raw == 0))
            nonfinite_count = int(np.sum(~np.isfinite(raw)))
        audits.append(
            ColumnAudit(
                name=name,
                dtype=str(series.dtype),
                role=role,  # type: ignore[arg-type]
                missing_count=missing,
                missing_pct=round(100.0 * missing / rows, 4) if rows else 0.0,
                unique_count=unique,
                min=min_v,
                max=max_v,
                negative_count=negative_count,
                zero_count=zero_count,
                nonfinite_count=nonfinite_count,
            )
        )
        if unique <= 1:
            constant_columns.append(name)
        elif unique <= 2 and rows >= 50:
            near_constant_columns.append(name)
        if role == "identifier":
            identifier_cols.append(name)
        elif role == "categorical":
            categorical_cols.append(name)
        elif role == "numeric":
            numerical_cols.append(name)
        elif role == "date":
            date_cols.append(name)
        if role == "target":
            target_candidates.append(name)

    if not target_candidates:
        # Cardinality screening fallback: low-cardinality non-numeric,
        # non-metadata columns are surfaced for manual review.
        for name in columns:
            if name in identifier_columns or name in date_columns:
                continue
            series = frame[name]
            if pd.api.types.is_numeric_dtype(series):
                continue
            unique = int(series.nunique(dropna=True))
            if 1 < unique <= 20:
                target_candidates.append(name)

    if target_candidates:
        distribution = frame[target_candidates[0]].value_counts(dropna=False)
        class_distribution = {str(k): int(v) for k, v in distribution.items()}

    dup_ids = (
        int(frame[duplicate_id_column].duplicated().sum())
        if duplicate_id_column and duplicate_id_column in frame.columns
        else None
    )
    duplicate_rows = int(frame.duplicated().sum())
    if duplicate_rows:
        notes.append(f"{duplicate_rows} fully duplicated rows present")
    if any(a.missing_count > 0 for a in audits):
        missing_cols = [a.name for a in audits if a.missing_count > 0]
        notes.append(f"missing values in: {', '.join(missing_cols)}")
    if constant_columns:
        notes.append(f"constant columns: {', '.join(constant_columns)}")

    return DatasetAudit(
        dataset_id=dataset_id,
        file_name=file_name,
        rows=rows,
        columns=columns,
        column_audits=audits,
        duplicate_rows=duplicate_rows,
        duplicate_id_count=dup_ids,
        constant_columns=constant_columns,
        near_constant_columns=near_constant_columns,
        identifier_columns=identifier_cols,
        categorical_columns=categorical_cols,
        numerical_columns=numerical_cols,
        date_columns=date_cols,
        target_candidates=target_candidates,
        target_present=bool(target_candidates),
        class_distribution=class_distribution,
        suspicious_notes=notes,
    )


def build_feature_matrix(
    frame: pd.DataFrame,
    columns: list[str],
    *,
    dataset_id: str,
) -> pd.DataFrame:
    """Select and coerce the numeric feature block, deterministically.

    Raises if a forbidden identifier/metadata/label column is requested, so
    leakage by construction is impossible.
    """
    offenders = [c for c in columns if c in FORBIDDEN_FEATURE_COLUMNS]
    if offenders:
        raise ValueError(f"{dataset_id}: forbidden feature columns requested: {offenders}")
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{dataset_id}: columns absent from raw file: {missing}")
    matrix = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce").astype(float)
    values = matrix.to_numpy(dtype=float)
    bad = int(np.sum(~np.isfinite(values) & ~np.isnan(values)))
    if bad:
        raise ValueError(f"{dataset_id}: {bad} non-finite values in feature matrix")
    return matrix


def leakage_audit(
    *,
    dataset_id: str,
    feature_columns: list[str],
    target_columns: list[str],
    forbidden_columns: list[str],
    preprocessing_uses_target: bool,
    duplicate_cross_split: bool | None,
    time_order_leakage: bool | None,
) -> LeakageReport:
    """Explicit Phase 7 leakage audit; any failed check blocks the experiment."""
    checks: list[LeakageCheck] = []
    leaked_targets = sorted(set(feature_columns) & set(target_columns))
    checks.append(
        LeakageCheck(
            name="target_not_in_features",
            passed=not leaked_targets,
            detail=(
                "no target column present in feature matrix"
                if not leaked_targets
                else f"target leaked into features: {leaked_targets}"
            ),
        )
    )
    leaked_forbidden = sorted(set(feature_columns) & set(forbidden_columns))
    checks.append(
        LeakageCheck(
            name="identifiers_and_metadata_not_in_features",
            passed=not leaked_forbidden,
            detail=(
                "identifiers/time/metadata excluded from features"
                if not leaked_forbidden
                else f"forbidden columns in features: {leaked_forbidden}"
            ),
        )
    )
    checks.append(
        LeakageCheck(
            name="preprocessing_independent_of_target",
            passed=not preprocessing_uses_target,
            detail=(
                "preprocessing parameters are computed from feature data only"
                if not preprocessing_uses_target
                else "preprocessing used target labels"
            ),
        )
    )
    if duplicate_cross_split is None:
        checks.append(
            LeakageCheck(
                name="no_duplicate_entities_across_splits",
                passed=True,
                detail="not applicable: no supervised train/evaluation split exists",
            )
        )
    else:
        checks.append(
            LeakageCheck(
                name="no_duplicate_entities_across_splits",
                passed=not duplicate_cross_split,
                detail=(
                    "no duplicated entity crosses split boundaries"
                    if not duplicate_cross_split
                    else "duplicated entities found across split boundary"
                ),
            )
        )
    if time_order_leakage is None:
        checks.append(
            LeakageCheck(
                name="no_future_information_in_historical_features",
                passed=True,
                detail="not applicable: no temporal supervised features are constructed",
            )
        )
    else:
        checks.append(
            LeakageCheck(
                name="no_future_information_in_historical_features",
                passed=not time_order_leakage,
                detail=(
                    "features are strictly trailing"
                    if not time_order_leakage
                    else "future information found in historical features"
                ),
            )
        )
    return LeakageReport(dataset_id=dataset_id, checks=checks)


def make_preprocessing_config(
    *,
    dataset_id: str,
    version: str,
    features: list[str],
    transforms: list[str],
    encoding: str,
    scaling: str,
    missing_value_strategy: str,
    row_filter: str,
    random_seed: int,
    notes: list[str],
) -> PreprocessingConfig:
    """Build the recorded preprocessing configuration (Phase 6)."""
    return PreprocessingConfig(
        dataset_id=dataset_id,
        version=version,
        features=list(features),
        transforms=list(transforms),
        encoding=encoding,
        scaling=scaling,
        missing_value_strategy=missing_value_strategy,
        row_filter=row_filter,
        random_seed=random_seed,
        notes=list(notes),
    )


def relative_name(path: str | Path) -> str:
    """File name only — artifacts never embed absolute local paths."""
    return Path(path).name


def round_dict(payload: dict[str, Any], digits: int = 6) -> dict[str, Any]:
    """Round floats for stable serialization of computed summaries."""
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, float):
            out[key] = round(value, digits) if math.isfinite(value) else value
        else:
            out[key] = value
    return out
