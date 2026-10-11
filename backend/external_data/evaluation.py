"""External evaluation runners (Phases 8, 9, 15).

Everything here *reuses* frozen project contracts without modification:

- ``fit_isolation_forest`` / ``threshold_from_expected_rate`` (Phase 5 model
  and threshold policy),
- ``rolling_rule_baseline`` (Phase 5 rule baseline),
- ``evaluate_methods`` (frozen metric set) — only when real labels exist,
- ``attribute_row`` / ``global_summary`` / ``explain_flagged_period`` (Phase 5
  explanation paths).

No label-gated metric is ever computed without real labels; unavailability is
returned as an explicit ``EvaluationOutcome`` record instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from backend.external_data.contracts import (
    EXPECTED_ANOMALY_RATE,
    RANDOM_SEED,
    AnomalyRun,
    EvaluationOutcome,
)
from backend.external_data.preprocessing import round_dict
from backend.ml_engine.baseline import rolling_rule_baseline
from backend.ml_engine.evaluate import evaluate_methods
from backend.ml_engine.explain import EXPLAINER_SEED
from backend.ml_engine.features import fingerprint_frame
from backend.ml_engine.models import (
    FittedIsolationForest,
    fit_isolation_forest,
    threshold_from_expected_rate,
)


def run_isolation_forest(
    features: pd.DataFrame,
    *,
    dataset_id: str,
    expected_rate: float = EXPECTED_ANOMALY_RATE,
    random_state: int = RANDOM_SEED,
) -> tuple[FittedIsolationForest, AnomalyRun, list[float], list[bool]]:
    """Fit the existing Phase 5 Isolation Forest on external features.

    The model class, hyperparameters (n_estimators=200, max_samples='auto',
    max_features=1.0, bootstrap=False), robust median/IQR scaling, seed 42,
    and train-quantile threshold policy are the frozen project configuration,
    applied unchanged to the external feature matrix. The model is fit on
    complete rows only (``frame.dropna()``) — the frozen contract — and the
    row filter is reported through the run record.
    """
    complete = features.dropna()
    fitted = fit_isolation_forest(complete)
    decisions = fitted.decision_values(complete)
    threshold = threshold_from_expected_rate(fitted.train_decision, expected_rate)
    flags = [(-value) >= threshold for value in decisions]
    scores = fitted.anomaly_scores(complete)
    score_summary = round_dict(
        {
            "min": float(np.min(scores)),
            "max": float(np.max(scores)),
            "mean": float(np.mean(scores)),
            "median": float(np.median(scores)),
            "p90": float(np.percentile(scores, 90)),
            "flag_rate": float(np.mean(flags)),
        }
    )
    run = AnomalyRun(
        dataset_id=dataset_id,
        n_observations=int(len(complete)),
        n_features=int(len(fitted.feature_names)),
        feature_names=list(fitted.feature_names),
        model="IsolationForest (frozen Phase 5 configuration)",
        parameters=dict(fitted.config),
        threshold_policy=(
            f"train quantile at expected rate {expected_rate:.6f} "
            "(same policy form as frozen Phase 5 golden)"
        ),
        threshold=threshold,
        flagged_count=int(sum(flags)),
        score_summary=score_summary,
        dataset_fingerprint=fingerprint_frame(complete, config={"seed": random_state}),
    )
    return fitted, run, scores, flags


def unavailable_evaluation(dataset_id: str, reason: str) -> EvaluationOutcome:
    """Explicit record: label-gated metrics cannot be computed for this dataset."""
    return EvaluationOutcome(dataset_id=dataset_id, available=False, reason=reason)


def evaluate_against_labels(
    *,
    dataset_id: str,
    scores: list[float],
    flags: list[bool],
    labels: list[bool],
    baseline_scores: list[float],
    baseline_flags: list[bool],
    fingerprint: str,
    threshold_policy: str,
) -> EvaluationOutcome:
    """Run the frozen metric set — only callable with genuine labels.

    Kept for completeness and unit-tested with toy labels; the actual external
    datasets carry no labels, so experiment runs record
    ``unavailable_evaluation`` instead of fabricated metrics.
    """
    if len(labels) != len(scores) or not labels:
        return unavailable_evaluation(
            dataset_id,
            "no evaluation labels available for this dataset",
        )
    report = evaluate_methods(
        model_scores=scores,
        model_flags=flags,
        baseline_scores=baseline_scores,
        baseline_flags=baseline_flags,
        labels=labels,
        dataset_fingerprint=fingerprint,
        threshold_policy=threshold_policy,
    )
    return EvaluationOutcome(
        dataset_id=dataset_id,
        available=True,
        reason="evaluated against genuine labels with the frozen metric set",
        metrics=round_dict(
            {
                "pr_auc": report.model.pr_auc,
                "roc_auc": report.model.roc_auc,
                "precision": report.model.metrics_at_threshold["precision"],
                "recall": report.model.metrics_at_threshold["recall"],
                "f1": report.model.metrics_at_threshold["f1"],
                "baseline_pr_auc": report.baseline.pr_auc,
                "baseline_roc_auc": report.baseline.roc_auc,
            }
        ),
        detail={"verdict": report.verdict, "n_labels": len(labels)},
    )


CROSS_SECTIONAL_BASELINE_REASON = (
    "The frozen rolling z-score/IQR rule baseline computes trailing windows over "
    "row order and is only valid for an ordered temporal series. This dataset is "
    "cross-sectional (no time column; row order is an identifier order), so every "
    "trailing-window statistic would be meaningless. The baseline is therefore "
    "recorded as unavailable rather than reported with an invalid flag rate."
)

FROZEN_RULE_PARAMETERS: dict[str, float | int] = {
    "window": 12,
    "min_periods": 8,
    "z_threshold": 3.0,
    "iqr_multiplier": 1.5,
}


def external_rule_baseline(
    features: pd.DataFrame,
    *,
    dataset_id: str,
    groups: Sequence[object] | None = None,
    years: Sequence[object] | None = None,
) -> dict[str, Any]:
    """Applicability-gated wrapper around the frozen Phase 5 rule baseline.

    Frozen code (``rolling_rule_baseline``) is called *unchanged*; this wrapper
    only decides whether a valid application exists and, when it does, isolates
    it:

    - ``groups=None`` (cross-sectional / unordered data) -> an explicit
      ``available=False`` record with the reason; the frozen function is never
      called because trailing-row windows have no valid meaning there.
    - ``groups`` provided -> complete rows are re-sorted to
      (group, year ascending) and the frozen function is called **once per
      group**, so rolling windows never cross group (company) boundaries and
      only past observations enter every window. Rows with fewer than
      ``min_periods`` within-group predecessors are unscorable and reported as
      such; flag statistics are computed over scorable rows only.
    """
    parameters = dict(FROZEN_RULE_PARAMETERS)
    if groups is None:
        return {
            "dataset_id": dataset_id,
            "available": False,
            "reason": CROSS_SECTIONAL_BASELINE_REASON,
            "method": "rolling z-score / IQR rule baseline (frozen parameters)",
            "parameters": parameters,
            "frozen_function_called": False,
            "flagged_count": None,
            "n_scorable": 0,
            "flag_rate": None,
        }
    if years is None:
        raise ValueError(f"{dataset_id}: groups provided without years for chronological ordering")
    if len(groups) != len(features) or len(years) != len(features):
        raise ValueError(f"{dataset_id}: groups/years must align with the feature frame")

    order_frame = pd.DataFrame(
        {
            "group": pd.Series(list(groups), dtype=str).to_numpy(),
            "year": pd.to_numeric(pd.Series(list(years)), errors="raise").to_numpy(),
            "row": np.arange(len(features)),
        }
    )
    # (group, year ascending): windows become strictly past-only per company.
    order_frame = order_frame.sort_values(
        ["group", "year"], kind="mergesort"
    ).reset_index(drop=True)
    sorted_features = features.iloc[order_frame["row"].to_numpy()].reset_index(drop=True)

    window = int(parameters["window"])
    min_periods = int(parameters["min_periods"])
    per_group: dict[str, dict[str, int]] = {}
    flagged_total = 0
    scorable_total = 0
    groups_seen = order_frame["group"].unique()
    for group in groups_seen:
        idx = order_frame.index[order_frame["group"] == group]
        sub = sorted_features.iloc[idx]
        result = rolling_rule_baseline(sub)
        n_rows = len(sub)
        scorable = sum(1 for i in range(n_rows) if min(i, window) >= min_periods)
        group_flags = [
            flag
            for i, flag in enumerate(result.flags)
            if min(i, window) >= min_periods
        ]
        flagged_total += sum(1 for flag in group_flags if flag)
        scorable_total += scorable
        per_group[str(group)] = {
            "n_rows": n_rows,
            "n_scorable": scorable,
            "n_flagged": sum(1 for flag in group_flags if flag),
        }

    return {
        "dataset_id": dataset_id,
        "available": True,
        "reason": (
            "applied per group (company) in chronological order with the frozen "
            "parameters; windows are trailing-row only within a group"
        ),
        "method": "rolling z-score / IQR rule baseline (frozen parameters, per-group)",
        "parameters": parameters,
        "frozen_function_called": True,
        "grouping": "one independent series per group; sorted by (group, year ascending)",
        "cross_boundary_guarantee": (
            "the frozen function is called on each group's own sub-frame, so no "
            "window can span two groups and no future observation enters a window"
        ),
        "window_semantics_note": (
            "frozen window=12/min_periods=8 are period counts: 12 annual periods "
            "here versus 12 monthly periods in the synthetic environment "
            "(parameters unchanged, not retuned)"
        ),
        "n_groups": int(len(groups_seen)),
        "n_observations": int(len(features)),
        "n_scorable": int(scorable_total),
        "n_unscorable": int(len(features) - scorable_total),
        "unscorable_reason": (
            "fewer than min_periods=8 prior observations within the same group"
        ),
        "flagged_count": int(flagged_total),
        "flag_rate": (
            round(flagged_total / scorable_total, 6) if scorable_total else None
        ),
        "per_group": per_group,
        "flag_rate_denominator": "scorable rows only",
        "interpretation_note": (
            "flag rates are baseline breach rates, not verified anomaly prevalence"
        ),
    }


def runtime_explainer_class(fitted: FittedIsolationForest, frame: pd.DataFrame) -> str:
    """Resolved ``shap.Explainer`` class for the frozen attribution parameters.

    Constructs the explainer exactly as ``backend.ml_engine.explain`` does
    (callable ``decision_function``, ``Independent`` masker capped at 50
    background samples, seed 42) and reports the concrete class SHAP dispatches
    to — the authoritative runtime terminology for external-evaluation
    metadata. Never claims TreeSHAP.
    """
    try:
        import shap
    except ImportError:  # pragma: no cover - shap is a hard project dependency
        return "unavailable (shap not installed)"
    try:
        matrix = fitted.scaled_matrix(frame)
        background = matrix[: min(len(matrix), 50)]
        explainer = shap.Explainer(
            fitted.model.decision_function,
            shap.maskers.Independent(background, max_samples=50),
            seed=EXPLAINER_SEED,
        )
    except Exception:  # noqa: BLE001 - metadata must never break the experiment
        return "unavailable (explainer construction failed)"
    return f"{type(explainer).__module__}.{type(explainer).__name__}"
