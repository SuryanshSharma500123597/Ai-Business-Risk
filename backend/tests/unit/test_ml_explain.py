"""Unit tests for Phase 5 attribution and evaluation semantics."""

from __future__ import annotations

import pytest

from backend.data_engine.contracts import (
    AnomalyInjection,
    AnomalyType,
    GeneratedCompany,
    SyntheticCompanyConfig,
)
from backend.data_engine.ingest.synthetic import _anomaly_active, generate_company
from backend.ml_engine.baseline import rolling_rule_baseline
from backend.ml_engine.evaluate import evaluate_methods
from backend.ml_engine.explain import (
    attribute_row,
    explain_flagged_period,
    global_summary,
)
from backend.ml_engine.features import build_feature_frame
from backend.ml_engine.models import (
    fit_isolation_forest,
    threshold_from_expected_rate,
)


def _injected_company(seed: int = 2001) -> tuple[SyntheticCompanyConfig, GeneratedCompany]:
    config = SyntheticCompanyConfig(
        seed=seed,
        periods=24,
        inject_anomalies=[
            AnomalyInjection(
                type=AnomalyType.MARGIN_COLLAPSE,
                start_month=18,
                duration_months=4,
                magnitude=0.6,
            )
        ],
    )
    return config, generate_company(config)


def test_attribution_is_finite_and_row_associated() -> None:
    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    attribution = attribute_row(fitted, frame, 0)
    assert len(attribution.values) == len(fitted.feature_names)
    assert all(v == v for v in attribution.values)  # no NaN
    assert attribution.explainer in ("shap_exact", "permutation")


def test_explanation_top_k_drivers() -> None:
    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    explanation = explain_flagged_period(fitted, frame, 0, top_k=5)
    assert len(explanation.drivers) == 5
    assert "causal" in explanation.causality_note.lower()
    assert all(d.feature in fitted.feature_names for d in explanation.drivers)


def test_global_summary_ranks_features() -> None:
    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    attributions = [attribute_row(fitted, frame, i) for i in range(3)]
    ranked = global_summary(attributions, fitted.feature_names)
    assert set(ranked) == set(fitted.feature_names)


def test_evaluation_metrics_and_verdict() -> None:
    config, company = _injected_company()
    frame = build_feature_frame(company.periods)
    fitted = fit_isolation_forest(frame)
    scores = fitted.anomaly_scores(frame)
    threshold = threshold_from_expected_rate(fitted.train_decision, 4 / 24)
    model_flags = [(-v) >= threshold for v in fitted.decision_values(frame)]
    rule = rolling_rule_baseline(frame)
    labels = [_anomaly_active(config.inject_anomalies[0], i + 1) for i in range(len(frame))]
    report = evaluate_methods(
        model_scores=scores,
        model_flags=model_flags,
        baseline_scores=rule.scores,
        baseline_flags=rule.flags,
        labels=labels,
    )
    assert report.verdict in ("if_beats_baseline", "baseline_wins_or_tie")
    assert 0.0 <= report.model.pr_auc <= 1.0
    assert 0.0 <= report.baseline.pr_auc <= 1.0
    assert "synthetic" in report.limitation.lower()
    assert report.detail["n_injected"] == 4


def test_evaluation_inputs_must_align() -> None:
    with pytest.raises(ValueError, match="align row-for-row"):
        evaluate_methods(
            model_scores=[0.1],
            model_flags=[True, False],
            baseline_scores=[0.1],
            baseline_flags=[True],
            labels=[True],
        )


def test_evaluation_insufficient_labels_verdict() -> None:
    report = evaluate_methods(
        model_scores=[0.1, 0.2],
        model_flags=[False, False],
        baseline_scores=[0.1, 0.2],
        baseline_flags=[False, False],
        labels=[False, False],
    )
    assert report.verdict == "insufficient_labels"
    assert report.model.pr_auc == 0.0


def test_single_class_roc_and_pr_helpers() -> None:
    from backend.ml_engine.evaluate import _pr_auc, _roc_auc

    assert _roc_auc([0.1, 0.2], [True, True]) == 0.5
    assert _roc_auc([0.1, 0.2], [False, False]) == 0.5
    assert _pr_auc([0.1, 0.2], [False, False]) == 0.0


def test_permutation_row_deterministic_and_non_negative() -> None:
    from backend.ml_engine.explain import _permutation_row

    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    first = _permutation_row(fitted, frame, 0)
    second = _permutation_row(fitted, frame, 0)
    assert first.explainer == "permutation"
    assert first.values == second.values
    assert len(first.values) == len(fitted.feature_names)
    assert all(v >= 0.0 and v == v for v in first.values)


def test_attribute_row_falls_back_when_shap_row_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.ml_engine.explain as explain_module

    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    monkeypatch.setattr(explain_module, "_shap_exact_row", lambda *args, **kwargs: None)
    attribution = attribute_row(fitted, frame, 0)
    assert attribution.explainer == "permutation"


@pytest.mark.parametrize("mode", ["nan_values", "non_additive", "raises"])
def test_shap_failure_paths_fall_back(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    import types

    import numpy as np
    import shap as shap_module

    class _FakeExplainer:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __call__(self, vector: object) -> object:
            n_cols = int(vector.shape[1])  # type: ignore[attr-defined]
            if mode == "raises":
                raise RuntimeError("explainer boom")
            if mode == "nan_values":
                values = np.full((1, n_cols), np.nan)
                base = 0.0
            else:
                values = np.zeros((1, n_cols))
                base = 999.0
            return types.SimpleNamespace(values=values, base_values=np.array([base]))

    monkeypatch.setattr(shap_module, "Explainer", _FakeExplainer)
    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    attribution = attribute_row(fitted, frame, 0)
    assert attribution.explainer == "permutation"


def test_missing_shap_module_uses_permutation_and_builtins_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)
    monkeypatch.setitem(sys.modules, "shap", None)
    explanation = explain_flagged_period(fitted, frame, 0, top_k=3)
    assert explanation.explainer == "permutation"
    assert explanation.explainer_version == "permutation-builtin"
    assert len(explanation.drivers) == 3


def test_explanation_parses_non_finite_feature_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.ml_engine.explain as explain_module
    from backend.ml_engine.explain import RowAttribution

    _, company = _injected_company()
    base = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(base)
    broken = base.astype(object)
    broken.iloc[0, 0] = "not-a-number"
    broken.iloc[0, 1] = float("nan")
    values = [0.0] * len(fitted.feature_names)
    values[0] = -1.0
    values[1] = -0.5
    monkeypatch.setattr(
        explain_module,
        "attribute_row",
        lambda *args, **kwargs: RowAttribution(values=values),
    )
    explanation = explain_flagged_period(fitted, broken, 0, top_k=5)
    parsed = {driver.feature: driver.feature_value for driver in explanation.drivers}
    assert parsed[fitted.feature_names[0]] is None
    assert parsed[fitted.feature_names[1]] is None


def test_attribution_is_stable_after_global_rng_consumption() -> None:
    """Regression: PermutationExplainer samples from the global NumPy RNG.

    Attribution must be identical after unrelated RNG consumption, and must not
    leak RNG state to the caller.
    """
    import numpy as np

    from backend.ml_engine.explain import ADDITIVITY_TOL

    _, company = _injected_company()
    frame = build_feature_frame(company.periods).dropna().reset_index(drop=True)
    fitted = fit_isolation_forest(frame)

    before = attribute_row(fitted, frame, 0)

    # Burn 9,999 numbers from the GLOBAL NumPy RNG.
    np.random.seed(12345)
    np.random.rand(9999)

    after = attribute_row(fitted, frame, 0)
    assert after.values == before.values
    assert after.base_value == before.base_value

    # Additivity must still hold after the burn.
    vector = fitted.scaled_matrix(frame[0:1])
    decision = float(fitted.model.decision_function(vector)[0])
    assert abs(after.base_value + sum(after.values) - decision) < ADDITIVITY_TOL

    # The engine must restore the caller's RNG state.
    np.random.seed(4242)
    expected = np.random.get_state()[1][:8].tolist()
    _ = attribute_row(fitted, frame, 0)
    assert np.random.get_state()[1][:8].tolist() == expected


def test_global_summary_empty_input_returns_empty() -> None:
    from backend.ml_engine.features import FEATURE_NAMES

    assert global_summary([], list(FEATURE_NAMES)) == []
