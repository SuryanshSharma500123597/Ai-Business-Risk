"""Typed contracts for the ML anomaly-detection engine (Phase 5).

Every contract carries the frozen disclaimers: model attribution is not
causal explanation, and an ML anomaly is not a financial-risk judgment.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Feature-schema version for the Phase 5 ML feature matrix. Bumped whenever
# the feature list, derivation, or preprocessing changes.
FEATURE_SCHEMA_VERSION = "1.0.0"

# Version of the persisted ML model artifact format.
MODEL_VERSION = "1.0.0"

CAUSALITY_DISCLAIMER = (
    "Model attribution, not causal explanation: drivers explain the model's "
    "output, not the business cause."
)

ANOMALY_RISK_DISCLAIMER = (
    "An ML anomaly flag marks unusual multi-ratio behavior; it is not a "
    "financial-risk judgment and never replaces the Phase 4 risk score."
)

SYNTHETIC_EVAL_DISCLAIMER = (
    "Evaluation uses synthetic injected anomalies only; no real-world "
    "predictive validity is claimed."
)


class Provenance(BaseModel):
    """Provenance carried on every ML engine output."""

    model_config = ConfigDict(extra="forbid")

    generator_seeds: list[int] = Field(default_factory=list)
    registry_version: str = ""
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    model_version: str = MODEL_VERSION
    random_state: int = 0
    input_fingerprint: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


class AnomalyResult(BaseModel):
    """Per-period anomaly outcome for one company."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = ""
    period_end: date | None = None
    anomaly_score: float = Field(ge=0.0, le=1.0)
    is_anomaly: bool = False
    decision_value: float = 0.0
    rule_score: float = 0.0
    rule_flag: bool = False
    injected_label: bool = False
    status: Literal["ok", "missing_input", "insufficient_history", "disabled"] = "ok"
    provenance: Provenance = Field(default_factory=Provenance)


class DriverContribution(BaseModel):
    """One attributed feature driver for a flagged period."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    attribution: float
    feature_value: float | None = None
    direction: Literal["pushes_anomalous", "pushes_normal"] = "pushes_anomalous"


class AnomalyExplanation(BaseModel):
    """Local explanation for one flagged observation."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = ""
    period_end: date | None = None
    explainer: str = ""
    explainer_version: str = ""
    drivers: list[DriverContribution] = Field(default_factory=list)
    background: str = ""
    causality_note: str = CAUSALITY_DISCLAIMER
    anomaly_note: str = ANOMALY_RISK_DISCLAIMER


class ModelMetadata(BaseModel):
    """Versioned metadata describing a trained ML artifact."""

    model_config = ConfigDict(extra="forbid")

    model_type: str = "isolation_forest"
    model_version: str = MODEL_VERSION
    feature_schema_version: str = FEATURE_SCHEMA_VERSION
    feature_names: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    random_state: int = 0
    threshold: float = 0.0
    training_fingerprint: str = ""
    provenance: Provenance = Field(default_factory=Provenance)


class MLFinding(BaseModel):
    """Minimal projection for the future Phase 9 ``MLFindings`` consumer."""

    model_config = ConfigDict(extra="forbid")

    period_end: date | None = None
    score: float = Field(ge=0.0, le=1.0)
    top_drivers: list[str] = Field(default_factory=list)
