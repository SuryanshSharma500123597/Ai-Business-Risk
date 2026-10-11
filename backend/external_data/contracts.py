"""Typed contracts for the external Kaggle evaluation layer.

This package is intentionally isolated from the deterministic core: it only
*consumes* public interfaces of the Risk Engine, ML engine, and data contracts.
It never modifies frozen registries, golden fixtures, or Phase 5 methodology.

All artifacts produced from these contracts are JSON-serializable and contain
no absolute local paths and no computational timestamps (provenance timestamps
are documentation metadata only).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EXTERNAL_EVAL_VERSION = "1.0.0"
RANDOM_SEED = 42

# The frozen Phase 5 golden threshold policy is a training-set quantile at
# expected rate 4/24 (see backend/tests/golden/test_ml_goldens.py). External
# anomaly runs reuse the same operating rate so the flagging policy matches
# the frozen benchmark's form. This is an external experiment; the frozen
# synthetic benchmark itself is never re-run or overwritten.
EXPECTED_ANOMALY_RATE = 4 / 24

Role = Literal["identifier", "numeric", "categorical", "date", "target", "metadata"]
MappingStatus = Literal["mapped", "derived", "provided_not_mapped", "unmapped"]


@dataclass(frozen=True)
class ColumnAudit:
    """Per-column audit facts (Phase 1)."""

    name: str
    dtype: str
    role: Role
    missing_count: int
    missing_pct: float
    unique_count: int
    min: float | None = None
    max: float | None = None
    negative_count: int = 0
    zero_count: int = 0
    nonfinite_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DatasetAudit:
    """Full dataset audit (Phase 1) for one raw file."""

    dataset_id: str
    file_name: str
    rows: int
    columns: list[str]
    column_audits: list[ColumnAudit]
    duplicate_rows: int
    duplicate_id_count: int | None
    constant_columns: list[str]
    near_constant_columns: list[str]
    identifier_columns: list[str]
    categorical_columns: list[str]
    numerical_columns: list[str]
    date_columns: list[str]
    target_candidates: list[str]
    target_present: bool
    class_distribution: dict[str, int] | None
    suspicious_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["column_audits"] = [c for c in data["column_audits"]]
        return data


@dataclass(frozen=True)
class LeakageCheck:
    """One leakage control result (Phase 7)."""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LeakageReport:
    """Leakage audit for one dataset experiment (Phase 7)."""

    dataset_id: str
    checks: list[LeakageCheck]

    @property
    def clean(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "clean": self.clean,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class PreprocessingConfig:
    """Deterministic preprocessing record (Phase 6)."""

    dataset_id: str
    version: str
    features: list[str]
    transforms: list[str]
    encoding: str
    scaling: str
    missing_value_strategy: str
    row_filter: str
    random_seed: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnomalyRun:
    """Record of one external anomaly-detection run (Phase 8)."""

    dataset_id: str
    n_observations: int
    n_features: int
    feature_names: list[str]
    model: str
    parameters: dict[str, Any]
    threshold_policy: str
    threshold: float
    flagged_count: int
    score_summary: dict[str, float]
    dataset_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvaluationOutcome:
    """Label-gated evaluation result or an explicit unavailability record (Phase 9)."""

    dataset_id: str
    available: bool
    reason: str
    metrics: dict[str, float] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
