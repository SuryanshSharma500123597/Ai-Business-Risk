"""End-to-end external Kaggle evaluation experiment (Phases 1-21 orchestration).

Run with: ``python -m backend.external_data.run_experiment``

Produces only real outputs: JSON/CSV artifacts under
``data/processed/kaggle/`` and PNGs under ``docs/assets/external-evaluation/``.
Raw CSVs are opened read-only and verified by hash before and after the run.
Label-gated metrics (PR-AUC, ROC, confusion matrices) are recorded as explicit
"unavailable" outcomes because neither provided dataset carries labels.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.external_data import bankruptcy as bankruptcy_adapter
from backend.external_data import figures
from backend.external_data import financial_statements as fs_adapter
from backend.external_data.contracts import (
    EXTERNAL_EVAL_VERSION,
    RANDOM_SEED,
)
from backend.external_data.evaluation import (
    external_rule_baseline,
    run_isolation_forest,
    runtime_explainer_class,
    unavailable_evaluation,
)
from backend.external_data.preprocessing import (
    build_feature_matrix,
    leakage_audit,
    make_preprocessing_config,
)
from backend.external_data.provenance import (
    SourceRef,
    build_provenance,
    sha256_file,
    write_json,
)
from backend.external_data.risk_mapping import availability_summary, evaluate_companies
from backend.ml_engine.explain import (
    attribute_row,
    explain_flagged_period,
    global_summary,
)
from backend.risk_engine.engine import QuantitativeRiskEngine

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_BANKRUPTCY = REPO_ROOT / "data" / "raw" / "kaggle" / "bankruptcy" / "Bankruptcy.csv"
RAW_FS = (
    REPO_ROOT
    / "data"
    / "raw"
    / "kaggle"
    / "financial statements"
    / "Financial Statements.csv"
)
PROCESSED_ROOT = REPO_ROOT / "data" / "processed" / "kaggle"
FIGURES_ROOT = REPO_ROOT / "docs" / "assets" / "external-evaluation"

ATTRIBUTION_SAMPLE = 100  # evenly spaced rows; documented in the report
TOP_EXAMPLES = 5

NO_LABEL_REASON_BANKRUPTCY = (
    "Bankruptcy.csv is the unlabeled competition test feature matrix "
    "(byte-identical to lupitaastari/bankruptcy 'bankruptcy_Test_X.csv'). "
    "Its companion labeled train file covers a different row set (55/5000 "
    "content-identical rows), so no genuine labels exist for these 5000 rows. "
    "PR-AUC/ROC-AUC/precision/recall/F1 would require fabricated labels and "
    "are therefore not computed."
)
NO_LABEL_REASON_FS = (
    "Financial Statements.csv contains no target column of any kind; "
    "unsupervised anomaly scores cannot be evaluated against outcomes."
)


def _sample_indices(n_rows: int, sample: int) -> list[int]:
    """Evenly spaced deterministic row indices for explanation sampling."""
    if n_rows <= sample:
        return list(range(n_rows))
    return sorted({int(i) for i in np.linspace(0, n_rows - 1, sample)})


def _write_json_artifact(directory: Path, name: str, payload: dict[str, Any]) -> None:
    write_json(directory / name, payload)


def _explainer_metadata(
    *, dataset_id: str, fitted: Any, complete: pd.DataFrame, sample_rows: int
) -> dict[str, Any]:
    """Accurate attribution metadata: runtime class recorded, frozen label kept.

    The Phase 5 literal ``"shap_exact"`` is a known misnomer (deferred item D-1,
    ``docs/development-log.md`` and ``docs/05_ml_engine/phase-report.md``
    §11.5) and must not be renamed because the golden fixture depends on it.
    This record preserves it while stating the authoritative runtime class and
    method — no TreeSHAP claim is ever made.
    """
    runtime_cls = runtime_explainer_class(fitted, complete)
    return {
        "dataset_id": dataset_id,
        "frozen_explainer_label": "shap_exact",
        "explainer_runtime_class": runtime_cls,
        "label_note": (
            "'shap_exact' is the frozen Phase 5 internal label and a known "
            "misnomer (deferred D-1; docs/development-log.md; "
            "docs/05_ml_engine/phase-report.md section 11.5). The runtime "
            "class above is authoritative; no TreeExplainer/TreeSHAP is used."
        ),
        "attribution_method": (
            "shap.Explainer(decision_function, Independent masker, seed=42); "
            "the concrete estimator is recorded in explainer_runtime_class "
            "(a seeded Monte-Carlo permutation-family Shapley estimator); "
            "global NumPy RNG pinned and restored around every call"
        ),
        "additivity_note": (
            "efficiency (base_value + sum(values) == decision_function(x)) is "
            "verified per row at tolerance 1e-6; exact additivity does not "
            "imply exact attribution (documented seed-to-seed drift ~2.2e-4, "
            "docs/05_ml_engine/phase-report.md section 11)"
        ),
        "sampling": (
            f"{sample_rows} evenly spaced rows of {len(complete)} complete rows "
            "(ATTRIBUTION_SAMPLE=100)"
        ),
        "background": (
            "first up-to-50 complete rows in file order "
            "(Independent masker, max_samples=50); background composition "
            "follows the source CSV row order"
        ),
        "fallback": (
            "deterministic permutation importance "
            "(backend.ml_engine.explain._permutation_row) when SHAP fails or "
            "the per-row additivity check does not hold"
        ),
        "causality_note": "model explanations only, never causal claims",
    }


BANKRUPTCY_TRANSFORMS = [
    "strict schema validation (ID + Attr1..Attr64, optional Class kept out of features)",
    "ID coerced to int64 and checked for duplicates",
    "Attr columns coerced to numeric (invalid parses become NaN and drop out)",
    "no imputation: complete rows only, matching frozen fit_isolation_forest",
    "no scaling stored at this stage (median/IQR scaling lives inside the frozen model)",
    "no target-derived handling needed (no target column present)",
]


def run_bankruptcy_experiment(
    *,
    processed_dir: Path,
    figures_dir: Path,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    """Phases 1, 4, 6-8, 15 for the unlabeled Bankruptcy test matrix."""
    pre_hash = sha256_file(RAW_BANKRUPTCY)
    raw = bankruptcy_adapter.load_bankruptcy(RAW_BANKRUPTCY)
    features = bankruptcy_adapter.feature_frame(raw)
    audit = bankruptcy_adapter.audit(RAW_BANKRUPTCY)
    config = make_preprocessing_config(
        dataset_id="bankruptcy",
        version=EXTERNAL_EVAL_VERSION,
        features=list(features.columns),
        transforms=list(BANKRUPTCY_TRANSFORMS),
        encoding="none (all features numeric)",
        scaling="none at adapter stage; robust median/IQR inside frozen Isolation Forest",
        missing_value_strategy=(
            "drop incomplete rows inside frozen fit_isolation_forest; no imputation"
        ),
        row_filter="complete rows only (frozen contract frame.dropna())",
        random_seed=RANDOM_SEED,
        notes=[
            "deterministic: column order fixed Attr1..Attr64; seed 42 on the model",
            "ID excluded from features (identifier, mirrors frozen FORBIDDEN_COLUMNS)",
        ],
    )
    leakage = leakage_audit(
        dataset_id="bankruptcy",
        feature_columns=list(features.columns),
        target_columns=[],
        forbidden_columns=["ID"],
        preprocessing_uses_target=False,
        duplicate_cross_split=None,
        time_order_leakage=None,
    )
    if not leakage.clean:  # pragma: no cover - defensive; should never trigger
        raise RuntimeError(f"leakage detected for bankruptcy: {leakage.to_dict()}")
    fitted, run, scores, flags = run_isolation_forest(features, dataset_id="bankruptcy")
    # Cross-sectional matrix: no valid temporal ordering, so the applicability
    # gate marks the rolling rule baseline unavailable (frozen function not
    # called — trailing-row windows over an ID-ordered test matrix are invalid).
    rule_record = external_rule_baseline(features, dataset_id="bankruptcy")
    complete_index = features.dropna().index
    complete_ids = raw.loc[complete_index, "ID"].tolist()
    complete = features.dropna().reset_index(drop=True)
    sample_positions = _sample_indices(len(complete), ATTRIBUTION_SAMPLE)
    rows = [attribute_row(fitted, complete, i) for i in sample_positions]
    matrix = np.asarray([row.values for row in rows], dtype=float)
    importance = {
        name: float(np.abs(matrix[:, pos]).mean())
        for pos, name in enumerate(fitted.feature_names)
    }
    ranking = global_summary(rows, fitted.feature_names)
    explainer_meta = _explainer_metadata(
        dataset_id="bankruptcy",
        fitted=fitted,
        complete=complete,
        sample_rows=len(rows),
    )
    flagged_positions = [i for i, flag in enumerate(flags) if flag][:TOP_EXAMPLES]
    examples = []
    for position in flagged_positions:
        explanation = explain_flagged_period(fitted, complete, position)
        examples.append(
            {
                "row_position": int(position),
                "explainer": explanation.explainer,
                "drivers": [
                    {
                        "feature": driver.feature,
                        "attribution": round(float(driver.attribution), 6),
                        "feature_value": driver.feature_value,
                        "direction": driver.direction,
                    }
                    for driver in explanation.drivers
                ],
            }
        )
    evaluation = unavailable_evaluation("bankruptcy", NO_LABEL_REASON_BANKRUPTCY)
    processed_dir.mkdir(parents=True, exist_ok=True)
    features.dropna().to_csv(processed_dir / "features.csv", index=False)
    pd.DataFrame(
        {"ID": complete_ids, "anomaly_score": scores, "flagged": flags}
    ).to_csv(processed_dir / "anomaly_scores.csv", index=False)
    _write_json_artifact(processed_dir, "audit.json", audit.to_dict())
    _write_json_artifact(processed_dir, "preprocessing.json", config.to_dict())
    _write_json_artifact(processed_dir, "leakage.json", leakage.to_dict())
    _write_json_artifact(processed_dir, "anomaly_run.json", run.to_dict())
    _write_json_artifact(
        processed_dir,
        "rule_baseline.json",
        rule_record,
    )
    _write_json_artifact(
        processed_dir,
        "explanations.json",
        {
            "dataset_id": "bankruptcy",
            "sample_rows": len(rows),
            "explainer_kinds": sorted({row.explainer for row in rows}),
            "explainer_metadata": explainer_meta,
            "global_ranking": ranking,
            "global_importance": {k: round(float(v), 6) for k, v in importance.items()},
            "representative_flagged_examples": examples,
            "causality_note": "model explanations only, never causal claims",
        },
    )
    _write_json_artifact(processed_dir, "evaluation.json", evaluation.to_dict())
    _write_json_artifact(
        processed_dir,
        "provenance.json",
        build_provenance(
            dataset_id="bankruptcy",
            file_path=RAW_BANKRUPTCY,
            source=SourceRef(
                name="lupitaastari/bankruptcy (bankruptcy_Test_X.csv)",
                url="https://www.kaggle.com/datasets/lupitaastari/bankruptcy",
                kaggle_ref="lupitaastari/bankruptcy",
                license="competition/dataset terms (unverified - see report)",
                license_verified=False,
                verification=(
                    "row-content equality of all 5,000 data rows with "
                    "bankruptcy_Test_X.csv; headers differ (ID vs X1 header alias)"
                ),
            ),
            rows=audit.rows,
            columns=len(audit.columns),
            seeds={"model": RANDOM_SEED, "attribution": 42},
            configuration=dict(run_config),
        ),
    )
    post_hash = sha256_file(RAW_BANKRUPTCY)
    if pre_hash != post_hash:  # pragma: no cover - defensive
        raise RuntimeError("raw bankruptcy file changed during the experiment run")

    usable = features.dropna()
    figures.feature_distributions(
        usable,
        list(usable.columns),
        figures_dir / "feature-distributions.png",
        title=(
            "Bankruptcy test matrix - feature distributions "
            "(first 12 of 64 anonymized Attr columns)"
        ),
    )
    figures.anomaly_score_distribution(
        scores,
        figures_dir / "anomaly-score-distribution.png",
        title=(
            "Bankruptcy - Isolation Forest anomaly-score distribution "
            "(frozen Phase 5 configuration)"
        ),
        threshold=run.threshold,
        flagged=flags,
    )
    figures.unavailable_notice(
        figures_dir / "dataset-class-distribution.png",
        title="Bankruptcy - class distribution unavailable (unlabeled test matrix)",
        lines=[
            "The provided Bankruptcy.csv carries no target column.",
            "It matches the competition test matrix,",
            "so no class distribution can be plotted.",
        ],
    )
    figures.unavailable_notice(
        figures_dir / "pr-curve.png",
        title="Bankruptcy - PR curve unavailable (no labels)",
        lines=[
            "Label-gated curves require genuine labels;",
            "none exist for these rows.",
        ],
    )
    figures.unavailable_notice(
        figures_dir / "roc-curve.png",
        title="Bankruptcy - ROC curve unavailable (no labels)",
        lines=[
            "Label-gated curves require genuine labels;",
            "none exist for these rows.",
        ],
    )
    figures.unavailable_notice(
        figures_dir / "confusion-matrix.png",
        title="Bankruptcy - confusion matrix unavailable (no labels)",
        lines=["No labels: anomaly scores exist, evaluation does not."],
    )
    figures.shap_summary(
        matrix,
        list(fitted.feature_names),
        figures_dir / "shap-summary.png",
        title=f"Bankruptcy - per-row attributions for top features ({len(rows)} sampled rows)",
        top_k=15,
    )
    figures.model_comparison_placeholder(
        figures_dir / "model-comparison.png",
        title="Bankruptcy - supervised comparison unavailable (no labels)",
    )
    return {
        "audit": audit.to_dict(),
        "preprocessing": config.to_dict(),
        "leakage": leakage.to_dict(),
        "anomaly_run": run.to_dict(),
        "evaluation": evaluation.to_dict(),
        "global_importance": {k: round(float(v), 6) for k, v in importance.items()},
        "global_ranking": ranking,
        "raw_sha256": post_hash,
        "fitted": fitted,
        "scores": scores,
        "flags": flags,
    }


FS_NUMERIC_FEATURES = [
    "Market Cap(in B USD)",
    "Revenue",
    "Gross Profit",
    "Net Income",
    "Earning Per Share",
    "EBITDA",
    "Share Holder Equity",
    "Cash Flow from Operating",
    "Cash Flow from Investing",
    "Cash Flow from Financial Activities",
    "Current Ratio",
    "Debt/Equity Ratio",
    "ROE",
    "ROA",
    "ROI",
    "Net Profit Margin",
    "Free Cash Flow per Share",
    "Return on Tangible Equity",
    "Number of Employees",
    "Inflation Rate(in US)",
]

FS_TRANSFORMS = [
    "strict schema validation against the 24 verified source columns",
    "Year coerced to int; Company/Category kept as metadata (never features)",
    "numeric columns coerced to float (invalid parses become NaN and drop out)",
    "no imputation: complete rows only, matching frozen fit_isolation_forest",
    "no target-derived handling needed (no target column present)",
]


def run_fs_experiment(
    *,
    processed_dir: Path,
    figures_dir: Path,
    run_config: dict[str, Any],
) -> dict[str, Any]:
    """Phases 1, 3, 4, 6-8, 13, 15 for the annual Financial Statements panel."""
    pre_hash = sha256_file(RAW_FS)
    raw = fs_adapter.load_financial_statements(RAW_FS)
    audit = fs_adapter.audit(RAW_FS)
    panel = fs_adapter.panel_summary(raw)
    available = [c for c in FS_NUMERIC_FEATURES if c in raw.columns]
    features = build_feature_matrix(raw, available, dataset_id="financial-statements")
    config = make_preprocessing_config(
        dataset_id="financial-statements",
        version=EXTERNAL_EVAL_VERSION,
        features=list(features.columns),
        transforms=list(FS_TRANSFORMS),
        encoding="none (all features numeric; Company/Category excluded)",
        scaling="none at adapter stage; robust median/IQR inside frozen Isolation Forest",
        missing_value_strategy=(
            "drop incomplete rows inside frozen fit_isolation_forest; no imputation"
        ),
        row_filter="complete rows only (frozen contract frame.dropna())",
        random_seed=RANDOM_SEED,
        notes=[
            "Company/Year/Category excluded from features (identifiers/time/metadata)",
            "annual panel: Risk Engine evaluated per company; Digital Twin not applicable",
        ],
    )
    leakage = leakage_audit(
        dataset_id="financial-statements",
        feature_columns=list(features.columns),
        target_columns=[],
        forbidden_columns=["Company", "Category", "Year"],
        preprocessing_uses_target=False,
        duplicate_cross_split=None,
        time_order_leakage=None,
    )
    if not leakage.clean:  # pragma: no cover - defensive; should never trigger
        raise RuntimeError(f"leakage detected for financial-statements: {leakage.to_dict()}")
    fitted, run, scores, flags = run_isolation_forest(features, dataset_id="financial-statements")
    # Annual panel: baseline evaluated independently per company in ascending
    # year order using only past observations within the same company.
    # Company boundaries are never crossed (external_rule_baseline gate).
    # Groups/years are taken from complete rows only so they align 1:1 with the
    # feature frame the gate evaluates.
    complete_index = features.dropna().index
    complete = features.dropna().reset_index(drop=True)
    complete_keys = raw.loc[complete_index, ["Company", "Year"]].reset_index(drop=True)
    rule_record = external_rule_baseline(
        complete,
        dataset_id="financial-statements",
        groups=list(complete_keys["Company"]),
        years=list(complete_keys["Year"]),
    )
    sample_positions = _sample_indices(len(complete), ATTRIBUTION_SAMPLE)
    rows = [attribute_row(fitted, complete, i) for i in sample_positions]
    matrix = np.asarray([row.values for row in rows], dtype=float)
    importance = {
        name: float(np.abs(matrix[:, pos]).mean())
        for pos, name in enumerate(fitted.feature_names)
    }
    ranking = global_summary(rows, fitted.feature_names)
    explainer_meta_fs = _explainer_metadata(
        dataset_id="financial-statements",
        fitted=fitted,
        complete=complete,
        sample_rows=len(rows),
    )
    flagged_positions = [i for i, flag in enumerate(flags) if flag][:TOP_EXAMPLES]
    examples = []
    for position in flagged_positions:
        company = str(complete_keys.loc[position, "Company"])
        year = int(complete_keys.loc[position, "Year"])
        explanation = explain_flagged_period(fitted, complete, position)
        examples.append(
            {
                "row_position": int(position),
                "company": company,
                "year": year,
                "explainer": explanation.explainer,
                "drivers": [
                    {
                        "feature": driver.feature,
                        "attribution": round(float(driver.attribution), 6),
                        "feature_value": driver.feature_value,
                        "direction": driver.direction,
                    }
                    for driver in explanation.drivers
                ],
            }
        )
    evaluation = unavailable_evaluation("financial-statements", NO_LABEL_REASON_FS)
    engine = QuantitativeRiskEngine()
    risk = evaluate_companies(raw, engine=engine)
    availability = availability_summary(risk)
    processed_dir.mkdir(parents=True, exist_ok=True)
    features.dropna().to_csv(processed_dir / "features.csv", index=False)
    scored = complete_keys.copy()
    scored["anomaly_score"] = scores
    scored["flagged"] = flags
    scored.to_csv(processed_dir / "anomaly_scores.csv", index=False)
    _write_json_artifact(processed_dir, "audit.json", audit.to_dict())
    _write_json_artifact(processed_dir, "panel.json", panel)
    _write_json_artifact(processed_dir, "preprocessing.json", config.to_dict())
    _write_json_artifact(processed_dir, "leakage.json", leakage.to_dict())
    _write_json_artifact(processed_dir, "anomaly_run.json", run.to_dict())
    _write_json_artifact(
        processed_dir,
        "rule_baseline.json",
        rule_record,
    )
    _write_json_artifact(
        processed_dir,
        "risk_mapping.json",
        {
            "dataset_id": "financial-statements",
            "mapping_policy": "exact semantics to canonical PeriodFinancials; total_debt derived",
            "metrics_computable": availability["metrics_computable"],
            "metrics_total": availability["metrics_total"],
            "metrics": availability["metrics"],
            "dimension_scores": availability["dimension_scores"],
            "composite_scores": availability["composite_scores"],
        },
    )
    _write_json_artifact(processed_dir, "risk_reports.json", risk["dumped"])
    _write_json_artifact(
        processed_dir,
        "explanations.json",
        {
            "dataset_id": "financial-statements",
            "sample_rows": len(rows),
            "explainer_kinds": sorted({row.explainer for row in rows}),
            "explainer_metadata": explainer_meta_fs,
            "global_ranking": ranking,
            "global_importance": {k: round(float(v), 6) for k, v in importance.items()},
            "representative_flagged_examples": examples,
            "causality_note": "model explanations only, never causal claims",
        },
    )
    _write_json_artifact(processed_dir, "evaluation.json", evaluation.to_dict())
    _write_json_artifact(
        processed_dir,
        "provenance.json",
        build_provenance(
            dataset_id="financial-statements",
            file_path=RAW_FS,
            source=SourceRef(
                name="rish59/financial-statements-of-major-companies2009-2023",
                url="https://www.kaggle.com/datasets/rish59/financial-statements-of-major-companies2009-2023",
                kaggle_ref="rish59/financial-statements-of-major-companies2009-2023",
                license=(
                    "ODbL / Database Contents (as declared on the Kaggle page; "
                    "redistribution not recommended)"
                ),
                license_verified=False,
                verification=(
                    "SHA-256 equality with the downloaded upstream data.csv; "
                    "local file renamed to Financial Statements.csv"
                ),
            ),
            rows=audit.rows,
            columns=len(audit.columns),
            seeds={"model": RANDOM_SEED, "attribution": 42},
            configuration=dict(run_config),
        ),
    )
    post_hash = sha256_file(RAW_FS)
    if pre_hash != post_hash:  # pragma: no cover - defensive
        raise RuntimeError("raw financial-statements file changed during the experiment run")
    coverage = raw.pivot_table(index="Company", columns="Year", aggfunc="size", fill_value=0)
    coverage = (coverage > 0).astype(int)
    figures.dataset_overview(
        coverage,
        figures_dir / "dataset-overview.png",
        title="Financial Statements - company x year coverage (1 = observation present)",
    )
    per_company = panel["observations_per_company"]
    assert isinstance(per_company, dict)
    figures.company_coverage(
        {str(k): int(v) for k, v in per_company.items()},
        figures_dir / "company-coverage.png",
        title=(
            "Financial Statements - observations per company "
            "(annual; Digital Twin needs monthly)"
        ),
    )
    figures.financial_trends(
        raw,
        figures_dir / "financial-trends.png",
        title="Financial Statements - annual financial trends by company (source units)",
        value_columns=["Revenue", "Net Income", "EBITDA"],
    )
    figures.risk_dimension_distribution(
        availability["dimension_scores"],
        figures_dir / "risk-dimension-distribution.png",
        title="Financial Statements - Risk Engine dimension scores by company (0-100)",
    )
    scored_fs = scored.copy()
    scored_fs["Company"] = scored_fs["Company"].astype(str)
    scored_fs["Year"] = scored_fs["Year"].astype(int)
    figures.anomaly_results_scatter(
        scored_fs,
        figures_dir / "anomaly-results.png",
        title="Financial Statements - anomaly score by year (frozen Phase 5 configuration)",
    )
    figures.shap_summary(
        matrix,
        list(fitted.feature_names),
        figures_dir / "shap-summary.png",
        title=(
            f"Financial Statements - per-row attributions for top features "
            f"({len(rows)} sampled rows)"
        ),
        top_k=15,
    )
    return {
        "audit": audit.to_dict(),
        "panel": panel,
        "preprocessing": config.to_dict(),
        "leakage": leakage.to_dict(),
        "anomaly_run": run.to_dict(),
        "evaluation": evaluation.to_dict(),
        "risk_mapping": {
            "metrics_computable": availability["metrics_computable"],
            "metrics_total": availability["metrics_total"],
            "metrics": availability["metrics"],
            "dimension_scores": availability["dimension_scores"],
            "composite_scores": availability["composite_scores"],
        },
        "global_importance": {k: round(float(v), 6) for k, v in importance.items()},
        "global_ranking": ranking,
        "raw_sha256": post_hash,
        "fitted": fitted,
        "scores": scores,
        "flags": flags,
    }


def run_cross_dataset(
    *,
    bankruptcy: dict[str, Any],
    financial_statements: dict[str, Any],
    figures_dir: Path,
) -> dict[str, Any]:
    """Phase 14 comparison without merging datasets or averaging metrics."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    bk_flags = np.asarray(bankruptcy["flags"], dtype=bool)
    fs_flags = np.asarray(financial_statements["flags"], dtype=bool)
    comparison_rows = [
        {
            "dataset": "bankruptcy",
            "method": "Isolation Forest (frozen Phase 5)",
            "n_observations": int(len(bk_flags)),
            "n_features": len(bankruptcy["preprocessing"]["features"]),
            "flagged": int(bk_flags.sum()),
            "flag_rate": round(float(bk_flags.mean()), 6) if len(bk_flags) else 0.0,
            "evaluation": "unavailable (no labels)",
        },
        {
            "dataset": "financial-statements",
            "method": "Isolation Forest (frozen Phase 5)",
            "n_observations": int(len(fs_flags)),
            "n_features": len(financial_statements["preprocessing"]["features"]),
            "flagged": int(fs_flags.sum()),
            "flag_rate": round(float(fs_flags.mean()), 6) if len(fs_flags) else 0.0,
            "evaluation": "unavailable (no labels)",
        },
    ]
    pd.DataFrame(comparison_rows).to_csv(
        figures_dir / "model-performance-comparison.csv", index=False
    )
    figures.model_comparison_placeholder(
        figures_dir / "model-performance-comparison.png",
        title="Cross-dataset - supervised comparison unavailable (neither dataset carries labels)",
    )
    coverage_matrix = pd.DataFrame(
        {
            "bankruptcy": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "financial-statements": [1.0, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0],
        },
        index=[
            "financial_strength",
            "liquidity",
            "market",
            "credit",
            "operational",
            "concentration",
            "macro",
        ],
    )
    figures.risk_dimension_comparison(
        coverage_matrix,
        figures_dir / "risk-dimension-comparison.png",
        title="Cross-dataset - Risk Engine dimension computability (1 = fully)",
    )
    figures.feature_importance_comparison(
        {
            "bankruptcy": bankruptcy["global_importance"],
            "financial-statements": financial_statements["global_importance"],
        },
        figures_dir / "feature-importance-comparison.png",
        title="Cross-dataset - top mean attribution features (normalized within dataset)",
        top_k=10,
    )
    import json as _json

    summary = {
        "datasets_compared": ["bankruptcy", "financial-statements"],
        "merging": "none: datasets evaluated independently",
        "label_gated_metrics": (
            "unavailable for both datasets (documented in evaluation.json per dataset)"
        ),
        "dimension_notes": (
            "bankruptcy Attr columns are anonymized ratios with no balance-sheet semantics, "
            "so no Risk Engine metric is computable; financial-statements supports a partial "
            "subset (see risk_mapping.json)"
        ),
        "consistency_answer": (
            "the frozen Isolation Forest + rule baseline pipeline executes deterministically "
            "on both datasets; outcome evaluation is impossible without labels, so no "
            "generalization claim beyond pipeline portability is supported"
        ),
    }
    figures_dir.joinpath("comparison-summary.json").write_text(
        _json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def build_run_config() -> dict[str, Any]:
    """Documented experiment configuration (no timestamps as computation inputs)."""
    import platform

    import sklearn

    return {
        "external_eval_version": EXTERNAL_EVAL_VERSION,
        "random_seed": RANDOM_SEED,
        "attribution_sample": ATTRIBUTION_SAMPLE,
        "top_examples": TOP_EXAMPLES,
        "anomaly_model": {
            "method": "IsolationForest (frozen Phase 5 contract)",
            "n_estimators": 200,
            "contamination": "auto",
            "random_state": RANDOM_SEED,
            "scaling": "robust median/IQR inside fit_isolation_forest",
        },
        "rule_baseline": {
            "method": "rolling z-score / IQR (frozen parameters)",
            "window": 12,
            "min_periods": 8,
            "z_threshold": 3.0,
            "iqr_multiplier": 1.5,
        },
        "python": platform.python_version(),
        "packages": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit-learn": sklearn.__version__,
            "matplotlib": __import__("matplotlib").__version__,
        },
    }


def main() -> int:
    """Run the full external evaluation end to end."""
    run_config = build_run_config()
    bk_processed = PROCESSED_ROOT / "bankruptcy"
    fs_processed = PROCESSED_ROOT / "financial-statements"
    bk_figures = FIGURES_ROOT / "bankruptcy"
    fs_figures = FIGURES_ROOT / "financial-statements"
    cross_figures = FIGURES_ROOT / "cross-dataset"
    bk = run_bankruptcy_experiment(
        processed_dir=bk_processed, figures_dir=bk_figures, run_config=run_config
    )
    fs = run_fs_experiment(
        processed_dir=fs_processed, figures_dir=fs_figures, run_config=run_config
    )
    cross = run_cross_dataset(
        bankruptcy=bk, financial_statements=fs, figures_dir=cross_figures
    )
    write_json(
        PROCESSED_ROOT / "run_summary.json",
        {
            "external_eval_version": EXTERNAL_EVAL_VERSION,
            "random_seed": RANDOM_SEED,
            "run_config": run_config,
            "bankruptcy": {
                "rows": bk["audit"]["rows"],
                "features": len(bk["preprocessing"]["features"]),
                "flagged": int(np.asarray(bk["flags"], dtype=bool).sum()),
                "evaluation_available": bk["evaluation"]["available"],
                "evaluation_reason": bk["evaluation"]["reason"],
                "raw_sha256": bk["raw_sha256"],
            },
            "financial_statements": {
                "rows": fs["audit"]["rows"],
                "companies": fs["panel"]["companies"],
                "features": len(fs["preprocessing"]["features"]),
                "flagged": int(np.asarray(fs["flags"], dtype=bool).sum()),
                "evaluation_available": fs["evaluation"]["available"],
                "raw_sha256": fs["raw_sha256"],
            },
            "cross_dataset": cross,
        },
    )
    print("external evaluation complete:")
    print(
        f"  bankruptcy rows={bk['audit']['rows']} "
        f"features={len(bk['preprocessing']['features'])}"
    )
    print(f"  financial-statements rows={fs['audit']['rows']} companies={fs['panel']['companies']}")
    print(f"  artifacts: {PROCESSED_ROOT}")
    print(f"  figures: {FIGURES_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
