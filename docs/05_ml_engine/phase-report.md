# Phase 5 — ML Engine Completion Report

**Status:** Engineering complete — documentation closed at the Phase 5 closure audit; awaiting approval for Phase 6.
**Scope:** `backend/ml_engine/` — a deterministic, LLM-independent anomaly-detection subsystem
(Isolation Forest + rolling rule baseline + SHAP driver attribution).
**Upstream dependencies:** Phase 3 data contracts and the Phase 4 metric calculators (consumed read-only).
**Phase 4 impact:** none. No Phase 4 formula, anchor, scoring, aggregation, sensitivity rule or golden file
was modified by this phase.

---

## 1. Phase Objective

Deliver an auditable, reproducible, LLM-independent **ML anomaly engine** that sits alongside — and
never inside — the deterministic risk engine:

```text
Phase 3 canonical periods
    -> ML feature construction (scale-free ratio matrix)
    -> rule baseline (rolling z-score / IQR, trailing only)
    -> Isolation Forest (deterministic)
    -> anomaly score in [0, 1] + anomaly flag
    -> evaluation vs synthetic injected anomalies
    -> SHAP driver attribution
    -> structured ML finding contract
```

The engine exists to answer **"is this period unusual for this company?"** — a question the Phase 4
risk engine deliberately does not answer.

### Core semantic boundary

**ANOMALY ≠ FINANCIAL RISK.** An ML anomaly marks unusual multi-ratio behaviour. It is:

- **not** a Phase 4 risk score, and is never mapped onto the Phase 4 0–100 scale;
- **not** a causal claim, a distress prediction, an investment prediction, or a substitute for a
  professional risk team.

These boundaries are enforced in code (`ANOMALY_RISK_DISCLAIMER`, `CAUSALITY_DISCLAIMER`,
`SYNTHETIC_EVAL_DISCLAIMER` in `backend/ml_engine/contracts.py`) and are stamped onto every
explanation and evaluation output, not merely documented.

---

## 2. Scope Completed

| Module | Responsibility |
|---|---|
| `contracts.py` | Pydantic contracts (`Provenance`, `AnomalyResult`, `DriverContribution`, `AnomalyExplanation`, `ModelMetadata`, `MLFinding`), frozen disclaimers, `FEATURE_SCHEMA_VERSION = "1.0.0"`, `MODEL_VERSION = "1.0.0"` |
| `features.py` | 27-column scale-free feature matrix, leakage guard, SHA-256 frame fingerprint |
| `models.py` | Isolation Forest wrapper, median/IQR scaling, rank-CDF scores, quantile thresholding |
| `baseline.py` | Rolling z-score / Tukey-IQR rule baseline, trailing window only |
| `explain.py` | SHAP attribution with additivity verification + deterministic permutation fallback |
| `evaluate.py` | ROC-AUC, PR-AUC, precision/recall/F1/FPR/FNR, precision@k, recall@k, verdict |
| `train.py` | Versioned artifact persistence (`model.joblib` + `metadata.json`), checksum, schema validation |

**Explicitly out of scope for Phase 5** (deferred, see §23): persistence wiring into the API, an
`ml_anomaly` agent, the LLM-facing `MLFindings` graph node, model registry/service integration, and
any external benchmark.

---

## 3. Architecture Boundary

- `backend/ml_engine/` imports **only** `backend.ml_engine`, `backend.risk_engine` (metric
  calculators and `MetricStatus` only), `pandas`, `numpy`, `scikit-learn`, `shap`, `joblib`.
- It imports **no** `app`, `agents`, `llm` or `services` module. This is enforced mechanically by
  `backend/tests/unit/test_architecture_imports.py` (architecture rule **R3**), which already listed
  `ml_engine` in `DETERMINISTIC_PACKAGES` before the package existed and now actively scans it.
- The dependency direction is strictly **Phase 5 → Phase 3/4**. Phase 4 does not import Phase 5.
- The engine reuses the **frozen Phase 4 metric calculators** rather than reimplementing financial
  mathematics, so a change to a Phase 4 formula cannot silently diverge from the ML feature matrix.

---

## 4. Feature Contract

`build_feature_frame()` returns a deterministic **24 × 27** matrix (24 periods × 27 features) for a
24-period company.

| Group | Count | Contents |
|---|---|---|
| Base ratios | 14 | gross/operating/net margin, ROA, ROE, debt-to-equity, debt-to-EBITDA, current/quick/cash ratio, short-term obligation coverage, DSO, DIO, DPO |
| Cash cycle | 1 | `ccc` (from `calc_ccc`) |
| Period deltas | 6 | `_delta` for gross margin, operating margin, net margin, ROA, current ratio, DSO |
| Rolling volatility | 6 | `_rollvol` over the same six ratios (window 12, minimum 8 observations, sample std) |

**Design rules:**
- Every feature is **scale-free**. Absolute currency-unit levels never enter the matrix; size and
  scale enter only through ratios, growth deltas and bounded volatilities.
- Deltas and rolling statistics use **trailing history only** (`history[-ROLLING_WINDOW:]`), so no
  feature can see a future period.
- Deliberate **exclusions** (`features.py`): history-dependent metrics
  (`receivable_trend`, `revenue_volatility`, `cash_runway_months`), listed-only metrics
  (`equity_volatility`, `beta`, `var_95`, `es_95`, `merton_dd`, `altman_z_distance`), exposure-share
  inputs, concentration buckets, and the constant `opex_rigidity`. These are not per-period
  scale-free ratios.
- Phase 4 `score` / `severity` outputs are excluded — only measured ratio `value` fields are used.

**Leakage guard:** `FORBIDDEN_COLUMNS` (16 entries: `company_id`, `company_name`, `period_start`,
`period_end`, `fiscal_year`, `quarter`, `frequency`, `source`, `currency`, `sector`, `size`,
`health`, `seed`, `label`, `injected_label`, `anomaly`) is intersected with the built frame and
raises `ValueError` on any intersection. The `company_id` parameter is accepted and immediately
discarded. Verified in the unit tests and demonstrated in the notebook.

---

## 5. Anomaly Semantics

Five distinct concepts are kept separate and are never used interchangeably:

| Concept | Where it lives | Meaning |
|---|---|---|
| `injected_anomaly` | `AnomalyResult.injected_label`, evaluation only | Ground-truth label from the synthetic generator. **Never a feature.** |
| `rule_anomaly` | `RuleBaselineResult.flags`, `AnomalyResult.rule_flag` | Trailing z-score / IQR breach |
| `model_anomaly` | `AnomalyResult.is_anomaly`, `anomaly_score` | Isolation Forest flag / rank-CDF score |
| `risk_metric` / risk score | `backend/risk_engine/` | Phase 4 metric value and the 0–100 composite |
| `anomaly_severity` | **not implemented** | No mapping from anomaly score to a severity band exists |

The ML engine never writes to the Phase 4 risk pipeline, never consumes a Phase 4 composite score as
input, and never converts an anomaly score into a risk severity.

**Injected labels are evaluation-only.** They are passed to `evaluate_methods()` as a separate
argument and are read by nothing in `features.py` or `models.py`. EDGAR real-statement data is
never treated as ground-truth anomaly labels anywhere in the codebase.

---

## 6. Rule Baseline

`rolling_rule_baseline()` scores the **same** feature matrix with a deterministic statistical rule:

- Trailing window only: `frame.iloc[max(0, i - window) : i]` — **no look-ahead**.
- Window 12, minimum 8 trailing observations; periods with insufficient history cannot be flagged.
- Flags when `|z| >= 3.0` **or** the value falls outside `Q1 - 1.5·IQR .. Q3 + 1.5·IQR` (Tukey).
- Non-numeric, `NaN` or infinite cells are **skipped**, never imputed.
- Per-period score = maximum absolute z across features; `breached_features` records which features
  triggered the flag.

The baseline is the falsifiability control required by decision **D4**. It is not a fallback for the
model — it is the comparator the model must beat.

---

## 7. Isolation Forest Implementation

- `IsolationForest(n_estimators=200, max_samples="auto", max_features=1.0, bootstrap=False, random_state=42, n_jobs=1)`.
- Fitted on **complete rows only** (`frame.dropna()`); an empty complete set raises
  `ValueError("no complete feature rows available for training")`.
- Preprocessing: **median / IQR robust scaling** persisted with the model. IQR is floored at `1.0` to
  avoid division by zero on constant columns; an all-`NaN` column maps to median `0.0`, IQR `1.0`.
- `n_jobs=1` keeps the fit bit-reproducible.
- `decision_values()` returns raw `decision_function` values (lower = more anomalous); the fitted
  training decisions are retained for thresholding.

Repeat fits on identical input produce bit-identical decision values (unit-tested).

---

## 8. Score Semantics

`anomaly_scores()` returns a **rank-CDF in [0, 1]**, higher = more anomalous. It is:

- **not** a probability of anything;
- **not** calibrated against any real-world outcome;
- **not** the Phase 4 0–100 risk score, and there is no mapping to it anywhere in the codebase;
- a *relative* position in the model's own decision distribution.

### Known limitation: batch-dependent reference distribution

The rank-CDF is computed over the **training rows pooled with the rows being scored**. The score is
therefore a *dataset-relative rank*, not a fixed calibration. Measured on the pinned fixture:

```text
rows 17-21 scored within the full 24-row frame: [0.891892, 0.810811, 0.837838, 0.864865, 1.0]
rows 17-21 scored as a 5-row subset:            [0.833333, 0.666667, 0.722222, 0.777778, 1.0]
identical: False
```

Scoring a different batch therefore shifts the scores of the *same* periods. This is **documented
and deliberately unchanged** in Phase 5; freezing a reference distribution inside the model artifact
is recorded as a deferred decision (§23) because it changes score semantics. The same behaviour is
demonstrated explicitly in the validation notebook (section 8) so it cannot be mistaken for a
calibrated probability.

---

## 9. Thresholding

`threshold_from_expected_rate(train_decision, expected_rate)` takes the empirical quantile of the
**negated training decision distribution** at the declared expected flag rate:

```python
ordered = sorted(-v for v in train_decision)
index = min(len(ordered) - 1, max(0, int(len(ordered) * (1.0 - expected_rate))))
```

A period is flagged when `-decision_function(x) >= threshold`. The rate is a caller-declared
operating parameter, not a tuned constant, and `expected_rate` outside `(0, 1)` raises `ValueError`.

On the pinned golden fixture with `expected_rate = 4/24` the threshold is
**0.017591369042159632**.

---

## 10. Synthetic Anomaly Evaluation

Evaluation uses the Phase 3 synthetic generator's **labelled injected anomalies** only. Metrics are
computed for the model and the baseline on **identical labels**; `evaluate_methods()` refuses inputs
that do not align row-for-row.

Implemented metric set (`evaluate.py`): ROC-AUC, PR-AUC, precision/recall/F1/FPR/FNR at the operating
threshold, and precision@k / recall@k for k ∈ {5, 10}. `_roc_auc` returns `0.5` and `_pr_auc`
returns `0.0` for degenerate single-class label sets rather than raising, and a label set with zero
positives returns `verdict = "insufficient_labels"`.

### Evaluation boundary — these are in-sample numbers

There is **no train/test split**. The model is fitted on the same rows it is then scored on, on a
single 24-period synthetic company. Consequently:

- the reported metrics are **descriptive statistics of the synthetic fixture**;
- they are **not** generalization performance, and must never be presented as such;
- `max_samples="auto"` with 24 rows means each tree sees a subsample, so the model is not memorising
  rows verbatim, which limits but does not eliminate in-sample optimism.

The frozen Phase 5 leakage requirement — "no row-wise random leakage across periods from the same
company" — is satisfied, because every feature is trailing-only and chronological within one company,
and no split exists that rows could leak across. An explicit out-of-sample split would change the
frozen methodology and was **not** introduced; it is listed as deferred (§23).

### Measured result on the pinned fixture — the honest outcome

| metric | Isolation Forest | rule baseline |
|---|---|---|
| ROC-AUC | 0.9000 | 0.9500 |
| **PR-AUC** | **0.5250** | **0.8304** |
| precision | 0.5714 | 0.3636 |
| recall | 1.0000 | 1.0000 |
| F1 | 0.7273 | 0.5333 |
| FPR | 0.1500 | 0.3500 |
| precision@5 / recall@5 | 0.6000 / 0.7500 | 0.6000 / 0.6667 |
| precision@10 / recall@10 | 0.4000 / 1.0000 | 0.4000 / 1.0000 |

```text
verdict = "baseline_wins_or_tie"    (n_periods = 24, n_injected = 4)
```

**The rule baseline beats the Isolation Forest on PR-AUC (0.8304 vs 0.5250).** The verdict is
`baseline_wins_or_tie` because retention requires *both* a higher PR-AUC *and* a higher F1, and the
model's F1 advantage (0.7273 vs 0.5333) is bought by flagging more periods at a fixed expected rate,
which costs precision.

**This is the intended falsifiability behaviour of decision D4** — "retained only if it beats the
baseline". On this fixture the model is **not retained**, and the engine reports that honestly rather
than presenting the model as an accuracy win. No real-world predictive-validity claim is made or
implied, and no external benchmark exists for this system.

---

## 11. SHAP Implementation — planned vs. actual

### 11.1 What the specification anticipated

The master specification (§Explainability, §L2 explanation layer, and the file table) names
**SHAP TreeExplainer (TreeSHAP)** for per-anomaly driver attribution with LIME / permutation
importance as cross-checks. Its risk register also anticipates this exact integration risk:

> "SHAP × IsolationForest integration friction | low | med | **Phase 5 spike first; fallback: explain
> on surrogate / permutation importance (documented)**"

and Phase 0 open question #7 is "SHAP × IsolationForest integration spike — Phase 5 (fallback
documented)". The specification therefore **pre-authorised** a documented permutation-based fallback.

### 11.2 What the production code actually does

`backend/ml_engine/explain.py` does **not** call `shap.TreeExplainer`. There is no `TreeExplainer`
reference anywhere in `backend/`. The implementation constructs:

```python
masker = shap.maskers.Independent(background, max_samples=50)
explainer = shap.Explainer(fitted.model.decision_function, masker, seed=EXPLAINER_SEED)
```

**Verified at runtime:** with `shap 0.52.0`, this call resolves to **`PermutationExplainer`** — a
Monte-Carlo permutation estimator — not to TreeSHAP.

A second, independent fallback exists: `_permutation_row()`, a deterministic permutation-importance
computation (`np.random.default_rng(42)`, 5 rounds) used when SHAP is unavailable, raises, produces
non-finite values, or violates the additivity check.

### 11.3 Why TreeSHAP is not suitable here — measured, not assumed

The engine's attribution contract is `base_value + Σ(values) == decision_function(x)` within
`1e-6`. TreeSHAP explains the ensemble's **raw path-length output**, not the offset-adjusted
`decision_function` the engine attributes against. Measured on the pinned fixture model:

```text
decision_function(x)                  = -0.025343
score_samples(x)                      = -0.525343        (fixed +0.5 offset)
TreeExplainer expected_value          =  4.962134
TreeExplainer base + sum(values)      =  4.473635
additivity error vs decision_function =  4.498977   -> contract violated (tolerance 1e-6)
```

TreeSHAP is structurally unable to satisfy this contract for this model. The permutation route is
therefore the **approved fallback**, not an undocumented substitution.

### 11.4 Honest statement about the repository's history

The repository contains **no committed record** of a TreeExplainer attempt — no code, no test, no
comment and no changelog entry references one. This report therefore does **not** claim that a
TreeExplainer attempt was made and later abandoned. What can be stated from repository evidence is:

- the production code uses `shap.Explainer`, which resolves to `PermutationExplainer`;
- TreeSHAP cannot meet the engine's additivity contract against `decision_function` (measured
  above, reproducible);
- the specification explicitly anticipated this and pre-authorised a documented permutation fallback.

### 11.5 Honest naming note: `"shap_exact"` is a misnomer

The `ExplainerKind` literal is `"shap_exact"` and the golden fixture pins
`"explainer": "shap_exact"`, but the underlying estimator is **approximate**. Measured evidence:

- values differ between sampling seeds by up to ~2.2e-4;
- additivity is nevertheless exact (measured error `0.0`), because `PermutationExplainer` enforces
  the efficiency constraint — **exact additivity is not exact attribution**.

The label is **not renamed in Phase 5**: renaming it would invalidate the committed golden fixture
and is a semantic change requiring separate approval (§23). It is recorded here as an open
interpretation item, analogous to the Phase 4 items Q-M1 / Q-M2 / Q-C1.

---

## 12. Determinism — the SHAP RNG defect and its fix

### 12.1 What was observed

`shap.Explainer` resolves to `PermutationExplainer`, which draws its permutations from the **global
NumPy RNG** at call time. Without explicit control, attribution was **not reproducible**: two
back-to-back attributions of the same row on the same fitted model differed (measured maximum
absolute drift **3.91e-4**), and the driver **ranking reordered** between runs. This was observed
directly: the ML golden passed in isolation but failed in the full-suite run at
`top_drivers[2]`, where `gross_margin_rollvol` and `roa_rollvol` exchanged positions.

### 12.2 What was implemented

`backend/ml_engine/explain.py` now pins and restores the caller's RNG state around the explainer:

```python
rng_state = np.random.get_state()
np.random.seed(EXPLAINER_SEED)          # EXPLAINER_SEED = 42
try:
    masker = shap.maskers.Independent(background, max_samples=50)
    explainer = shap.Explainer(fitted.model.decision_function, masker, seed=EXPLAINER_SEED)
    vector = matrix[row_index : row_index + 1]
    explanation = explainer(vector)
finally:
    np.random.set_state(rng_state)
```

Two independent mechanisms cooperate:

1. the explicit `seed=EXPLAINER_SEED` kwarg, which `shap 0.52`'s `PermutationExplainer` consumes at
   construction (`np.random.seed(seed)`);
2. the manual `get_state()` / `set_state()` wrapper, which additionally protects masker construction
   and guarantees the engine **leaks no RNG state to its caller**.

The additivity contract (`ADDITIVITY_TOL = 1e-6`) is enforced per row, so a non-additive
attribution is rejected and the deterministic `_permutation_row` fallback is used instead.

### 12.3 How repeatability is tested

Determinism is now covered by a **committed regression test**,
`test_attribution_is_stable_after_global_rng_consumption` in
`backend/tests/unit/test_ml_explain.py`. It:

1. records an attribution of a fixed row;
2. burns **9,999 numbers from the global NumPy RNG** (`np.random.seed(12345); np.random.rand(9999)`);
3. re-attributes the same row and asserts the values and base value are **identical**;
4. asserts additivity still holds within `ADDITIVITY_TOL` after the burn;
5. asserts the caller's global RNG state is restored.

The same check is demonstrated interactively in the validation notebook (section 7), including the
explicit assertion that the global RNG state is preserved.

> Note on history: the 9,999-number RNG burn was originally an **interactive verification**, not a
> committed test. It became a committed regression test at the Phase 5 documentation-closure audit,
> at which point it was added to the suite and confirmed passing.

### 12.4 Other determinism guarantees

| Element | Guarantee | Mechanism |
|---|---|---|
| Isolation Forest fit | bit-reproducible | `random_state=42`, `n_jobs=1` |
| Feature matrix | deterministic | pure function of the canonical periods |
| Rule baseline | deterministic | no RNG anywhere |
| Permutation fallback | deterministic | `np.random.default_rng(42)`, fixed 5 rounds |
| SHAP attribution | deterministic | explicit seed + RNG save/restore |
| Artifact fingerprint | stable | SHA-256 over the full matrix + build config |
| Golden fixture | pinned | `--regen-golden`, `abs_tol = 1e-9` |

Measured in the notebook: additivity error `2.776e-17`, attribution identical after the burn, RNG
state preserved.

---

## 13. Artifact Integrity

`train_artifact()` persists a versioned artifact directory containing:

- `model.joblib` — the fitted model plus `feature_names`, `medians`, `iqrs`, `train_decision`,
  `random_state` and `config`;
- `metadata.json` — a `ModelMetadata` document: `model_version`, `feature_schema_version`,
  `feature_names`, `config`, `random_state`, `threshold`, `training_fingerprint` and a nested
  `Provenance` block (`generator_seeds`, `registry_version`, `random_state`, `input_fingerprint`,
  `detail.complete_rows`).

**Verified behaviours (all unit-tested):**

| Behaviour | Result |
|---|---|
| train → save → load round trip | Loaded model reproduces identical decision values |
| Metadata serialization | `metadata.json` is stable, sorted JSON |
| Invalid operating rate | `expected_anomaly_rate` outside `(0, 1)` raises `ValueError` (tested at 0.0, 1.0, −0.5, 1.5) |
| Schema validation — payload vs. metadata | Tampering `metadata.json` `feature_names` raises `ValueError("artifact model/metadata feature schema mismatch")` |
| Schema validation — vs. contract | Tampering both consistently so they agree but differ from `FEATURE_NAMES` raises `ValueError("artifact feature schema does not match FEATURE_SCHEMA_VERSION")` |
| Input fingerprint | SHA-256 over the feature matrix and build config |

`checksum_file()` computes a streaming SHA-256 digest of a file (verified against `hashlib`).

> **Accurate statement of checksum usage:** the checksum is **generated for provenance and audit
> purposes only**. It is **not** stored inside `metadata.json` and it is **not verified at load
> time**. Tamper detection today rests on the **schema validation** checks described above (model vs.
> metadata feature lists, and both vs. the frozen `FEATURE_NAMES`), not on a digest comparison.
> Persisting and enforcing a checksum at load is a deferred item (§23).

No model binary is committed to the repository; `.gitignore` continues to exclude build and coverage
artifacts, and the ML golden is a small deterministic JSON fixture.

---

## 14. Missing-Data Behavior

The engine follows the Phase 4 missing-input philosophy and **never fabricates financial values**.
There is no zero-filling, no forward-fill, no interpolation and no imputation anywhere in
`features.py`, `models.py`, `baseline.py` or `explain.py`.

| Condition | Behavior | Verified |
|---|---|---|
| Ratio calculator raises | feature becomes `None` (never `0.0`) | unit test |
| Calculator returns a non-valid `MetricStatus` | feature becomes `None` | unit test |
| `None` / non-numeric / infinite period field | feature becomes `None` | unit tests |
| Period with no trailing history | `_delta` / `_rollvol` are missing | unit test |
| Single-period frame | all history-derived features missing | unit test |
| Any missing feature in a row | row excluded from model training (`dropna`) | unit test |
| Empty training frame / no complete rows | `ValueError("no complete feature rows available for training")` | unit test |
| Constant feature (IQR = 0) | IQR floored at `1.0`; no division by zero | unit test |
| All-`NaN` column | median `0.0`, IQR `1.0` (scaling constants only, not financial values) | unit test |
| Non-numeric cell in the rule baseline | cell skipped, never treated as 0 | unit test |
| Unsupported period object type | `TypeError` with an explicit message | unit test |
| Zero positive labels | `verdict = "insufficient_labels"` | unit test |
| Single-class labels | ROC-AUC → `0.5`, PR-AUC → `0.0` (no raise) | unit test |
| Mismatched evaluation input lengths | `ValueError("evaluation inputs must align row-for-row")` | unit test |
| Duplicate periods | not explicitly tested — recorded as an open edge case (§23) | — |

The notebook (section 9) demonstrates the three headline cases live: an all-missing period yields
`NaN` features rather than zeros, a malformed field degrades to a missing feature rather than a
crash or a fabricated number, and an empty training frame raises `ValueError`.

---

## 15. Leakage Controls

| Control | Implementation | Verified |
|---|---|---|
| No identifier / metadata / label features | `FORBIDDEN_COLUMNS` intersected with the built frame; raises on intersection | unit test + notebook |
| Absolute currency levels excluded | only ratios, deltas and volatilities are built | unit test |
| Chronological ordering within a company | periods sorted by `period_end` before feature construction | unit test |
| No look-ahead in features | deltas and rolling stats use trailing history only | unit test |
| No look-ahead in the baseline | trailing `iloc[max(0, i-window) : i]` slice | unit test |
| Labels are evaluation-only | passed separately to `evaluate_methods()`; read by no feature/model code | unit test |
| Phase 4 judgments excluded | registry `score` / `severity` are never features | unit test |
| Unlabeled real-world data | EDGAR statements are never treated as anomaly labels | codebase-wide |

**Evaluation split:** there is no train/test split; see §10 for the in-sample scope statement.

---

## 16. Explainability Output Contract

`explain_flagged_period()` returns an `AnomalyExplanation` carrying:

| Field | Content |
|---|---|
| `company_id`, `period_end` | row identity (the identifier is *carried*, never a feature) |
| `explainer` | which explainer produced the values (`shap_exact` / `permutation` — see §11.5) |
| `explainer_version` | `shap.__version__` (measured `0.52.0`), or `permutation-builtin` if shap is absent |
| `drivers` | top-k `DriverContribution`, each with `feature`, `attribution`, `feature_value` (parsed, `None` when non-finite/non-numeric) and `direction` (`pushes_anomalous` / `pushes_normal`) |
| `background` | description of the background sample used |
| `causality_note` | `CAUSALITY_DISCLAIMER` — attribution is not causation |
| `anomaly_note` | `ANOMALY_RISK_DISCLAIMER` — an anomaly is not a financial-risk judgment |

Drivers are ranked by **absolute** attribution, so the sign (captured in `direction`) and the
magnitude are both reported. Attribution of a lower `decision_function` (i.e. more anomalous) is
negative, and the direction label is derived from that sign.

**Global explanation:** `global_summary()` ranks features by mean absolute attribution across a list
of explained rows and returns a full feature ordering; it returns `[]` for an empty input.

**Attribution is presented as attribution, never as causation.** The causality disclaimer is a
contract default and is stamped onto every explanation object, not merely documented in prose.

---

## 17. Provenance

`Provenance` carries `generator_seeds`, `registry_version`, `feature_schema_version`,
`model_version`, `random_state`, `input_fingerprint` and a free-form `detail` map. `train_artifact()`
populates it from the caller-declared seeds, the registry version string, the fitted random state and
a SHA-256 fingerprint of the exact training matrix plus its build configuration.

`fingerprint_frame()` hashes the schema version, the column list, every row value (non-finite values
normalised to `null`) and the build config, giving a stable identity for the exact input a model was
trained on.

> Scope note: `AnomalyResult`, `MLFinding` and `Provenance` are fully defined, typed and unit-covered
> contracts, but **no orchestration function constructs them in production yet** — `train_artifact()`
> is currently invoked only from tests. Wiring detection output into these contracts belongs to the
> Phase 9 agent layer / Phase 10 API (§23).

---

## 18. Testing

| Suite | File | Coverage |
|---|---|---|
| Features / leakage | `backend/tests/unit/test_ml_features.py` | shape (24, 27), forbidden columns, determinism, trailing deltas, rollvol minimum history, `_period_dict` guards, `_finite_or_none`, malformed periods |
| Models / baseline | `backend/tests/unit/test_ml_models.py` | score bounds and rank consistency, threshold flag share, repeat-fit determinism, empty-frame rejection, trailing-only baseline, injected-window detection, non-numeric cells, robust-params fallback, threshold range validation |
| Explain / evaluate | `backend/tests/unit/test_ml_explain.py` | attribution finiteness, top-k drivers, global summary, evaluation metrics and verdict, input-alignment rejection, insufficient labels, single-class helpers, **permutation fallback determinism**, **SHAP failure paths (NaN values, non-additive, raising explainer)**, **missing-shap module path**, **non-finite feature-value parsing**, **RNG-burn determinism + additivity + state restoration** |
| Artifacts | `backend/tests/unit/test_ml_train.py` | train→load round trip, metadata JSON, checksum, invalid-rate rejection, metadata tamper rejection, schema-version tamper rejection |
| Property | `backend/tests/property/test_ml_properties.py` | seeded (`random.Random(42)`) magnitude monotonicity, threshold/flag score consistency, baseline monotonicity |
| Golden | `backend/tests/golden/test_ml_goldens.py` | pinned seed 7101 fixture, full recursive comparison |

Property tests use **deterministic seeded randomization** (`random.Random(42)`), consistent with the
Phase 4 decision that Hypothesis is not used.

The three uncovered statements in `features.py` are the unreachable leakage-guard `raise` and its
two supporting lines — defensive code that no normal input can trigger.

---

## 19. Notebook

`notebooks/05_ml_engine/01_ml_anomaly_validation.ipynb` — **24 cells (13 code, 11 markdown)**,
executed top-to-bottom from a fresh kernel with `nbclient` at the Phase 5 closure audit.

The notebook is **validation and documentation only**. It contains no production logic: every
computation is a call into `backend/ml_engine/*` or `backend/data_engine/*`. It uses only locally
generated synthetic data, performs no network access, and requires no API keys.

Sections: (1) setup/path bootstrap, (2) 27-column feature contract + leakage-guard assertion,
(3) trailing-only rule baseline, (4) Isolation Forest + thresholding + anomaly scores, (5)
baseline-vs-model evaluation with the honest verdict, (6) SHAP explanation + additivity assertion,
(7) determinism with a 9,999-number RNG burn + RNG-state preservation, (8) batch-dependent
rank-CDF, (9) missing-data behaviour, plus a closing summary table.

**Execution result:** all 24 cells executed, **0 error outputs**. Observed values include frame shape
`(24, 27)`, leakage guard "none", threshold `0.017591369042`, verdict `baseline_wins_or_tie`,
explainer `shap_exact` / version `0.52.0`, additivity error `2.776e-17`, and identical attribution
after the RNG burn.

One real defect was caught and fixed during this execution: the explanation cell initially referenced
`company.profile.company_id`, which does not exist on the `CompanyProfile` contract; it now uses
`company.edgar_cik`. The failure was surfaced by the fresh-kernel run, not suppressed.

---

## 20. Dependencies

Declared in `pyproject.toml` `[project].dependencies`:

```toml
"scikit-learn>=1.3,<2",
"shap>=0.45",
"joblib>=1.3",
```

`joblib` is now declared explicitly (it was previously only a transitive dependency of
scikit-learn, while `train.py` imports it directly).

`requirements-lock.txt` pins the full closure, and the **installed versions match the lockfile
exactly** (verified at runtime):

| Package | Locked / installed |
|---|---|
| scikit-learn | 1.9.1 |
| shap | 0.52.0 |
| scipy | 1.18.1 |
| joblib | 1.6.0 |
| numba | 0.68.0 |
| llvmlite | 0.50.0 |
| slicer | 0.0.8 |
| cloudpickle | 3.1.2 |
| narwhals | 2.26.0 |
| threadpoolctl | 3.7.0 |
| tqdm | 4.70.1 |

No existing dependency version was changed; the lockfile entry for `joblib` remains `1.6.0`.

---

## 21. Verification Results (at Phase 5 documentation closure)

All commands were executed on the repository after the Phase 5 changes.

```text
pytest backend/tests -q                       -> 270 passed
ruff check backend scripts                    -> All checks passed!
ruff format --check backend scripts           -> 101 files already formatted
mypy backend                                  -> Success: no issues found in 97 source files
pytest backend/tests -q --cov=backend          -> ml_engine line coverage 99%
```

Coverage by module (`ml_engine`, 503 statements):

| Module | Statements | Coverage |
|---|---|---|
| `ml_engine/__init__.py` | 1 | 100% |
| `ml_engine/contracts.py` | 62 | 100% |
| `ml_engine/features.py` | 86 | 97% |
| `ml_engine/models.py` | 86 | 100% |
| `ml_engine/baseline.py` | 48 | 100% |
| `ml_engine/explain.py` | 96 | 100% |
| `ml_engine/evaluate.py` | 77 | 100% |
| `ml_engine/train.py` | 52 | 100% |
| **total** | **503** | **99%** |

Phase 4 is unaffected: `risk_engine` coverage remains **94%** (`scoring.py` 94%, `registry.py` 95%,
`engine.py` 98%), registry coverage remains 40/40, contribution reconciliation remains 5/5, and the
Phase 4 golden profiles `seed_1001.json` … `seed_1005.json` are byte-for-byte unchanged.

Test count progression: 223 at Phase 4 closure → 269 at Phase 5 engineering completion → **270**
after adding the committed SHAP determinism regression test.

Notebook execution: `notebooks/05_ml_engine/01_ml_anomaly_validation.ipynb` executed top-to-bottom
from a fresh kernel via `nbclient` — 24 cells, 0 errors.

---

## 22. Known Limitations

1. **The rule baseline currently beats the Isolation Forest** on the pinned fixture
   (PR-AUC 0.8304 vs 0.5250). The model is not retained. No accuracy improvement is claimed.
2. **Evaluation is in-sample.** No train/test split exists; all metrics are descriptive statistics of
   a single 24-period synthetic company and are not generalization estimates.
3. **Attribution is approximate.** The permutation estimator varies by ~2.2e-4 between seeds; the
   `"shap_exact"` label overstates its precision (§11.5).
4. **Anomaly scores are batch-dependent** — the rank-CDF pools training rows with the rows being
   scored, so the same period can score differently in a different batch (§8).
5. **No real-world validation.** Evaluation uses synthetic injected anomalies only. No audited
   financial statements, no external benchmark, no predictive-validity claim.
6. **Not causal.** SHAP drivers explain the model's output, not the business cause of the anomaly.
7. **Anomaly ≠ financial risk.** No mapping onto the Phase 4 0–100 composite exists, and none is
   planned implicitly.
8. **Not a professional risk tool.** This is a decision-support and research platform; it does not
   replace a professional risk team.
9. **No production entry point.** Detection is currently invoked from tests and the notebook; the
   `AnomalyResult` / `MLFinding` contracts are declared but not produced by an orchestrator.
10. **Checksum not enforced on load** (§13).
11. **Duplicate-period input is not explicitly tested** (§14).
12. **No anomaly severity mapping.** Anomaly scores are not converted into Low/Moderate/High/Critical
    bands; that concept belongs to Phase 4 scoring and is deliberately not duplicated here.

---

## 23. Deferred Items

None of these were implemented; each requires separate approval.

| # | Item | Why deferred |
|---|---|---|
| D-1 | Rename `ExplainerKind` `"shap_exact"` to reflect the permutation estimator | Would invalidate the committed golden fixture; changes output semantics |
| D-2 | Freeze a reference distribution inside the model artifact so scores stop being batch-dependent | Changes score semantics |
| D-3 | Introduce an explicit out-of-sample evaluation split | Changes frozen Phase 5 methodology |
| D-4 | Persist the artifact checksum in `metadata.json` and verify it on load | Changes artifact format (`MODEL_VERSION`) |
| D-5 | A production detection orchestrator producing `AnomalyResult` / `MLFinding` | Phase 9 agent layer / Phase 10 API |
| D-6 | Persist trained artifacts to the database / expose a model registry | Phase 10 persistence |
| D-7 | LIME cross-check | Not implemented; the deterministic permutation fallback is the documented substitute |
| D-8 | Real-company evaluation against EDGAR statements | Unlabeled real data cannot serve as ground truth; would need a labeled real dataset |
| D-9 | Phase 13 external benchmark harness | Out of scope by design |
| D-10 | Duplicate-period handling test | Open edge case, low priority |

---

## 24. Research Interpretation

Phase 5 demonstrates a property that matters more than the model itself: **a focused ML component
can be built into a deterministic research platform without contaminating the audited risk
methodology, and it can report that it lost.**

Three findings are worth recording as research results rather than as engineering trivia:

1. **Falsifiability was exercised, not asserted.** The engine was required to beat a transparent
   statistical baseline, and on the pinned fixture it did not. The system reports
   `baseline_wins_or_tie` rather than re-tuning until the model won. Decision D4 is therefore
   demonstrated to be enforceable, not merely written.
2. **Explainability carries a reproducibility obligation.** A defensible explanation that varies run
   to run is not auditable. The SHAP RNG defect shows that adding an explanation layer introduced a
   new determinism requirement that the rest of the platform already satisfied by construction, and
   that the requirement had to be enforced explicitly (seed + state save/restore) rather than assumed.
3. **Attribution must be labelled honestly.** The `"shap_exact"` label on an approximate estimator is
   a small but real scientific-integrity defect: it would let a downstream consumer treat a sampled
   approximation as an exact decomposition. The naming discrepancy is documented rather than silently
   fixed precisely because fixing it changes a pinned artifact.

The boundary between "unusual behaviour" (Phase 5) and "quantified financial risk" (Phase 4) is now
enforced in code, contracts, tests and documentation. The ML engine contributes an independent
signal; it does not alter, replace or reinterpret the Phase 4 risk score.

---

## 25. Phase 6 Boundary

Phase 5 ends here. The following are explicitly **not** part of this phase and were not started:
business digital twin, scenario engine, stress testing and propagation, mitigation, LangGraph agent
graph, the `ml_anomaly` agent, the REST/SSE API surface, the frontend, and any database schema
expansion. Phase 5 consumes Phase 3 and Phase 4 contracts read-only and modifies no Phase 4
methodology, formula, anchor, scoring rule, sensitivity rule or golden fixture.

---

**PHASE 5 DOCUMENTATION CLOSURE COMPLETE — AWAITING USER REVIEW.**
**Next phase after approval: PHASE 6 — BUSINESS DIGITAL TWIN (not started).**
