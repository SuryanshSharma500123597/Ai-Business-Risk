# UCI Taiwanese Bankruptcy Prediction — Benchmark Report

## Dataset audit and source attribution

**Source:** UCI Machine Learning Repository, *Taiwanese Bankruptcy Prediction*
(dataset id **572**, DOI **10.24432/C5004D**), license **CC BY 4.0** (verified on
the official page). Collected from the Taiwan Economic Journal, 1999–2009.

**Attribution:** Taiwanese Bankruptcy Prediction, UCI ML Repository (id 572,
DOI 10.24432/C5004D), CC BY 4.0.

**Immutable raw bytes** (`data/raw/uci/`):

| File | SHA-256 | Bytes |
|---|---|---|
| `taiwanese-bankruptcy-prediction.zip` | `C346F5AD2618CB198E7ED8306CF2F31FE3BB2EC60ACDBBE1736788D50F269AAC` | 4,808,883 |
| `data.csv` | `67BF2E7C75490F7AD3F76BBCE57D49CDC25967CDAB607527B94F944863FA14D8` | 11,456,101 |

**Measured schema:** 6,819 rows × 96 columns (target `Bankrupt?` + 95 features).
0 duplicate rows, 0 missing cells, 0 non-finite values, 1 constant column
(` Net Income Flag`). **Positive class `Bankrupt?==1`: 220 / 6,819 = 3.2263%.**

## Split sizes and class distribution

Fixed-seed (42) stratified 80/20 split. Prevalence is preserved across partitions:

| Partition | Rows | Class 0 | Class 1 | Prevalence |
|---|---:|---:|---:|---:|
| Train | 5,455 | 5,279 | 176 | 0.0323 |
| Test | 1,364 | 1,320 | 44 | 0.0323 |

The test set is untouched until final evaluation. The F1-optimal threshold is
chosen by 5-fold CV **inside the training partition only**.

## Model configurations and measured metrics

Threshold-selection: maximize F1 on out-of-fold training predictions. Positive
class = `Bankrupt?==1`. **No-skill average-precision reference = prevalence =
0.03226.**

| Model | AP (PR-AUC) | ROC-AUC | Precision | Recall | F1 | Bal. Acc | Threshold | CV AP mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DummyClassifier (stratified) | 0.0320 | 0.4939 | 0.032 | 1.000 | 0.062 | 0.500 | 0.000 | 0.0325 |
| LogisticRegression | 0.3190 | 0.9171 | 0.356 | 0.591 | 0.444 | 0.778 | 0.8703 | 0.3267 |
| RandomForest | 0.4955 | 0.9528 | 0.433 | 0.591 | 0.500 | 0.783 | 0.3867 | 0.4026 |
| HistGradientBoosting | 0.5238 | 0.9540 | 0.451 | 0.523 | 0.484 | 0.751 | 0.0415 | 0.4491 |

Confusion matrices (rows = actual [0,1], cols = predicted [0,1]):

- **DummyClassifier:** `[[0, 1320], [0, 44]]` — predicts every observation as positive.
- **LogisticRegression:** `[[1273, 47], [18, 26]]`.
- **RandomForest:** `[[1286, 34], [18, 26]]`.
- **HistGradientBoosting:** `[[1292, 28], [21, 23]]`.

## Interpretation (honest)

- **Every supervised model beats the no-skill reference** (AP 0.0320). The dummy
  classifier sits exactly at no-skill, confirming the reference.
- **HistGradientBoosting** is strongest (AP 0.5238, ROC-AUC 0.9540); the tree
  ensembles clearly outperform logistic regression on this feature space.
- **These are single-split benchmark numbers**, not out-of-time performance.
  CV AP means on training (0.33–0.45) are in the same range as the test APs, which
  is reassuring about split stability but does not validate temporal
  generalization.

## Leakage checks and reproducibility

- Target `Bankrupt?` is never used as a feature; it is separated before any model.
- StandardScaler (LogisticRegression) is fit inside each training fold via a Pipeline.
- Threshold chosen from out-of-fold training predictions only; test set touched once.
- Determinism: seed 42 for split and every stochastic estimator; identical
  partitions for all models. Re-running produces identical metrics.
- The anonymized Kaggle `Bankruptcy.csv` is never joined, relabeled, or inferred.

**Reproduce:** `python -m backend.external_data.uci_benchmark` →
`data/processed/uci-bankruptcy/benchmark_results.json`.

## Limitations and what this does NOT establish

1. **No documented prediction horizon** — this is not years-in-advance forecasting.
2. **No company IDs / dates** — entity and temporal leakage cannot be excluded.
3. **A single random split** does not establish out-of-time performance or
   generalization to all companies.
4. Imbalanced (3.23% positive) — AP is the primary metric; precision/recall/F1
   depend on the operating threshold and should be read with the prevalence.
5. This benchmark is **independent** of the anonymized Kaggle dataset; success
   here does not validate that dataset or the frozen platform.

## Verification

- `pytest` — 11 dedicated tests (schema rejection, target separation, class-balance
  audit, leakage/threshold-on-training-only, stratified determinism, reproducibility,
  real-data schema, beats-no-skill, split balance). Full suite: **544 passed**.
- `ruff check backend` — clean. `mypy` (configured) — clean.
- Raw UCI SHA-256 verified; frozen Phases 4–8 and goldens unchanged.
