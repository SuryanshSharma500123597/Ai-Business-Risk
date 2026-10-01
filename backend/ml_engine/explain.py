"""Model attribution for flagged anomalies (Phase 5).

Primary path: ``shap.Explainer`` (exact per-observation mode) over the
fitted Isolation Forest ``decision_function``. The additivity identity
``base_value + sum(values) == decision_function(x)`` is verified per
explained row; rows failing the check fall back to deterministic
permutation importance on ``decision_function``.

Attribution outputs are model explanations, never causal claims.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from backend.ml_engine.contracts import (
    CAUSALITY_DISCLAIMER,
    AnomalyExplanation,
    DriverContribution,
)
from backend.ml_engine.models import FittedIsolationForest

ExplainerKind = Literal["shap_exact", "permutation"]
ADDITIVITY_TOL = 1e-6
PERMUTATION_SEED = 42
PERMUTATION_ROUNDS = 5
EXPLAINER_SEED = 42


@dataclass
class RowAttribution:
    values: list[float] = field(default_factory=list)
    base_value: float = 0.0
    explainer: ExplainerKind = "shap_exact"


def _permutation_row(
    fitted: FittedIsolationForest,
    frame: pd.DataFrame,
    row_index: int,
    *,
    rounds: int = PERMUTATION_ROUNDS,
) -> RowAttribution:
    """Deterministic permutation importance for one row (fallback path)."""
    rng = np.random.default_rng(PERMUTATION_SEED)
    matrix = fitted.scaled_matrix(frame)
    base = float(fitted.model.decision_function(matrix[row_index : row_index + 1])[0])
    n_cols = matrix.shape[1]
    importances = [0.0] * n_cols
    for _ in range(rounds):
        order = rng.permutation(matrix.shape[0])
        for col in range(n_cols):
            perturbed = matrix.copy()
            perturbed[:, col] = matrix[order, col]
            shifted = float(fitted.model.decision_function(perturbed[row_index : row_index + 1])[0])
            importances[col] += abs(base - shifted)
    totals = [v / max(rounds, 1) for v in importances]
    return RowAttribution(values=totals, base_value=base, explainer="permutation")


def _shap_exact_row(
    fitted: FittedIsolationForest,
    frame: pd.DataFrame,
    row_index: int,
) -> RowAttribution | None:
    """Exact SHAP row attribution, or None when unavailable/non-additive."""
    try:
        import shap
    except ImportError:
        return None
    try:
        matrix = fitted.scaled_matrix(frame)
        background = matrix[: min(len(matrix), 50)]
        # SHAP consumes the global NumPy RNG; pin and restore it so that
        # attributions are reproducible regardless of prior process state.
        rng_state = np.random.get_state()
        np.random.seed(EXPLAINER_SEED)
        try:
            masker = shap.maskers.Independent(background, max_samples=50)
            explainer = shap.Explainer(fitted.model.decision_function, masker, seed=EXPLAINER_SEED)
            vector = matrix[row_index : row_index + 1]
            explanation = explainer(vector)
        finally:
            np.random.set_state(rng_state)
        values = [float(v) for v in np.asarray(explanation.values)[0].tolist()]
        base_raw = np.asarray(explanation.base_values).ravel()[0]
        base_value = float(base_raw)
        decision = float(fitted.model.decision_function(vector)[0])
        if not math.isfinite(base_value) or any(not math.isfinite(v) for v in values):
            return None
        if abs(base_value + sum(values) - decision) > ADDITIVITY_TOL:
            return None
        return RowAttribution(values=values, base_value=base_value, explainer="shap_exact")
    except Exception:  # noqa: BLE001 - any SHAP failure uses the fallback
        return None


def attribute_row(
    fitted: FittedIsolationForest,
    frame: pd.DataFrame,
    row_index: int,
) -> RowAttribution:
    """Attribute one row, preferring exact SHAP with permutation fallback."""
    attribution = _shap_exact_row(fitted, frame, row_index)
    if attribution is not None:
        return attribution
    return _permutation_row(fitted, frame, row_index)


def explain_flagged_period(
    fitted: FittedIsolationForest,
    frame: pd.DataFrame,
    row_index: int,
    *,
    company_id: str = "",
    period_end: Any = None,
    top_k: int = 5,
) -> AnomalyExplanation:
    """Build a top-k local explanation for one flagged period."""
    attribution = attribute_row(fitted, frame, row_index)
    row = frame.iloc[row_index]
    ranked = sorted(
        range(len(fitted.feature_names)),
        key=lambda c: abs(attribution.values[c]),
        reverse=True,
    )[: max(top_k, 1)]
    drivers: list[DriverContribution] = []
    for col in ranked:
        name = fitted.feature_names[col]
        raw_value = row[name]
        parsed_value: float | None
        try:
            parsed_value = float(raw_value)
            if not math.isfinite(parsed_value):
                parsed_value = None
        except (TypeError, ValueError):
            parsed_value = None
        value = attribution.values[col]
        drivers.append(
            DriverContribution(
                feature=name,
                attribution=value,
                feature_value=parsed_value,
                direction="pushes_anomalous" if value < 0 else "pushes_normal",
            )
        )
    try:
        import shap as _shap

        explainer_version = str(_shap.__version__)
    except ImportError:
        explainer_version = "permutation-builtin"
    return AnomalyExplanation(
        company_id=company_id,
        period_end=period_end,
        explainer=attribution.explainer,
        explainer_version=explainer_version,
        drivers=drivers,
        background=f"training matrix ({len(frame)} rows, max 50 background samples)",
        causality_note=CAUSALITY_DISCLAIMER,
    )


def global_summary(attributions: list[RowAttribution], feature_names: list[str]) -> list[str]:
    """Rank features by mean absolute attribution over explained rows."""
    if not attributions:
        return []
    totals = [0.0] * len(feature_names)
    for attribution in attributions:
        for col, value in enumerate(attribution.values):
            totals[col] += abs(value)
    ranked = sorted(range(len(feature_names)), key=lambda c: totals[c], reverse=True)
    return [feature_names[col] for col in ranked]
