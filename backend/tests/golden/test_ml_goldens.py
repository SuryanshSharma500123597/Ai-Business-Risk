"""Phase 5 ML golden regression: pinned fixture model + dataset outputs."""

from __future__ import annotations

import json
from pathlib import Path

from backend.data_engine.contracts import (
    AnomalyInjection,
    AnomalyType,
    SyntheticCompanyConfig,
)
from backend.data_engine.ingest.synthetic import _anomaly_active, generate_company
from backend.ml_engine.baseline import rolling_rule_baseline
from backend.ml_engine.evaluate import evaluate_methods
from backend.ml_engine.explain import explain_flagged_period
from backend.ml_engine.features import build_feature_frame, fingerprint_frame
from backend.ml_engine.models import (
    fit_isolation_forest,
    threshold_from_expected_rate,
)

GOLDEN_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = GOLDEN_DIR / "ml_anomaly_golden.json"
TOLERANCE = 1e-9
EXPECTED_RATE = 4 / 24


def _build_document() -> dict:
    config = SyntheticCompanyConfig(
        seed=7101,
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
    company = generate_company(config)
    frame = build_feature_frame(company.periods)
    fitted = fit_isolation_forest(frame)
    scores = fitted.anomaly_scores(frame)
    decisions = fitted.decision_values(frame)
    threshold = threshold_from_expected_rate(fitted.train_decision, EXPECTED_RATE)
    model_flags = [(-v) >= threshold for v in decisions]
    rule = rolling_rule_baseline(frame)
    labels = [_anomaly_active(config.inject_anomalies[0], i + 1) for i in range(len(frame))]
    report = evaluate_methods(
        model_scores=scores,
        model_flags=model_flags,
        baseline_scores=rule.scores,
        baseline_flags=rule.flags,
        labels=labels,
        dataset_fingerprint=fingerprint_frame(frame, config={"seed": 7101}),
        threshold_policy=f"train quantile at expected rate {EXPECTED_RATE}",
    )
    complete = frame.dropna().reset_index(drop=True)
    fitted_complete = fit_isolation_forest(complete)
    first_flag = next(i for i, flag in enumerate(model_flags) if flag)
    complete_index = min(first_flag, len(complete) - 1)
    explanation = explain_flagged_period(fitted_complete, complete, complete_index, top_k=5)
    return {
        "seed": 7101,
        "feature_schema": "1.0.0",
        "threshold": threshold,
        "anomaly_scores": scores,
        "model_flags": model_flags,
        "rule_flags": rule.flags,
        "labels": labels,
        "verdict": report.verdict,
        "model_pr_auc": report.model.pr_auc,
        "baseline_pr_auc": report.baseline.pr_auc,
        "top_drivers": [d.feature for d in explanation.drivers],
        "explainer": explanation.explainer,
    }


def _compare(expected: object, actual: object, path: str) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected a mapping"
        assert set(expected) == set(actual), f"{path}: keys differ"
        for key in expected:
            _compare(expected[key], actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list), f"{path}: expected a list"
        assert len(expected) == len(actual), f"{path}: length differs"
        for index, (exp_item, act_item) in enumerate(zip(expected, actual, strict=True)):
            _compare(exp_item, act_item, f"{path}[{index}]")
        return
    if isinstance(expected, float):
        assert isinstance(actual, (int, float)), f"{path}: expected a number"
        assert actual == expected or abs(float(actual) - expected) <= TOLERANCE, f"{path} differs"
        return
    assert actual == expected, f"{path}: {actual!r} != {expected!r}"


def test_ml_golden_matches_pinned_outputs(regen_golden: bool) -> None:
    document = _build_document()
    if regen_golden:
        GOLDEN_PATH.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
        return
    assert GOLDEN_PATH.exists(), "missing Phase 5 golden file"
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    _compare(expected, document, "ml_golden")
