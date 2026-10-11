# UCI Taiwanese Bankruptcy Prediction — Supervised Benchmark Plan

## Objective

Establish a **defensible, independently evaluated** supervised bankruptcy-classification
benchmark on the official **UCI Taiwanese Bankruptcy Prediction** dataset
(dataset id **572**, DOI **10.24432/C5004D**, license **CC BY 4.0**). This is a
**separate experiment**: it does not validate the whole AI Business Risk platform,
does not relabel the existing anonymized Kaggle `Bankruptcy.csv`, and does not
modify any frozen phase.

## Dataset identity and provenance (verified)

- **Publisher:** UCI Machine Learning Repository — *Taiwanese Bankruptcy Prediction*.
- **DOI:** 10.24432/C5004D. **License:** CC BY 4.0 (verified on the official page).
- **Landing page:** https://archive.ics.uci.edu/dataset/572/taiwanese+bankruptcy+prediction
- **Official download (ZIP):** https://archive.ics.uci.edu/static/public/572/taiwanese+bankruptcy+prediction.zip
- **Origin:** collected from the Taiwan Economic Journal, 1999–2009.
- **Attribution:** Taiwanese Bankruptcy Prediction, UCI ML Repository (id 572,
  DOI 10.24432/C5004D), CC BY 4.0.

## Measured facts (from the downloaded bytes)

| Property | Value |
|---|---|
| Rows | 6,819 |
| Columns | 96 (target + 95 features) |
| Target | `Bankrupt?` (binary 0/1) |
| Positive class (`Bankrupt?==1`) | 220 (3.2263%) |
| Duplicate rows | 0 |
| Missing cells | 0 |
| Non-finite values | 0 |
| Constant columns | ` Net Income Flag` |
| Feature dtypes | float64 / int64 |

Raw bytes are preserved immutably under `data/raw/uci/`:
- `taiwanese-bankruptcy-prediction.zip` (SHA-256 `C346F5AD…`, 4,808,883 bytes)
- `data.csv` (SHA-256 `67BF2E7C…`, 11,456,101 bytes)

## Material limitations (must be stated everywhere)

1. **No documented prediction horizon.** The dataset does not state how many
   years before bankruptcy each observation is taken. Therefore results are a
   classification of the given financial state, **not** years-in-advance
   forecasting.
2. **No company identifiers or observation dates.** Entity-level and temporal
   leakage cannot be ruled out from the file alone; independent-sample
   assumptions rest on the anonymized design.
3. **Strict separation** from the anonymized Kaggle file — never joined or relabeled.

## Evaluation protocol

- **Split:** single fixed-seed (`RANDOM_SEED = 42`) **stratified 80/20** train/test
  split. Class counts/percentages reported for both partitions. Reported as a
  reproducible benchmark split — **not** out-of-time validation.
- **Model selection / threshold:** stratified **5-fold CV** confined to the
  **training** partition. The F1-optimal operating threshold is chosen from
  out-of-fold predictions on training only. The held-out test set is untouched
  until final evaluation.
- **Preprocessing:** fit **inside training folds only** (Logistic Regression uses
  a `StandardScaler` inside a `Pipeline`). Constant columns dropped. No imputation
  (the data has none). Any resampling would occur inside training folds only — none
  is used for the baseline.

## Models (shortlist, documented configs, fixed seed)

1. `DummyClassifier(stratified)` — no-skill reference.
2. `LogisticRegression` (max_iter 2000, class_weight balanced, standardized).
3. `RandomForestClassifier` (n_estimators 300, class_weight balanced).
4. `HistGradientBoostingClassifier` (scikit-learn; no XGBoost dependency added).

## Metrics

- **Primary:** Average Precision (PR-AUC) via scikit-learn `average_precision_score`,
  positive class = `Bankrupt?==1`. The **no-skill reference** for average precision
  equals the positive prevalence and is reported separately.
- Also: ROC-AUC, precision, recall, F1, balanced accuracy, confusion matrix at the
  CV-chosen threshold, and positive-class prevalence.
- **Uncertainty:** stratified 5-fold CV AP (mean/std) on training.

## Reproducibility

- Seed 42; deterministic split and estimators; identical partitions for all models.
- Command: `python -m backend.external_data.uci_benchmark`.
- Results persisted to `data/processed/uci-bankruptcy/benchmark_results.json`.

## Honesty constraints

No metric is reported that the data/design does not support. A single random-split
benchmark without a documented horizon **does not** establish out-of-time
performance or generalization to all companies.
