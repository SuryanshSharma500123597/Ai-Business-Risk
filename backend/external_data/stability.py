"""Isolated anomaly-detection stability & threshold-sensitivity analysis.

Workstream C of the external-evaluation research program. This module is a
*read-only consumer* of the frozen Phase 5 core: it imports and **calls** the
frozen functions unchanged and never modifies them.

What it does (and does not) do:

- **Threshold sensitivity (C1):** sweeps an explicitly justified range of
  expected-rate operating points and reports flagged counts/rates and Jaccard
  overlap against the frozen reference rate (``4/24``). It applies the frozen
  ``threshold_from_expected_rate`` policy to the frozen seed-42 model.
- **Ranking stability (C2):** refits the frozen Isolation Forest at additional
  *documented* seeds (42=reference, 43, 44, 45, 46) purely to measure ranking
  stability (Spearman rank correlation, top-k Jaccard). Only
  ``IsolationForestConfig.random_state`` is varied; the production default seed
  and all other hyperparameters are unchanged. This uses the frozen public API
  ``fit_isolation_forest`` directly.
- **Rule baseline (C3):** reads the already-generated per-company rule-baseline
  evidence; introduces no parameter sweep.

It never fabricates labels, never reports precision/recall/ROC-AUC/PR-AUC/F1
(no ground truth exists), and never interprets a flag rate as real-world
anomaly prevalence. Every configuration and seed is recorded.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from backend.external_data.bankruptcy import feature_frame, load_bankruptcy
from backend.external_data.contracts import EXPECTED_ANOMALY_RATE, RANDOM_SEED
from backend.external_data.financial_statements import load_financial_statements
from backend.external_data.preprocessing import build_feature_matrix
from backend.external_data.run_experiment import (
    FS_NUMERIC_FEATURES,
    RAW_BANKRUPTCY,
    RAW_FS,
    REPO_ROOT,
)
from backend.ml_engine.models import (
    FittedIsolationForest,
    IsolationForestConfig,
    fit_isolation_forest,
    threshold_from_expected_rate,
)

# Justified expected-rate sweep. The frozen production default is 4/24 ~=
# 0.16667 (same policy form as the Phase 5 golden). The span 0.02-0.30 brackets
# the reference on both sides so classifications can be observed as the
# operating point tightens (fewer flags) or loosens (more flags). These are
# operating choices for sensitivity analysis, NOT tuned values and NOT an
# estimate of true anomaly prevalence.
THRESHOLD_RATES: list[float] = [0.02, 0.05, 0.10, 0.1667, 0.20, 0.25, 0.30]
REFERENCE_RATE: float = EXPECTED_ANOMALY_RATE  # 4/24 = 0.16666...
# Reference seed plus four variations, used only to measure ranking stability.
STABILITY_SEEDS: list[int] = [RANDOM_SEED, 43, 44, 45, 46]

_PROCESSED = REPO_ROOT / "data" / "processed" / "kaggle"


def _complete_features(dataset_id: str) -> pd.DataFrame:
    """Reproduce the exact frozen feature matrix and complete-row filter.

    Mirrors ``run_experiment`` precisely so the reference flags reproduce the
    committed artifacts: bankruptcy uses ``feature_frame``; financial statements
    uses the documented numeric feature list. Complete rows only
    (``dropna``) match the frozen ``fit_isolation_forest`` contract.
    """
    if dataset_id == "bankruptcy":
        raw = load_bankruptcy(RAW_BANKRUPTCY)
        features = feature_frame(raw)
    elif dataset_id == "financial-statements":
        raw = load_financial_statements(RAW_FS)
        available = [c for c in FS_NUMERIC_FEATURES if c in raw.columns]
        features = build_feature_matrix(raw, available, dataset_id=dataset_id)
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown dataset_id: {dataset_id}")
    return features.dropna().reset_index(drop=True)


def _saved_flags(dataset_id: str) -> np.ndarray:
    """Load the committed ``flagged`` column in file order (for reproduction)."""
    sub = "bankruptcy" if dataset_id == "bankruptcy" else "financial-statements"
    path = _PROCESSED / sub / "anomaly_scores.csv"
    frame = pd.read_csv(path)
    return frame["flagged"].astype(bool).to_numpy()


def _fit_seed(complete: pd.DataFrame, seed: int) -> tuple[FittedIsolationForest, np.ndarray]:
    """Fit the frozen Isolation Forest at an explicit documented seed."""
    fitted = fit_isolation_forest(
        complete, config=IsolationForestConfig(random_state=seed)
    )
    decisions = np.asarray(fitted.decision_values(complete), dtype=float)
    return fitted, -decisions  # score = -decision (higher = more anomalous)

def threshold_sensitivity(dataset_id: str) -> dict[str, Any]:
    """C1: flagged counts/rates and Jaccard overlap across expected rates.

    A single frozen seed-42 model is fit; the frozen quantile threshold policy
    is applied at each expected rate. No model is retrained and no production
    default is changed.
    """
    complete = _complete_features(dataset_id)
    n = int(len(complete))
    fitted = fit_isolation_forest(complete)  # frozen, seed 42
    decisions = np.asarray(fitted.decision_values(complete), dtype=float)
    neg = -decisions
    train_decision = fitted.train_decision

    ref_threshold = threshold_from_expected_rate(train_decision, REFERENCE_RATE)
    ref_flags = neg >= ref_threshold
    ref_count = int(ref_flags.sum())

    flags_by_rate: dict[float, np.ndarray] = {}
    sweep: list[dict[str, Any]] = []
    for rate in THRESHOLD_RATES:
        threshold = threshold_from_expected_rate(train_decision, rate)
        flags = neg >= threshold
        flags_by_rate[rate] = flags
        count = int(flags.sum())
        intersection = int(np.logical_and(flags, ref_flags).sum())
        union = int(np.logical_or(flags, ref_flags).sum())
        jaccard = round(intersection / union, 6) if union else None
        sweep.append(
            {
                "expected_rate": rate,
                "threshold": round(float(threshold), 10),
                "flagged_count": count,
                "flag_rate": round(count / n, 6),
                "jaccard_vs_reference": jaccard,
                "is_reference": abs(rate - REFERENCE_RATE) < 1e-3,
            }
        )

    core_mask = flags_by_rate[0.02]  # smallest flag set = most extreme
    loose_mask = flags_by_rate[0.30]  # largest flag set
    core_count = int(core_mask.sum())
    boundary_only = int(np.logical_and(loose_mask, ~core_mask).sum())

    # Reproduction check: reference flags must match the committed artifact.
    saved = _saved_flags(dataset_id)
    if saved.shape == ref_flags.shape:
        mismatches = int(np.sum(saved != ref_flags))
    else:  # pragma: no cover - defensive
        mismatches = None

    return {
        "dataset_id": dataset_id,
        "n_observations": n,
        "reference": {
            "expected_rate": REFERENCE_RATE,
            "threshold": round(float(ref_threshold), 10),
            "flagged_count": ref_count,
            "flag_rate": round(ref_count / n, 6),
        },
        "sweep": sweep,
        "core_flagged_at_0_02": core_count,
        "boundary_sensitive_flagged_only_above_0_02": boundary_only,
        "reproduction_check": {
            "saved_artifact_flagged_count": int(saved.sum()) if saved.size else None,
            "recomputed_reference_flagged_count": ref_count,
            "exact_match": mismatches == 0,
            "mismatched_rows": mismatches,
        },
        "threshold_interpretation": (
            "flag counts/rates are a direct consequence of the chosen expected-rate "
            "operating point under the frozen quantile policy; they are NOT a measured "
            "real-world anomaly prevalence"
        ),
        "label_gated_metrics": {
            "available": False,
            "note": (
                "precision/recall/F1/ROC-AUC/PR-AUC require independent ground-truth "
                "labels; none exist for this dataset, so none are computed or reported"
            ),
        },
    }

def seed_rank_stability(dataset_id: str, top_k: int) -> dict[str, Any]:
    """C2: ranking stability of the frozen IF across documented seeds.

    Uses the frozen public API with an explicit ``random_state`` override; the
    production default (seed 42) is the reference and is never changed.
    """
    complete = _complete_features(dataset_id)
    n = int(len(complete))
    neg_by_seed: dict[int, np.ndarray] = {}
    flagged_by_seed: dict[int, np.ndarray] = {}
    config_by_seed: dict[int, dict[str, Any]] = {}
    for seed in STABILITY_SEEDS:
        fitted, neg = _fit_seed(complete, seed)
        neg_by_seed[seed] = neg
        threshold = threshold_from_expected_rate(fitted.train_decision, REFERENCE_RATE)
        flagged_by_seed[seed] = neg >= threshold
        config_by_seed[seed] = dict(fitted.config)

    ref_scores = neg_by_seed[RANDOM_SEED]
    ref_order = np.argsort(-ref_scores, kind="stable")
    ref_topk = set(ref_order[:top_k].tolist())

    per_seed: list[dict[str, Any]] = []
    for seed in STABILITY_SEEDS:
        rho = spearmanr(neg_by_seed[seed], ref_scores).statistic
        order = np.argsort(-neg_by_seed[seed], kind="stable")
        topk = set(order[:top_k].tolist())
        union = topk | ref_topk
        jaccard = (len(topk & ref_topk) / len(union)) if union else None
        per_seed.append(
            {
                "seed": seed,
                "is_reference": seed == RANDOM_SEED,
                "config": config_by_seed[seed],
                "spearman_vs_reference": (
                    round(float(rho), 6) if rho == rho else None
                ),
                "topk_jaccard_vs_reference": (
                    round(float(jaccard), 6) if jaccard is not None else None
                ),
                "flagged_count_at_reference_rate": int(flagged_by_seed[seed].sum()),
            }
        )

    return {
        "dataset_id": dataset_id,
        "n_observations": n,
        "top_k": top_k,
        "reference_seed": RANDOM_SEED,
        "seeds": list(STABILITY_SEEDS),
        "rank_metric": (
            "Spearman rank correlation of -decision_function over all complete rows "
            "vs reference seed 42"
        ),
        "topk_metric": (
            f"Jaccard overlap of the top-{top_k} rows by -decision_function "
            "vs reference seed 42"
        ),
        "per_seed": per_seed,
        "frozen_core_unchanged": (
            "frozen fit_isolation_forest called unchanged; only "
            "IsolationForestConfig.random_state varied (documented); production "
            "default seed 42 and all hyperparameters unchanged"
        ),
        "interpretation": (
            "measures repeatability/stability of the ranking, NOT predictive accuracy "
            "(no ground-truth labels exist)"
        ),
    }


def rule_baseline_evidence() -> dict[str, Any]:
    """C3: read the committed per-company rule-baseline evidence (no sweep)."""
    out: dict[str, Any] = {}
    for dataset_id in ("financial-statements", "bankruptcy"):
        path = _PROCESSED / dataset_id / "rule_baseline.json"
        out[dataset_id] = json.loads(path.read_text(encoding="utf-8"))
    return out

def _configure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 200,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.grid": True,
            "grid.alpha": 0.3,
        }
    )
    return plt


def save_threshold_sensitivity_figure(
    results: dict[str, dict[str, Any]], out_path: Path
) -> None:
    """Flagged count vs expected rate for both datasets (real computed data)."""
    plt = _configure_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    titles = {
        "bankruptcy": "Bankruptcy (cross-sectional, 5,000 rows)",
        "financial-statements": "Financial Statements (12 companies, 160 rows)",
    }
    for ax, dataset_id in zip(axes, ["bankruptcy", "financial-statements"], strict=True):
        res = results[dataset_id]
        rates = [row["expected_rate"] for row in res["sweep"]]
        counts = [row["flagged_count"] for row in res["sweep"]]
        ref_rate = res["reference"]["expected_rate"]
        ax.plot(rates, counts, marker="o", color="#1f77b4")
        ax.axvline(ref_rate, color="grey", linestyle="--", linewidth=1)
        ax.set_title(titles[dataset_id])
        ax.set_xlabel("Expected-rate operating point")
        ax.set_ylabel("Flagged observations")
    fig.suptitle(
        "Threshold sensitivity of frozen Isolation Forest "
        "(flag count is an operating choice, not anomaly prevalence)"
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def save_seed_stability_figure(
    results: dict[str, dict[str, Any]], out_path: Path
) -> None:
    """Spearman rank correlation vs seed for both datasets (real computed data)."""
    plt = _configure_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    titles = {"bankruptcy": "Bankruptcy", "financial-statements": "Financial Statements"}
    for ax, dataset_id in zip(axes, ["bankruptcy", "financial-statements"], strict=True):
        res = results[dataset_id]
        seeds = [row["seed"] for row in res["per_seed"]]
        rho = [row["spearman_vs_reference"] for row in res["per_seed"]]
        ax.plot(seeds, rho, marker="o", color="#2ca02c")
        ax.set_ylim(0.0, 1.02)
        ax.set_title(titles[dataset_id])
        ax.set_xlabel("Isolation Forest random_state")
        ax.set_ylabel("Spearman rho vs seed 42")
    fig.suptitle(
        "Ranking stability of frozen Isolation Forest across seeds "
        "(repeatability, not predictive accuracy)"
    )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def run_stability(
    *, out_dir: Path, figures_dir: Path, make_figures: bool = True
) -> dict[str, Any]:
    """Run C1 + C2 + C3 for both datasets and write JSON evidence (+ figures)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    top_k = {"bankruptcy": 834, "financial-statements": 27}

    threshold_results = {
        ds: threshold_sensitivity(ds)
        for ds in ["bankruptcy", "financial-statements"]
    }
    seed_results = {
        ds: seed_rank_stability(ds, top_k[ds])
        for ds in ["bankruptcy", "financial-statements"]
    }
    rule_results = rule_baseline_evidence()

    (out_dir / "threshold_sensitivity.json").write_text(
        json.dumps(threshold_results, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "seed_rank_stability.json").write_text(
        json.dumps(seed_results, indent=2, sort_keys=True), encoding="utf-8"
    )

    figures_written: list[str] = []
    if make_figures:
        save_threshold_sensitivity_figure(
            threshold_results, figures_dir / "threshold-sensitivity.png"
        )
        save_seed_stability_figure(
            seed_results, figures_dir / "seed-rank-stability.png"
        )
        figures_written = [
            str(figures_dir / "threshold-sensitivity.png"),
            str(figures_dir / "seed-rank-stability.png"),
        ]

    return {
        "threshold_sensitivity": threshold_results,
        "seed_rank_stability": seed_results,
        "rule_baseline": rule_results,
        "figures_written": figures_written,
        "config": {
            "threshold_rates": THRESHOLD_RATES,
            "reference_rate": REFERENCE_RATE,
            "stability_seeds": STABILITY_SEEDS,
            "top_k": top_k,
        },
    }


def main() -> int:
    processed = _PROCESSED / "stability"
    figures = REPO_ROOT / "docs" / "assets" / "external-evaluation" / "cross-dataset"
    result = run_stability(out_dir=processed, figures_dir=figures, make_figures=True)
    for dataset_id in ("bankruptcy", "financial-statements"):
        repro = result["threshold_sensitivity"][dataset_id]["reproduction_check"]
        print(
            f"[{dataset_id}] reference reproduction exact_match="
            f"{repro['exact_match']} "
            f"(recomputed {repro['recomputed_reference_flagged_count']} vs saved "
            f"{repro['saved_artifact_flagged_count']})"
        )
    print(f"figures: {result['figures_written']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
