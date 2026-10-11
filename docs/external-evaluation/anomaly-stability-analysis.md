# Anomaly Detection Stability & Threshold Sensitivity Analysis

**Workstream C of the external-evaluation research program.**

This report assesses how **robust** the external-dataset anomaly-detection
findings are to (a) the choice of anomaly operating threshold and (b) the
Isolation Forest random seed. It is a **robustness / repeatability** study, not
an optimization and **not** a predictive-accuracy study.

**Core disclaimer (applies to every number below).** Neither external dataset
has ground-truth outcome labels. Therefore **no** precision, recall, F1,
ROC-AUC, PR-AUC, accuracy, or confusion matrix is reported or can be computed.
A **flag rate is an operating choice** produced by the frozen quantile
threshold policy — it is **not** a measured real-world anomaly prevalence, and
a higher flag rate never means "better detection."

**Frozen-core guarantee.** All models are the **unmodified frozen Phase 5**
Isolation Forest. The seed sweep calls the frozen public API
`fit_isolation_forest(complete, config=IsolationForestConfig(random_state=seed))`;
only the documented `random_state` is varied. The production default (seed 42)
and every hyperparameter (`n_estimators=200`, `max_samples='auto'`,
`max_features=1.0`, `bootstrap=False`), the robust median/IQR scaling, and the
train-quantile threshold policy are unchanged. No frozen file was modified.

**Reproduction.** `python -m backend.external_data.stability` regenerates the
JSON evidence (`data/processed/kaggle/stability/`) and both figures. The
reference flag set is validated against the committed artifacts: **Bankruptcy
834 == 834** and **Financial Statements 27 == 27** (`exact_match: true`,
0 mismatched rows), confirming this analysis reproduces the published results.

---

## 1. Configuration

| Item | Value |
|---|---|
| Frozen model | Isolation Forest (Phase 5), seed 42 (reference) |
| Hyperparameters | n_estimators=200, max_samples=auto, max_features=1.0, bootstrap=False |
| Scaling | robust median/IQR (inside frozen model) |
| Score direction | `-decision_function`; higher = more anomalous (matches frozen `anomaly_scores`) |
| Threshold policy | frozen `threshold_from_expected_rate(train_decision, r)` |
| Reference rate | `4/24 ≈ 0.16667` (frozen production default) |
| Threshold sweep (C1) | 0.02, 0.05, 0.10, 0.1667, 0.20, 0.25, 0.30 |
| Seeds (C2) | 42 (reference), 43, 44, 45, 46 |
| Top-k (C2) | Bankruptcy 834; Financial Statements 27 (= reference flag counts) |

**Why this threshold range.** The sweep brackets the frozen reference rate on
both sides. Rates below 0.16667 tighten the operating point (fewer, more
extreme flags); rates above loosen it (more flags). This exposes how
classifications move as the operator changes the alert budget. These are
sensitivity points, **not** tuned values and **not** an anomaly-rate estimate.

---

## 2. C1 — Threshold sensitivity

Because all thresholds derive from a **single frozen seed-42 ranking**, the
flag sets are perfectly **nested** (monotone): a tighter rate yields a subset
of a looser rate. The Jaccard overlap therefore reflects **set-size nesting on
a fixed ranking**, not ranking instability — an honest structural property of a
one-model, many-thresholds sweep, not threshold-induced rank churn.

### 2.1 Bankruptcy (cross-sectional, n = 5,000; reference 834 flagged)

| Expected rate | Threshold | Flagged | Flag rate | Jaccard vs ref |
|---:|---:|---:|---:|---:|
| 0.02 | 0.008333 | 100 | 0.0200 | 0.1199 |
| 0.05 | -0.040822 | 250 | 0.0500 | 0.2998 |
| 0.10 | -0.076077 | 500 | 0.1000 | 0.5995 |
| **0.1667 (ref)** | **-0.103541** | **834** | **0.1668** | **1.0000** |
| 0.20 | -0.112433 | 1,000 | 0.2000 | 0.8340 |
| 0.25 | -0.122893 | 1,250 | 0.2500 | 0.6672 |
| 0.30 | -0.130888 | 1,500 | 0.3000 | 0.5560 |

- **Core (flagged even at r=0.02):** 100 rows. **Boundary-sensitive (only above r=0.02):** 1,400 rows.

### 2.2 Financial Statements (annual panel, n = 160; reference 27 flagged)

| Expected rate | Threshold | Flagged | Flag rate | Jaccard vs ref |
|---:|---:|---:|---:|---:|
| 0.02 | 0.104052 | 4 | 0.0250 | 0.1481 |
| 0.05 | 0.054533 | 8 | 0.0500 | 0.2963 |
| 0.10 | -0.004552 | 16 | 0.1000 | 0.5926 |
| **0.1667 (ref)** | **-0.045133** | **27** | **0.16875** | **1.0000** |
| 0.20 | -0.060898 | 32 | 0.2000 | 0.8438 |
| 0.25 | -0.076509 | 40 | 0.2500 | 0.6750 |
| 0.30 | -0.089528 | 48 | 0.3000 | 0.5625 |

- **Core (flagged even at r=0.02):** 4 rows. **Boundary-sensitive (only above r=0.02):** 44 rows.

**Interpretation.** Moving the operating point from 0.02 to 0.30 changes the
flagged set by an order of magnitude (100→1,500 for Bankruptcy; 4→48 for FS).
The flagged count is a direct, mechanical consequence of the chosen expected
rate under the frozen quantile policy. There is **no** basis to call any rate
"correct" without ground truth.

---

## 3. C2 — Ranking stability across seeds

For each seed the frozen model is refit and the ranking of `-decision_function`
is compared to seed 42. `Spearman rho` measures **global order** agreement;
`top-k Jaccard` measures agreement on the **specific most-anomalous set**.

### 3.1 Bankruptcy (top-k = 834)

| Seed | Spearman rho vs 42 | Top-k Jaccard vs 42 | Flagged @ ref rate |
|---:|---:|---:|---:|
| 42 (ref) | 1.000000 | 1.000000 | 834 |
| 43 | 0.965077 | 0.841060 | 834 |
| 44 | 0.973089 | 0.816993 | 834 |
| 45 | 0.968704 | 0.880496 | 834 |
| 46 | 0.967440 | 0.849224 | 834 |

### 3.2 Financial Statements (top-k = 27)

| Seed | Spearman rho vs 42 | Top-k Jaccard vs 42 | Flagged @ ref rate |
|---:|---:|---:|---:|
| 42 (ref) | 1.000000 | 1.000000 | 27 |
| 43 | 0.987730 | 0.928571 | 27 |
| 44 | 0.980596 | 0.862069 | 27 |
| 45 | 0.986851 | 0.928571 | 27 |
| 46 | 0.986148 | 0.862069 | 27 |

**Interpretation.**

- **Global ranking is stable:** Spearman rho is 0.96–0.97 (Bankruptcy) and
  0.98–0.99 (FS) across seeds — the overall anomaly ordering barely moves.
- **Exact top-k membership is seed-sensitive:** top-k Jaccard drops to
  0.82–0.88 (Bankruptcy) and 0.86–0.93 (FS), i.e. roughly **10–18%** (BK) /
  **7–14%** (FS) of the most-anomalous set swaps under a different seed.
- **Flagged count is seed-invariant (834 / 27):** because the threshold is a
  *train quantile* (≈1/6 of rows), the count is stable by construction even as
  the specific members churn.

**These are repeatability findings, not predictive findings.** Stable ranking
does **not** imply the flagged rows are truly anomalous, and top-k churn does
**not** imply error — without labels there is no "correct" set to be stable
against.

---

## 4. C3 — Rule-baseline evidence (deterministic; no sweep)

The frozen rolling z-score/IQR rule baseline is **deterministic** given fixed
inputs and configuration (no random seed), so its per-company result has
**zero run-to-run variance**. It is reported as an output of the frozen method
— **not** as empirically validated or necessarily reliable.

### 4.1 Financial Statements — per company (frozen window=12, min_periods=8)

Windows are trailing-only **within each company**, ascending year order, so no
window crosses a company boundary and no future observation enters a window.

| Company | Rows | Scorable | Flagged |
|---|---:|---:|---:|
| AAPL | 14 | 6 | 6 |
| AIG | 14 | 6 | 4 |
| AMZN | 14 | 6 | 6 |
| BCS | 14 | 6 | 5 |
| GOOG | 14 | 6 | 6 |
| INTC | 14 | 6 | 5 |
| MCD | 14 | 6 | 6 |
| MSFT | 15 | 7 | 7 |
| NVDA | 15 | 7 | 7 |
| PCG | 14 | 6 | 6 |
| PYPL | 8 | 0 | 0 |
| SHLDQ | 10 | 2 | 2 |
| **Total** | **160** | **64** | **60** |

- **96 of 160 rows are unscorable** because each has fewer than the frozen
  `min_periods=8` prior observations **within its own company** (PYPL has only
  8 rows → 0 scorable). The flag rate is over **scorable rows only**
  (60/64 = 0.9375). This is a **baseline breach rate on short annual series**,
  **not** verified anomaly prevalence. The frozen `window=12/min_periods=8` are
  *period counts*: 12 **annual** periods here vs. 12 **monthly** periods in the
  synthetic environment (parameters unchanged, not retuned) — which is why most
  short company series are largely unscorable.

### 4.2 Bankruptcy — rule baseline unavailable

The frozen rolling baseline requires an ordered temporal series. The Bankruptcy
file is **cross-sectional** (no time column; row order is an identifier order),
so every trailing-window statistic would be meaningless. The baseline is
recorded as **unavailable**, not reported with an invalid flag rate.

---

## 5. Figures

- ![Threshold sensitivity](../../assets/external-evaluation/cross-dataset/threshold-sensitivity.png)
- ![Seed rank stability](../../assets/external-evaluation/cross-dataset/seed-rank-stability.png)

Machine-readable evidence: `data/processed/kaggle/stability/threshold_sensitivity.json`
and `data/processed/kaggle/stability/seed_rank_stability.json`.

---

## 6. Limitations

- No ground truth → no predictive metrics; flag rates are operating choices.
- C1 sets are nested on one frozen ranking; Jaccard reflects set-size nesting.
- C2 varies only the seed; `max_samples='auto'` is seed-driven but not
  separately swept. Hyperparameters were deliberately **not** tuned.
- FS rule baseline operates on ≤15 annual observations per company; the frozen
  12-period window leaves most rows unscorable — a property of the data, not a
  defect introduced here.
- Anonymized Bankruptcy features have unknown semantics, so stability is
  assessed on ranks only, never on feature meaning.
