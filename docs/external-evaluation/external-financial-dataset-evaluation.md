# External Financial Dataset Evaluation — Research Report

**Project:** AI Business Risk — Autonomous Multi-Agent Business Risk Intelligence & Stress Testing Platform
**Experiment:** External Kaggle dataset evaluation (master external-data task)
**External eval version:** 1.0.0 · **Random seed:** 42 · **HEAD at execution:** `046c35e` (Phase 8)

---

## 1. Executive summary

This experiment asked one question: **how well does AI Business Risk generalize from its
deterministic synthetic validation environment to independent real-world/public financial
datasets?**

The honest answer has two parts:

1. **Pipeline portability: verified.** The frozen Phase 5 Isolation Forest, the frozen rule
   baseline, the unmodified Phase 4 Risk Engine, and the Phase 5 explanation paths all execute
   deterministically on two independent Kaggle datasets with zero modifications to any frozen
   phase, golden fixture, or raw file. Both raw SHA-256 hashes are byte-identical before and
   after the run.
2. **Predictive generalization: NOT established.** Neither provided dataset carries genuine
   outcome labels. `Bankruptcy.csv` is the unlabeled competition *test* feature matrix; exact
   label recovery failed (no Kaggle credentials configured, anonymous download blocked), so the
   mandated automatic fallback to **unsupervised-only evaluation** applied.
   `Financial Statements.csv` has no target column of any kind. Consequently **no PR-AUC,
   ROC-AUC, F1, precision, recall, confusion matrix, or supervised-model result exists for
   either dataset — and none was fabricated.** Five label-gated figures are honest
   "unavailable" notices stating exactly why.

Risk Engine mapping on the Financial Statements panel is **partial by construction**:
15 of 38 registry metrics are computable from the provided columns; the remaining 23 report
`MISSING_INPUT` (score `None`). No liquidity score exists for any company because current
assets/current liabilities are absent from the source. Nothing was interpolated, imputed, or
fabricated to make scores appear.

## 2. Research objective

- Audit both external datasets (schema, missingness, duplicates, label availability).
- Map external columns to the frozen Risk Engine semantics without fabrication.
- Apply deterministic, leakage-audited preprocessing (seed 42).
- Run the **unmodified** frozen Phase 5 Isolation Forest and rule baseline externally.
- Run label-gated evaluation **only** if genuine labels exist.
- Produce explainability, cross-dataset comparison (without merging), publication-quality
  figures, a reproducible report, notebook, and tests.

## 3. Exact dataset provenance

### 3.1 Bankruptcy

| Field | Value |
|---|---|
| Local path | `data/raw/kaggle/bankruptcy/Bankruptcy.csv` |
| Bytes | 6,212,713 |
| SHA-256 | `4d3c07357112cd3839d3c813363743777be032f2899604ba01219a9936eeba64` |
| Source | Kaggle `lupitaastari/bankruptcy` — file `bankruptcy_Test_X.csv` |
| Verification | Row-content equality of all 5,000 data rows with the upstream test file; headers differ only by the ID alias |
| License | Competition/dataset terms — **unverified** |

### 3.2 Financial Statements

| Field | Value |
|---|---|
| Local path | `data/raw/kaggle/financial statements/Financial Statements.csv` |
| Bytes | 24,551 |
| SHA-256 | `32e38512643a626340b43a4255bf79d45a7afc66ffe9058326507cc2885cb1b5` |
| Source | Kaggle `rish59/financial-statements-of-major-companies2009-2023` (`data.csv`) |
| Verification | SHA-256 equality with the downloaded upstream `data.csv`; renamed locally |
| License | ODbL / Database Contents as declared on the Kaggle page — **unverified**, redistribution not recommended |

Both raw files were opened **read-only**; hashes were re-verified after the full run and are
identical (see §4). The runner additionally re-hashes each raw file inside the same process
and raises `RuntimeError` if either changed mid-run; no such error occurred.

## 4. Raw file SHA-256 hashes (before → after)

| File | Before run | After run | Result |
|---|---|---|---|
| `Bankruptcy.csv` | `4d3c0735…6eeba64` | `4d3c0735…6eeba64` | **UNCHANGED** |
| `Financial Statements.csv` | `32e38512…85cb1b5` | `32e38512…85cb1b5` | **UNCHANGED** |

## 5. Dataset descriptions

### 5.1 Bankruptcy (5,000 × 65)

- Columns: `ID`, `Attr1` … `Attr64` — anonymized financial ratios (Taiwanese bankruptcy
  prediction competition lineage). No column names carry economic semantics.
- 5,000 rows, 0 duplicate rows, unique integral `ID`, no constant columns.
- No missing values; all 64 Attr columns numeric.
- **No target column** (`target_present = false`, `target_candidates = []`).

### 5.2 Financial Statements (161 × 23)

- 161 rows, 12 companies (AAPL, AIG, AMZN, BCS, GOOG, INTC, MCD, MSFT, NVDA, PCG, PYPL, SHLDQ),
  calendar years **2009–2023**, **annual frequency**, all company histories consecutive
  (min 9, max 15 obs/company; 10 of 12 companies have ≥ 12 periods).
- Columns: Year, Company, Category + 20 numeric fields (market cap, Revenue, Gross Profit,
  Net Income, EPS, EBITDA, Share Holder Equity, three cash-flow lines, Current Ratio,
  Debt/Equity, ROE, ROA, ROI, Net Profit Margin, FCF/share, Return on Tangible Equity,
  Number of Employees, Inflation Rate).
- Raw header contains `'Company '` (trailing space); the loader strips whitespace — recorded
  and unit-tested.
- 0 duplicate rows, 0 duplicate company-period combinations, no constant columns.
- Missingness: **1 missing value** in `Market Cap(in B USD)` → that row is dropped by the
  frozen complete-case contract (161 → 160 modeling rows). **No imputation.**
- Category labels are inconsistent in the source (`BANK`/`Bank`, `FinTech`/`Finance`, …);
  recorded as-is, used only as metadata.
- **Unit limitation:** the source does not state currency units per column; values are used in
  "source units" everywhere. No cross-company monetary aggregation is performed.
- No target column of any kind.

## 6. Bankruptcy label verification result — **UNAVAILABLE (recovery failed)**

Policy (approved): attempt exact label recovery only from an authoritative source matching on
`ID` + all 64 attributes + row content; otherwise fall back automatically to unsupervised-only.

What happened:

1. The provided file was verified to be the **unlabeled competition test matrix**
   (`bankruptcy_Test_X.csv` of `lupitaastari/bankruptcy`).
2. The companion labeled `bankruptcy_Train.csv` covers a **different row set** — only
   55/5,000 rows are content-identical — so it cannot label this file even in principle.
3. Download of the upstream 66-column source for exact recovery was attempted:
   `kaggle datasets download` failed with `KeyError: 'username'` (**no Kaggle credentials
   configured**), and the anonymous HTTPS endpoint was blocked (HTTP error). No approximate,
   partial, inferred, or cross-dataset labels were used as a substitute.

**Result: exact authoritative label recovery FAILED → automatic fallback to
UNSUPERVISED-ONLY evaluation.** Supervised classification performance **cannot be
established** from the downloaded file. `evaluation.json` records `available: false` with the
full reason string; `dataset-class-distribution.png`, `pr-curve.png`, `roc-curve.png`,
`confusion-matrix.png`, and `model-comparison.png` are honest "unavailable" notices, not plots.

## 7. Financial Statements compatibility analysis

- **Panel structure fits** the per-company evaluation model: `company_datasets()` builds one
  `{profile, periods}` record per company with chronologically sorted annual periods.
- **Canonical mapping (exact semantics only):** Revenue→`revenue`, Gross Profit→`gross_profit`,
  Net Income→`net_income`, EBITDA→`ebitda`, Share Holder Equity→`equity`,
  Cash Flow from Operating→`ocf`.
- **Single-unknown derivation (recorded as derived):** `total_debt = (Debt/Equity) × equity`.
- **Provided but not canonical (14 columns):** Market Cap, EPS, investing/financing cash flows,
  Current Ratio, Debt/Equity, ROE/ROA/ROI, margins, FCF/share, Return on Tangible Equity,
  employees, inflation — used as anomaly features and reported, never injected as canonical
  Risk Engine fields.
- **Unavailable canonical inputs (19):** cogs, opex, ebit, cash, receivables, inventory,
  current assets/liabilities, total assets/liabilities, short/long-term debt split, capex, fcf, …
  → these metrics stay `MISSING_INPUT`.
- **Frequency mismatch:** data are annual; the Digital Twin requires monthly observations.
  **No monthly data were invented, interpolated, or forward-filled.** The Twin was not run.

## 8. Preprocessing methodology (deterministic, seed 42)

Documented per dataset in `data/processed/kaggle/*/preprocessing.json`:

| Aspect | Bankruptcy | Financial Statements |
|---|---|---|
| Features | 64 (`Attr1..Attr64`) | 20 numeric columns |
| Excluded | `ID` (identifier) | `Company`, `Year`, `Category` (metadata/time) |
| Schema | strict `ID + Attr1..Attr64` validation | strict 23-column validation, whitespace-normalized |
| Encoding | none (all numeric) | none (all numeric) |
| Scaling | none stored; robust median/IQR inside frozen model | same |
| Missing values | none present | 1 incomplete row dropped (frozen `dropna()` contract) |
| Imputation | **none** | **none** |
| Seed | 42 (model + attribution) | 42 |

Forbidden-feature enforcement is programmatic: `build_feature_matrix` raises `ValueError` if
any of `ID/Company/Category/Year/class` is requested as a feature.

## 9. Leakage audit

`leakage.json` for both datasets: **`clean: true`**, 5/5 checks passed:

1. `target_not_in_features` — passed (no target present in either feature matrix).
2. `identifiers_and_metadata_not_in_features` — passed.
3. `preprocessing_independent_of_target` — passed (parameters computed from feature data only).
4. `no_duplicate_entities_across_splits` — n/a (no supervised split exists).
5. `no_future_information_in_historical_features` — n/a (no temporal supervised features).

The runner **hard-stops** (`RuntimeError`) if any audit is not clean; no stop occurred.

**Documented heuristic false positive:** the target-name pattern flagged
`Share Holder Equity` and `Return on Tangible Equity` as target *candidates* in the FS audit
(substring match on "…equit**y**"). They are ordinary financial ratio columns in an unlabeled
dataset, not outcomes; they are retained as documented features. No label was used anywhere
in preprocessing, training, or evaluation.

## 10. Isolation Forest methodology (frozen Phase 5, unmodified)

Identical configuration on both datasets — `backend/ml_engine/models.fit_isolation_forest`
called unchanged:

- `n_estimators=200`, `max_samples='auto'`, `max_features=1.0`, `bootstrap=False`,
  `random_state=42`, robust median/IQR scaling inside the frozen fit path.
- Threshold: train quantile at expected rate **4/24 ≈ 0.1667** — the same policy form as the
  frozen Phase 5 golden (no contamination retuning).

| Dataset | Rows modeled | Features | Threshold | Flagged | Flag rate |
|---|---|---|---|---|---|
| Bankruptcy | 5,000 | 64 | −0.1035405794730479 | 834 | 16.68 % |
| Financial Statements | 160 | 20 | −0.0451328817060862 | 27 | 16.875 % |

Score summaries (bankruptcy): min 0.0002, median 0.5001, mean 0.500101, p90 0.90002, max 1.0.
Dataset fingerprints recorded in `anomaly_run.json` (bankruptcy `530755c7…0f832`,
FS `31f94d77…fed8e`).

**Interpretation guardrail:** because the threshold policy *targets* the frozen expected rate,
the resulting flag rates are near 1/6 **by construction**. They demonstrate that the frozen
mechanism runs unchanged — they are *not* evidence of detected anomaly prevalence.

## 11. Rule baseline methodology (frozen Phase 5, applicability-gated)

`rolling_rule_baseline` (frozen parameters: window 12, min_periods 8, z-threshold 3.0,
IQR multiplier 1.5) is called **unchanged** through the applicability gate
`external_rule_baseline` (`backend/external_data/evaluation.py`), which decides whether a
valid application exists. The frozen function itself is never modified.

| Dataset | Application | Result | Honest reading |
|---|---|---|---|
| Bankruptcy | **Unavailable** — cross-sectional matrix (no time column; ID order is not temporal). The frozen function is **not called** (`"frozen_function_called": false`). | `available: false` in `rule_baseline.json` | Trailing-row windows over an ID-ordered test matrix would be meaningless; the baseline is recorded as unavailable rather than reported with an invalid flag rate. |
| Financial Statements | **Per-company, ascending-year, past-only** — the frozen function is called **once per company** on (Company, Year)-sorted complete rows, so windows never cross company boundaries and only past observations enter every window. | **60 flagged of 64 scorable rows** (flag rate 0.9375 of scorable rows); **96 of 160 complete rows are unscorable** because their within-company history has fewer than the frozen `min_periods = 8` prior observations (PYPL contributes 0 scorable rows; every other company 6–7). | A valid temporal application: each company's annual series is short (≤15 rows), so the rolling baseline is weak but honest. Previously reported pooled numbers (104/161 = 64.6 %) crossed company boundaries and are superseded. |

The **60/64 result is an output of the frozen rule method on a short annual series, not verified
anomaly prevalence.** It is the fraction of scorable company-years whose trailing within-company
window breaches the frozen z-score/IQR thresholds; there are no labels to score it against, and the
short annual windows (window=12 / min_periods=8 count annual periods here versus monthly in the
synthetic environment — parameters unchanged, not retuned) mean only 64 of 160 rows are scorable at
all. The 96 unscorable rows are excluded from the flag statistics for the documented reason above,
not discarded silently.

Neither output is a performance metric — no labels exist to score them against. The rule
baseline's historical pooled FS run and the bankruptcy run are retained only as a cautionary
note: rolling windows are the wrong shape for cross-sectional or pooled-panel row orders.

## 12. Supervised evaluation — NOT PERFORMED (no legitimate labels exist)

- **Bankruptcy:** exact label recovery failed (§6). No Class column, no matching label source
  reachable. Supervised metrics: **none computed**. A supervised reference model was **not
  trained** because a legitimate target does not exist for these rows — training on any other
  label set would be scientific fraud.
- **Financial Statements:** no target column exists. Supervised metrics: **none computed**.
- Both `evaluation.json` files: `{"available": false, "metrics": {}, "reason": "…"}` — explicit
  machine-readable unavailability records, not empty results.

## 13. Attributions / explainability results

Method: the project's Phase 5 explanation path (`backend.ml_engine.explain`). The frozen
internal label `"shap_exact"` is a **known misnomer** (deferred item D-1,
`docs/development-log.md` and `docs/05_ml_engine/phase-report.md` §11.5) and is preserved
only because the golden fixture depends on it — it must not be read as a TreeSHAP claim.
The authoritative record is `explainer_metadata` in each `explanations.json` and the runtime
class reported by `runtime_explainer_class`: `shap.Explainer(decision_function, Independent
masker, seed=42)` — a seeded Monte-Carlo permutation-family Shapley estimator — with a
deterministic permutation-importance fallback (`_permutation_row`) when SHAP fails or the
per-row additivity check (tolerance 1e-6) does not hold. Efficiency
(base_value + sum(values) == decision_function(x)) is verified per row, but exact additivity
does not imply exact attribution (documented seed-to-seed drift ~2.2e-4). No
TreeExplainer/TreeSHAP is used anywhere.

- **Sample:** 100 evenly spaced rows per dataset (deterministic, `ATTRIBUTION_SAMPLE = 100`),
  documented as a sample — not a full-dataset SHAP run.
- **Bankruptcy global ranking (top features):** Attr50, Attr1, Attr8, Attr18, Attr11, Attr48,
  Attr22, Attr34 — anonymized, so no economic interpretation is possible beyond "these ratios
  dominate the isolation score".
- **Financial Statements global ranking (top features):** Market Cap (in B USD), Net Income,
  EBITDA, Cash Flow from Financial Activities, Revenue, Gross Profit, Current Ratio,
  Inflation Rate (in US).
- **Representative flagged examples:** 5 per dataset with per-feature attributions, feature
  values, and direction (`pushes_anomalous`), e.g. FS/AAPL-2022 drivers: Net Income,
  Cash Flow from Financial Activities, Revenue, EBITDA, Market Cap.
- **Limitations:** attributions explain the *model*, not reality; they are not causal; values
  for unsupervised isolation scores indicate contribution to the anomaly score, not to
  any outcome; sampling means global rankings are estimates over 100 rows. Earlier drafts
  of this report called the method "exact TreeSHAP" — that claim is withdrawn; see the
  method note above.

## 14. Quantitative Risk Engine mapping (unmodified Phase 4)

`QuantitativeRiskEngine.evaluate_company(...)` was called per company through
`backend.external_data.risk_mapping` with **zero changes** to formulas, weights, registry, or
scoring. Evidence in `data/processed/kaggle/financial-statements/risk_mapping.json` and
`risk_reports.json` (full per-company reports, 12 companies).

**Coverage: 15 of 38 registry metrics computable (39.5 %).**

| Dimension | Score availability (12 companies) | Notes |
|---|---|---|
| financial_strength | **12/12 computable** (15.8 – 76.9) | varies by company; driven by profitability/equity inputs |
| market | **12/12 computable** (25.2 – 51.5) | market-cap-based inputs present |
| macro | **12/12** (35.0; PCG 55.0) | profile-driven; limited variation |
| credit | 12/12 but **constant 15.0** | only derived `total_debt` available → identical partial-input score everywhere |
| operational | 12/12 but **constant 12.5** | headcount-based input identical in form |
| concentration | 12/12 but **constant 18.33** | single-category source → no real dispersion |
| **liquidity** | **0/12 → `None`** | current assets/liabilities absent; **no score fabricated** |

Composite risk scores (aggregate of *available* dimensions only, frozen semantics):
MSFT 20.8 … SHLDQ 34.9 (full map in `risk_mapping.json`). The low absolute composites are an
artifact of partial coverage — **they are not comparable to full-input synthetic-environment
scores** and must not be read as "these companies are low risk".

Bankruptcy: **0 Risk Engine metrics computable** — the Attr columns are anonymized ratios with
no balance-sheet semantics; mapping any of them would require inventing field meanings.

## 15. Missing-input limitations

- 23/38 Risk Engine metrics report `MISSING_INPUT` on FS (all balance-sheet stock variables,
  cogs/opex/ebit, cash/receivables/inventory, capex/fcf, debt split).
- Liquidity dimension: no score for any company.
- Constant dimension scores (credit/operational/concentration) reflect identical available
  inputs across companies — partial-input behavior, not homogeneity of risk.
- No market price series → no time-series market metrics; no macro API → macro limited to
  dataset profile; no monthly data → Digital Twin not executed.
- Everything missing stayed missing. Nothing was forward-filled, zero-filled, interpolated,
  or imputed.

## 16. Cross-dataset comparison (no merging)

`docs/assets/external-evaluation/cross-dataset/comparison-summary.json` + CSV/PNG:

| Dimension | Bankruptcy | Financial Statements |
|---|---|---|
| Type | bankruptcy **anomaly** dataset (cross-sectional test matrix) | financial-**statement** company panel |
| Size | 5,000 × 65 | 161 × 23 (12 companies, 2009–2023, annual) |
| Structure | ID + 64 anonymized ratios | 3 metadata + 20 numeric fields, real semantics |
| Time coverage | none (no time column) | 15 calendar years, annual |
| Targets | none (recovery failed) | none |
| Preprocessing | 64 numeric features, complete rows | 20 numeric features, 1 row dropped |
| Anomaly evaluation | scores/flags only — no outcome evaluation possible | same |
| Risk Engine | 0/38 metrics | 15/38 metrics |
| Explainability | permutation-family Shapley attributions, 100-row sample | permutation-family Shapley attributions, 100-row sample |

**Datasets were never merged, joined, or averaged.** Flag rates are not performance; performance
on one dataset cannot be inferred from the other; the only defensible consistency claim is
*pipeline portability* (both run the identical frozen configuration deterministically).

## 17. Figures (real PNGs, deterministic, DPI 200)

All under `docs/assets/external-evaluation/` (relative paths from this report:
`../assets/external-evaluation/…`):

- **bankruptcy/** (8): `feature-distributions.png`, `anomaly-score-distribution.png`,
  `shap-summary.png`, plus honest unavailability notices `dataset-class-distribution.png`,
  `pr-curve.png`, `roc-curve.png`, `confusion-matrix.png`, `model-comparison.png`.
- **financial-statements/** (6): `dataset-overview.png`, `company-coverage.png`,
  `financial-trends.png`, `risk-dimension-distribution.png`, `anomaly-results.png`
  (score-vs-year scatter with flagged rows highlighted), `shap-summary.png`.
- **cross-dataset/** (3 PNG): `risk-dimension-comparison.png`,
  `feature-importance-comparison.png`, `model-performance-comparison.png` (unavailability
  notice) — plus `comparison-summary.json` and `model-performance-comparison.csv`.

**Total: 17 PNG files.** Every PNG was verified to exist with PNG magic bytes; none is empty
or fabricated. Label-gated plot slots contain explicit unavailability notices, not fake curves.

## 18. Scientific interpretation

1. **The frozen pipeline is portable.** The identical Phase 5 configuration (model, scaling,
   threshold policy, seed 42) executed deterministically on a 5,000×64 anonymized matrix and a
   160×20 real-semantics panel, producing recorded fingerprints, thresholds, scores, and flags
   with no code changes anywhere in Phases 4–8.
2. **Determinism held end-to-end.** Same seed → identical scores/flags across runs (unit-tested);
   raw file hashes unchanged before/after; all artifacts JSON-deterministic (sorted keys).
3. **Honest unavailability is itself a result.** The system correctly refused to produce
   label-gated metrics instead of laundering unsupervised scores into "accuracy" claims.
4. **Risk Engine external compatibility is real but partial.** 15/38 metrics compute from real
   external data with unchanged formulas; 23 stay `MISSING_INPUT`; liquidity refuses to score.
   This validates the no-fabrication contract under distribution shift.
5. **The rule baseline's poor external behavior is diagnostic, not a defect.** A pooled
   rolling window is the wrong shape for cross-sectional/pooled-panel data — the old pooled
   runs reported 92.3 %/64.6 % flag rates precisely because they were not gated to a valid
   temporal application. The corrected application (§11): bankruptcy **unavailable**
   (frozen function not called), FS per-company past-only on short annual series.

## 19. Limitations

- **No labels → no supervised conclusions anywhere.** This is the dominant limitation.
- Single test matrix (Taiwanese lineage, anonymized) and one small 12-company panel — not a
  representative sample of "real-world finance".
- SHAP over 100 sampled rows per dataset; rankings are sample estimates.
- FS currency units unstated; cross-company magnitude comparisons in "source units" only.
- 15/38 metric coverage makes composite scores partial-input artifacts, not full risk grades.
- Constant dimension scores (credit/operational/concentration) carry little discriminative
  information on this source.
- Rule baseline: pooled windows assume temporal ordering the data do not have (§11) — now
  applicability-gated (bankruptcy unavailable; FS per-company past-only).
- Kaggle licenses unverified; ODbL provenance obligations apply to the FS file.
- Attribution sample and flag thresholds are policy choices documented in `run_config`, not
  tuned — but they still shape what the outputs look like.

## 20. What this experiment does NOT prove

- It does **not** prove the platform detects real bankruptcies (no bankruptcy labels were available).
- It does **not** prove predictive accuracy, PR-AUC, ROC-AUC, F1, or calibration — none were computed.
- It does **not** prove anomaly flags correspond to real distressed firms.
- It does **not** prove composite risk scores equal full-input synthetic-environment scores.
- It does **not** establish superiority over any baseline — no outcome exists to compare against.
- It does **not** validate the Digital Twin, scenario engine, or stress-testing phases externally
  (annual data cannot exercise monthly contracts; those phases were untouched).

## 21. Reproducibility instructions

```bash
# from repository root, Python 3.12 venv
python -m backend.external_data.run_experiment   # regenerates all JSON/CSV/PNG outputs
python -m pytest -q                              # full suite incl. 15 external-data tests
python -m ruff check . && python -m mypy .       # static checks
jupyter nbconvert --to notebook --execute \
  notebooks/external_evaluation/01_kaggle_financial_risk_evaluation.ipynb
```

- Seed 42 everywhere (`RANDOM_SEED` in `backend/external_data/contracts.py`).
- Raw files are read-only inputs; the runner asserts their SHA-256 before/after.
- Environment at execution: Python 3.12.10, pandas 3.0.6, numpy 2.5.3,
  scikit-learn 1.9.1, matplotlib 3.11.2 (recorded in `run_summary.json`).
- Artifacts: `data/processed/kaggle/` (21 JSON incl. `run_summary.json` + 4 CSV),
  figures: `docs/assets/external-evaluation/` (17 PNG + 1 JSON + 1 CSV),
  tests: `backend/tests/unit/test_external_kaggle_eval.py`.

## 22. Final conclusion

**The experiment is a clean, honest PARTIAL success.**

- **PASS:** provenance verified, raw integrity preserved, deterministic preprocessing,
  leakage audits clean, frozen Phase 5 model run unchanged on both datasets with the rule
  baseline applicability-gated (bankruptcy unavailable; FS per-company past-only),
  unmodified Risk Engine returns real partial coverage with explicit missing inputs,
  attributions produced via the Phase 5 explanation path (see section 13), cross-dataset comparison without merging,
  17 real figures, full artifact trail, 15 new passing tests, frozen phases untouched.
- **NOT ESTABLISHED:** any supervised or outcome-based performance claim. Neither dataset
  carries genuine labels; exact label recovery for the bankruptcy test matrix failed at the
  download step (no Kaggle credentials), and the mandated fallback — unsupervised-only
  evaluation with explicit unavailability records — was executed exactly as specified.

The core research question is answered as: **AI Business Risk's frozen methodology is
*operationally* generalizable — it runs unchanged and honestly on independent public data —
but its *predictive* generalization remains untested, because the provided external data
contains no ground truth to test it against.** Closing that gap requires an external dataset
with verified labels; no amount of processing the current files can substitute for it.
