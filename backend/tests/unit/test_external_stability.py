"""Tests for the Workstream C stability & threshold-sensitivity layer
(``backend.external_data.stability``).

Covers: reference reproduction against committed artifacts, threshold-sweep
monotonicity, explicit unavailability of label-gated metrics, seed ranking
stability with recorded configs, determinism, company-boundary isolation and
chronological scoring of the frozen rule baseline, and the cross-sectional
(Bankruptcy) baseline-unavailability gate. Never modifies raw files or frozen
code; seed sweeps call the frozen public API only.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.external_data.evaluation import external_rule_baseline
from backend.external_data.stability import (
    REFERENCE_RATE,
    STABILITY_SEEDS,
    rule_baseline_evidence,
    seed_rank_stability,
    threshold_sensitivity,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _toy_panel() -> tuple[pd.DataFrame, list[str], list[int]]:
    """Two companies, 12 ascending years each, deterministic values.

    Company B is deliberately given values that would look 'normal' relative to
    A; the point is to test boundary isolation, not anomaly content.
    """
    rng = np.random.default_rng(7)
    feats: list[list[float]] = []
    groups: list[str] = []
    years: list[int] = []
    for company, base in (("A", 0.0), ("B", 100.0)):
        for k in range(12):
            feats.append([base + float(rng.normal()), float(rng.normal())])
            groups.append(company)
            years.append(2010 + k)
    return pd.DataFrame(feats, columns=["X0", "X1"]), groups, years


def test_threshold_reference_reproduces_committed_artifacts() -> None:
    """Reference flag set must match the committed anomaly_scores.csv exactly."""
    for dataset_id, expected in (
        ("bankruptcy", 834),
        ("financial-statements", 27),
    ):
        result = threshold_sensitivity(dataset_id)
        repro = result["reproduction_check"]
        assert repro["recomputed_reference_flagged_count"] == expected
        assert repro["saved_artifact_flagged_count"] == expected
        assert repro["exact_match"] is True
        assert repro["mismatched_rows"] == 0


def test_threshold_sweep_is_monotonic_and_marks_reference() -> None:
    """Flag counts must be non-decreasing in rate; exactly one reference row."""
    result = threshold_sensitivity("bankruptcy")
    counts = [row["flagged_count"] for row in result["sweep"]]
    assert counts == sorted(counts)
    ref_rows = [row for row in result["sweep"] if row["is_reference"]]
    assert len(ref_rows) == 1
    assert abs(ref_rows[0]["expected_rate"] - REFERENCE_RATE) < 1e-3


def test_threshold_sensitivity_reports_no_label_metrics() -> None:
    """Label-gated metrics must be explicitly unavailable (no ground truth)."""
    result = threshold_sensitivity("financial-statements")
    assert result["label_gated_metrics"]["available"] is False
    assert "PR-AUC" in result["label_gated_metrics"]["note"]


def test_threshold_sensitivity_is_deterministic() -> None:
    """Two runs on the same dataset must be byte-identical (JSON-stable)."""
    a = json.dumps(threshold_sensitivity("financial-statements"), sort_keys=True)
    b = json.dumps(threshold_sensitivity("financial-statements"), sort_keys=True)
    assert a == b

def test_seed_stability_reference_is_perfect() -> None:
    """Seed 42 (reference) must correlate 1.0 with itself and have top-k J=1.0."""
    result = seed_rank_stability("financial-statements", top_k=27)
    ref = next(row for row in result["per_seed"] if row["is_reference"])
    assert ref["seed"] == 42
    assert ref["spearman_vs_reference"] == 1.0
    assert ref["topk_jaccard_vs_reference"] == 1.0


def test_seed_stability_records_frozen_config_per_seed() -> None:
    """Each seed records its own random_state with frozen hyperparameters intact."""
    result = seed_rank_stability("financial-statements", top_k=27)
    assert result["seeds"] == STABILITY_SEEDS
    for row in result["per_seed"]:
        cfg = row["config"]
        assert cfg["random_state"] == row["seed"]
        assert cfg["n_estimators"] == 200
        assert cfg["max_features"] == 1.0
        assert cfg["bootstrap"] is False
    assert result["frozen_core_unchanged"]


def test_seed_stability_flagged_count_is_seed_invariant() -> None:
    """Train-quantile threshold keeps the reference flagged count constant."""
    result = seed_rank_stability("financial-statements", top_k=27)
    counts = {row["flagged_count_at_reference_rate"] for row in result["per_seed"]}
    assert counts == {27}


def test_rule_baseline_bankruptcy_unavailable() -> None:
    """Cross-sectional Bankruptcy dataset must gate the rule baseline off."""
    evidence = rule_baseline_evidence()
    assert evidence["bankruptcy"]["available"] is False
    assert evidence["bankruptcy"]["frozen_function_called"] is False


def test_rule_baseline_fs_per_company_evidence() -> None:
    """FS evidence lists 12 companies with scorable = rows - 8 and totals 64/60."""
    evidence = rule_baseline_evidence()["financial-statements"]
    assert evidence["available"] is True
    per_group = evidence["per_group"]
    assert len(per_group) == 12
    for stats in per_group.values():
        assert stats["n_scorable"] == max(0, stats["n_rows"] - 8)
    assert evidence["n_scorable"] == 64
    assert evidence["flagged_count"] == 60


def test_rule_baseline_company_boundary_isolation() -> None:
    """Windows must never cross company boundaries (toy two-company panel)."""
    features, groups, years = _toy_panel()
    record = external_rule_baseline(
        features, dataset_id="toy", groups=groups, years=years
    )
    per_group = record["per_group"]
    # 12 rows per company -> 4 scorable each (min_periods=8 within the group).
    assert per_group["A"]["n_scorable"] == 4
    assert per_group["B"]["n_scorable"] == 4
    assert record["n_scorable"] == 8
    assert record["cross_boundary_guarantee"]
