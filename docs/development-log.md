# AI Business Risk — Development Log

Running log of phases, decisions, and open questions. Newest phase at the top.

---

## Phase 8 — Stress Testing & Impact Analysis (2026-10-03)

**Status:** Engineering complete — documentation closed. Awaiting approval for Phase 9.
**Scope:** `backend/simulation/stress.py` (baseline-vs-stressed comparison, KPI deltas, frozen
breach policy, EBITDA waterfall + below-EBITDA bridge) and `backend/simulation/sensitivity.py`
(single-factor sweeps), plus unit/property/golden tests, the validation notebook and the phase
report.
**Upstream (read-only):** Phase 6 `simulate()` / `SimulationRunResult` / `assumption_records`;
Phase 7 `scenarios.py`; `backend/core/errors.py`.
**Authority:** `docs/01_architecture/simulation.md` §5–§6 (frozen at Phase 1). The §5 output list
and every §6 invariant stand as written; two clearly-marked implementation-status notes were
appended *after* the frozen text (the `testing.md` §7 recorded-status precedent).

- **Created** `stress.py` (`STRESS_VERSION = "1.0.0"`: `run_stress`, `compare_kpis`,
  `detect_breaches`, `attribute_waterfall`, `resolve_min_cash_buffer`, `BreachPolicy`),
  `sensitivity.py` (`SWEEPABLE_FIELDS` of nine bounded shocks, 9-point inclusive grid ∪ {0.0},
  OFAT from the zero-shock baseline, `breach_onset`), 32 unit tests + 3 property tests + 19 golden
  cases, `stress_seed_1001..1005.json` goldens and
  `notebooks/08_stress_testing/01_stress_validation.ipynb`.
- **Locked decisions A–L** recorded in `docs/08_stress_testing/phase-report.md` §2: one module
  version, one deterministic `simulate()` path for both runs, an undefined Δ% carries a *reason*,
  breach output is status/records only (no severity labels), frozen listing orders, SHA-256
  `result_hash`, no `backend/guardrails/` package.
- **D-6-3 pinned, not resolved:** on seed 1002 a −37.5% revenue contraction *raises* trough cash
  above the zero-shock baseline while EBITDA and DSCR fall (working-capital release through
  `OCF = NI + DA − ΔNWC`); the frozen §6.3 monotonicity invariant is contradicted and reported,
  never smoothed over. Amending it still requires change control.
- **New honest finding — capacity-ceiling saturation:** seed 1001 runs at its
  `revenue_capacity` (trailing-12-month maximum) in every baseline month, so positive
  `revenue_change_pct` shocks raise *demand* but leave revenue — and every KPI — identical to
  baseline; partially-capped seeds respond and then plateau. This is frozen twin behaviour (§1/§2),
  surfaced by the sweep, pinned in the notebook and recorded as Phase 8 limitation 8 rather than
  hidden; downside shocks are unaffected.
- **Evidence at closure:** **498 tests passing** (444 at Phase 7 closure → +54); `stress.py` and
  `sensitivity.py` coverage **97%** each (above the ≥80% NFR3 floor); Phase 4/5/6/7 suites green
  with `seed_100*.json`, `ml_anomaly_golden.json`, `twin_seed_*.json` and the scenario suites
  untouched; Ruff / Ruff-format / Mypy clean; goldens added as **new** files regenerated only via
  `pytest --regen-golden` and gated on `STRESS_VERSION`; the notebook executes from a fresh kernel
  (17 cells, 8 code, **0 error outputs**) with exact waterfall closure, byte-identical repeated
  `result_hash` and a hand-checked revenue-effect residual of 0.000e+00.
- **Documentation:** created `docs/08_stress_testing/phase-report.md`; status synchronized in
  `README.md`, `docs/master-project-specification.md`, `docs/01_architecture/project-overview.md`
  and `docs/01_architecture/testing.md` (Phase 8 golden family + coverage note);
  implementation-status notes appended to `simulation.md` §5/§6 with **no invariant amended**;
  this entry plus a retroactive Phase 7 entry (Phase 7 had been committed without one).
- **No Phase 4/5/6/7 file, formula, anchor, scoring rule or golden fixture was modified.**
  `backend/simulation/__init__.py` stays untouched — like Phase 7's `scenarios`, Phase 8 is
  consumed as a submodule (`from backend.simulation import stress`).

### Deferred (recorded, not implemented)

`D-6-3` frozen §6.3 trough-cash monotonicity (change control) · `D-6-4` annual→monthly conversion
(Phase 3) · `D-6-7` dimension deltas via Phase 4 re-scoring · `D-6-8` equity / balance-sheet
roll-forward; reverse stress testing · live scenario translation (Phase 9) · persistence of custom
breach policies, services and API (Phase 10).

### Approval gate

**PHASE 8 IMPLEMENTATION COMPLETE — AWAITING USER REVIEW BEFORE COMMIT/PUSH.**
**Next phase after approval: PHASE 9 — MULTI-AGENT LANGGRAPH (not started).**

---


## Phase 7 — Scenario Engine (2026-10-03)

**Status:** Engineering complete — approved and committed (`ec5b6aa`); logged retroactively in the
Phase 8 documentation pass (the phase report shipped with the code, but this log entry was missing).
**Scope:** `backend/simulation/scenarios.py` — the frozen `simulation.md` §3 schema and §4 presets,
plus 52 unit tests, 4 property tests and
`notebooks/07_scenario_engine/01_scenario_validation.ipynb`.
**Upstream:** Phase 6 `SimulationOverrides` (read-only normalization target);
`backend/core/errors.py`.

- **Created** `scenarios.py` (`SCENARIO_VERSION = "1.0.0"`): `ScenarioParams` (`extra="forbid"`),
  clamp-within-1.25× / reject `FIELD_BOUNDS` with `ClampEvent.rule = scenario_bounds.<field>`,
  the eight frozen presets, the FD-3 confirmation dock (`validate_candidate` → `confirm`
  re-validates; `cancel`), D-6 normalization `to_overrides` (pct/pp ÷ 100),
  `normalize_basis_points` (200bp → 2.0pp with mapping note) and SHA-256 `ScenarioProvenance`.
- **Locked decisions A–L** recorded in `docs/07_scenario_engine/phase-report.md` §2 — including F
  (`ramp_months > horizon_months` rejected), C (ambiguous "rates rise 2%" stays
  `awaiting_confirmation` at rate 0.0), K (`one_off_cost` unbounded) and L (no
  `backend/guardrails/` package; the policy lives in `scenarios.py`).
- **Evidence at closure:** 444 passed (+56 over Phase 6); `scenarios.py` coverage **100%** (175
  statements, 0 missed); Phase 4/5/6 suites green and goldens byte-identical; Ruff / format / mypy
  clean (108 source files); notebook executes fresh-kernel (7 code cells, 0 errors, no twin call);
  zero new dependencies. Frozen `simulation.md` not modified.

### Approval gate

**PHASE 7 IMPLEMENTATION COMPLETE — APPROVED; COMMITTED `ec5b6aa` (2026-10-03).**
**Next phase: PHASE 8 — STRESS TESTING.**

---

## Phase 6 — Business Digital Twin (2026-10-02)

**Status:** Engineering complete — documentation closed. Awaiting approval for Phase 7.
**Scope:** `backend/simulation/` (deterministic, LLM-independent monthly financial recursion)
plus the Phase 6 validation notebook and twin trajectory goldens.
**Upstream:** Phase 3 canonical periods and Phase 4 metric calculators, consumed read-only.
**Authority:** `docs/01_architecture/simulation.md` §1–§2 (frozen at Phase 1), implemented
verbatim. The frozen document was **not** modified.

- **Created** `backend/simulation/__init__.py` (exports and frozen scope disclaimers),
  `contracts.py` (typed contracts, `TWIN_VERSION = "1.0.0"`, `SimulationStatus`,
  `MonthLedger`), `assumptions.py` (frozen §1 parameter derivation) and `twin.py` (frozen §2
  monthly recursion, invariant checks, `run_twin`, `simulate`).
- **The frozen §2 equations are implemented verbatim, not the simplified set carried in the
  Phase 6 planning prompt** (decision D-0). The frozen version adds a supply ceiling
  `Capacity0`, FX demand elasticity, commodity and FX cost legs damped by `(1−ptc)`, a split
  floating/fixed interest basis, revolver draws against a minimum-cash buffer, and an
  explicit `funding_gap` breach. Implementing the subset would have deleted the FX/commodity
  channels the project advertises as a research contribution.
- **Phase 4 was reused, not modified.** `calc_interest_coverage` and
  `calc_cash_runway_months` fit the twin's per-month outputs exactly. `calc_dscr` needs a
  short-term balance that §2 never projects, so the month's actual scheduled principal is
  supplied as `st_debt`, yielding the standard monthly debt-service-coverage ratio. This is
  the only semantic substitution in the phase and it is documented at the call site.
- **Explicit missing-input behaviour.** Nothing is zero-filled, interpolated or
  forward-filled. A missing required series raises with the offending period named. Short
  histories raise `InsufficientHistoryError` rather than silently shortening the frozen
  12-month derivation window.
- **Honest finding recorded, not smoothed over (deferred D-6-3):** frozen §6.3's claim that
  single-factor sweeps move *trough cash* monotonically does **not** hold for contraction
  shocks. Under a −30% revenue shock on seed 1002, net income turns negative while operating
  cash flow stays positive, because `OCF = NI + DA − ΔNWC` and a shrinking business releases
  working capital (ΔNWC ≈ −4.5M in month 1). Trough cash *rises* (14.1M → 19.5M) while DSCR
  falls (0.597 → 0.022) and EBITDA falls. This is economically coherent, is pinned by a
  dedicated test, and is a genuine contradiction of a frozen invariant. **It is not resolved
  here** — amending a frozen invariant requires user approval via change control.
- **Honest limitation recorded (D-1):** the twin requires ≥ 12 monthly periods.
  `edgar.py` yields ANNUAL/QUARTERLY only and `normalize/periods.py` aggregates upward only,
  so no annual→monthly decomposer exists in the repository. Real annual-filing companies
  cannot be simulated yet; the fix belongs in Phase 3, not Phase 6.
- **Zero new dependencies.** `pyproject.toml` and `requirements-lock.txt` are byte-identical.
- **Evidence at closure:** **388 tests passing** (270 at Phase 5 closure → +118); `simulation`
  coverage **97–100%** (above the ≥80% NFR3 floor); `risk_engine` **94%** and `ml_engine`
  **97%**, both unchanged; Ruff and Ruff-format clean (`backend/`, `scripts/`, 109 files);
  Mypy clean (105 files); Phase 4 goldens 1001–1005 byte-for-byte unchanged and the Phase 5
  ML golden untouched; twin goldens added as **new** files `twin_seed_1001..1005.json`
  generated only via `pytest --regen-golden` and gated on `TWIN_VERSION`; the Phase 6
  notebook executes from a fresh kernel (27 cells, 13 code, **0 error outputs**) with a
  hand-calculated month 1 matching the engine to a worst relative residual of **1.7e-16**.
- **Documentation:** created `docs/06_digital_twin/phase-report.md`; status synchronized in
  `README.md`, `docs/master-project-specification.md` and `docs/01_architecture/testing.md`.
- **No Phase 4 or Phase 5 file, formula, anchor, scoring rule, sensitivity rule or golden
  fixture was modified.** `scenarios.py`, `stress.py` and `sensitivity.py` (Phases 7/8) were
  not created. No Phase 7 implementation occurred.

### Deferred (recorded, not implemented)

`D-6-3` frozen §6.3 trough-cash monotonicity needs an explicit decision · `D-6-4`
annual→monthly conversion for real filings (Phase 3) · `D-6-5` `scenarios.py` (Phase 7) ·
`D-6-6` `stress.py` / `sensitivity.py` (Phase 8) · `D-6-7` re-scoring the projected end-state
through Phase 4 for dimension deltas (Phase 8) · `D-6-8` equity / balance-sheet roll-forward ·
`D-6-9` persistence and a service/API entry point (Phase 10) · `D-6-10` bridging twin
trajectories into the Phase 5 ML feature matrix.

### Approval gate

**PHASE 6 DOCUMENTATION CLOSURE COMPLETE — AWAITING USER REVIEW.**
**Next phase after approval: PHASE 7 — SCENARIO ENGINE (not started).**

---

## Phase 5 — ML Engine (2026-10-02)

**Status:** Engineering complete — documentation closed. Awaiting approval for Phase 6.
**Scope:** `backend/ml_engine/` (deterministic, LLM-independent) plus the Phase 5 validation notebook.
**Upstream:** Phase 3 canonical periods and the Phase 4 metric calculators, consumed read-only.

### 5A — Engine implementation

**Implemented:** `backend/ml_engine/` — `contracts.py` (typed `Provenance`, `AnomalyResult`,
`DriverContribution`, `AnomalyExplanation`, `ModelMetadata`, `MLFinding`, frozen disclaimers,
`FEATURE_SCHEMA_VERSION = "1.0.0"`); `features.py` (27-column scale-free ratio matrix built from
**Phase 4 calculators**, trailing deltas and rolling volatility, `FORBIDDEN_COLUMNS` leakage guard,
SHA-256 frame fingerprint); `models.py` (Isolation Forest `n_estimators=200`, `random_state=42`,
`n_jobs=1`, median/IQR scaling, rank-CDF scores in `[0, 1]`, quantile thresholding);
`baseline.py` (trailing-only rolling z-score / Tukey-IQR rule, window 12, min 8 obs, `|z| >= 3.0`);
`explain.py` (SHAP attribution with a `1e-6` additivity contract plus a deterministic permutation
fallback); `evaluate.py` (ROC-AUC, PR-AUC, precision/recall/F1/FPR/FNR, precision@k, recall@k,
verdict); `train.py` (versioned `model.joblib` + `metadata.json`, checksum, schema validation).

**Key decisions:**
- **Anomaly ≠ risk.** No mapping from an anomaly score to the Phase 4 0–100 composite exists, and the
  disclaimers are contract defaults stamped onto every output rather than prose.
- **Falsifiability (D4).** The Isolation Forest is retained only if it beats the rule baseline on both
  PR-AUC and F1. On the pinned fixture it does not.
- **Phase 4 reuse, not reimplementation.** The ML feature matrix calls the frozen Phase 4 calculators,
  so the two engines cannot silently diverge.
- **R3 preserved.** `ml_engine` imports no `app`/`agents`/`llm`/`services` module; this is enforced by
  the existing AST scan in `test_architecture_imports.py`, which already listed `ml_engine` before the
  package existed.

### 5B — Determinism defect found and fixed

`shap.Explainer` resolves to `PermutationExplainer`, which samples permutations from the **global
NumPy RNG**. Attribution was therefore not reproducible: two back-to-back attributions of the same
row differed by up to `3.91e-4`, and the driver ranking reordered. This surfaced as a golden
regression — `top_drivers[2]` flipped between an isolated run and the full suite.

**Fix:** explicit `seed=EXPLAINER_SEED` (42) passed to `shap.Explainer`, plus
`np.random.get_state()` / `set_state()` save-restore around masker construction and the explainer
call, so the engine leaks no RNG state to its caller. Attribution is now identical after a
9,999-number RNG burn, and additivity holds (measured notebook error `2.776e-17`).

### 5C — Final documentation closure (this entry)

- **SHAP decision, recorded honestly.** The production code does **not** call `shap.TreeExplainer`;
  it calls `shap.Explainer`, which SHAP 0.52.0 resolves to `PermutationExplainer`. TreeSHAP cannot
  satisfy the engine's additivity contract against `decision_function` — measured mismatch
  `4.498977` (base + Σvalues `4.473635` vs `decision_function(x)` `-0.025343`) — because it explains
  the ensemble's raw path-length output. The master specification anticipated exactly this
  ("Phase 5 spike first; fallback: explain on surrogate / permutation importance (documented)"), so
  the permutation route is the **approved fallback**. The repository contains **no** committed record
  of a TreeExplainer attempt, and the report does not claim one.
- **Open interpretation item recorded (not fixed):** the internal `ExplainerKind` literal
  `"shap_exact"` is a misnomer for an approximate estimator (seed-to-seed drift ~2.2e-4). Renaming it
  would invalidate the committed golden, so it is documented as deferred item D-1.
- **Honest evaluation result:** model PR-AUC **0.5250** vs rule baseline PR-AUC **0.8304**, verdict
  **`baseline_wins_or_tie`**. The baseline wins on the pinned fixture; the model is not retained.
- **Evaluation boundary recorded:** there is no train/test split, so all metrics are **in-sample**
  descriptive statistics of a single 24-period synthetic company, not generalization performance.
- **Score semantics recorded:** `anomaly_scores()` is a rank-CDF over training rows **pooled with the
  rows being scored**, so it is batch-dependent (the same period scores differently in a different
  batch). Documented and deliberately unchanged; freezing a reference distribution is deferred (D-2).
- **Artifact integrity stated accurately:** `checksum_file()` generates a SHA-256 digest for
  provenance, but it is **not** stored in metadata and **not** verified on load. Tamper detection
  rests on schema validation (model vs. metadata feature lists, and both vs. `FEATURE_NAMES`),
  which is unit-tested for both tamper modes. Enforcing the checksum is deferred (D-4).
- **Notebook:** created `notebooks/05_ml_engine/01_ml_anomaly_validation.ipynb` (24 cells, 13 code) —
  validation/documentation only, no production logic, local synthetic data, no network, no API keys.
  Executed top-to-bottom from a fresh kernel with `nbclient`: **24 cells executed, 0 error outputs**.
  The run surfaced one genuine defect (`company.profile.company_id` does not exist on
  `CompanyProfile`), fixed to `company.edgar_cik` before the final execution.
- **Regression test added (test-only):**
  `test_attribution_is_stable_after_global_rng_consumption` in `backend/tests/unit/test_ml_explain.py`
  — asserts identical attribution and base value after burning 9,999 global NumPy random numbers,
  additivity within `ADDITIVITY_TOL`, and restoration of the caller's RNG state. This check was
  previously an interactive verification only; it is now a committed test and passes.
- **Dependency declaration:** added `joblib>=1.3` to `pyproject.toml` (`train.py` imports it
  directly; it had only been a transitive scikit-learn dependency). The lockfile version
  `joblib==1.6.0` is unchanged.
- **Evidence at closure:** **270 tests passing** (223 at Phase 4 closure → 269 at Phase 5 engineering
  completion → 270 with the determinism regression test); `ml_engine` coverage **99%** (503 statements);
  `risk_engine` coverage **94%**, unchanged; registry coverage **40/40**; contribution reconciliation
  **5/5**; Phase 4 golden profiles 1001–1005 byte-for-byte unchanged; ML golden
  (`ml_anomaly_golden.json`, seed 7101) passing and **not** regenerated during this closure; Ruff and
  Ruff-format clean on the code targets (`backend/`, `scripts/`, 101 files); Mypy clean (97 files).
- **Synchronized status** in `README.md`, `docs/01_architecture/project-overview.md`,
  `docs/master-project-specification.md` and `docs/01_architecture/testing.md`.
- **Repository cleanup at Phase 5 publication:** the obsolete `omnirush.md` status snapshot was
  **removed**. It was an OmniRush-era agent instruction/context file with no code, test, CI,
  packaging, Docker or Alembic dependency; every status fact it carried is preserved in `README.md`,
  this development log and the per-phase reports. Cline is the development agent. Two historical
  mentions of the file are deliberately retained in `docs/03_data-engineering/phase-report.md` and in
  the Phase 4 entry above, because they accurately describe what existed at the time. `graphify-out/`
  and `raw/` were added to `.gitignore` so that external Graphify tooling output can never be
  committed.
- No Phase 4 file, formula, anchor, scoring rule, sensitivity rule or golden fixture was modified. No
  Phase 6 implementation occurred. The Phase 5 work and the repository cleanup were published as a
  single commit on `main`; no previous commit was amended or rewritten.

### Deferred (recorded, not implemented)

`D-1` rename the `"shap_exact"` explainer label (changes the golden) · `D-2` freeze a reference
distribution so scores stop being batch-dependent · `D-3` explicit out-of-sample evaluation split ·
`D-4` persist and verify the artifact checksum on load · `D-5` production orchestrator emitting
`AnomalyResult` / `MLFinding` (Phase 9/10) · `D-6` artifact persistence and model registry (Phase 10)
· `D-7` LIME cross-check · `D-8` real-company evaluation (unlabeled EDGAR data cannot serve as ground
truth) · `D-9` Phase 13 external benchmark · `D-10` duplicate-period handling test.

### Approval gate

**PHASE 5 DOCUMENTATION CLOSURE COMPLETE — AWAITING USER REVIEW.**
**Next phase after approval: PHASE 6 — BUSINESS DIGITAL TWIN (not started).**

---

## Phase 4 — Quantitative Risk Engine (2026-10-01)

**Status:** Engineering complete — documentation closed. Awaiting approval for Phase 5.
**Scope:** `backend/risk_engine/` (deterministic, LLM-independent) plus the Stage 5 Phase 3→Phase 4 input adapter.

Phase 4 was delivered in three chronological steps, recorded separately below.

### 4A — Engine implementation + Category A audit remediation

**Implemented:** `backend/risk_engine/` — pure-function metric calculators; `registry.py` (40 metrics, frozen anchors, `registry_version = "1.0.0"`); `scoring.py` (piecewise-linear interpolation with clamping, severity bands, dimension/composite aggregation with exact additive contributions); `sensitivity.py` (±20% weight perturbation with re-normalization and Spearman rank stability); immutable Pydantic `contracts.py`; `engine.py` coordinator. Seven risk dimensions; Altman Z/Z′/Z″ with variant auto-selection; Merton DD/PD reference-only.

**Corrected during the audit ("Category A") — each correction is asserted by a named test:** D2/D3 Altman scoring maps linearly to 100 below the distress cut-off and each variant keeps its own cut-offs; D9 an entirely-missing profile no longer fabricates a 50.0 "Moderate" composite (the score is `None`); D10 `DimensionResult.weight` reports the configured weight used alongside the re-normalized `effective_weight`; D11 every metric/dimension/composite output carries `registry_version`; D12 interpolation clamps at the endpoints as well as between anchors.

### 4B — Stage 5 D18–D21 integration (approved)

- **D18 (beta):** removed the degenerate `calc_beta(series, series)` call that forced β = 1.0. `beta` now consumes two distinct typed legs (asset/equity and benchmark) and records both symbols in `inputs_used`; with a single leg it reports `UNAVAILABLE`/`MISSING_INPUT`.
- **D19 (series separation):** added the typed `RiskEngineMarketInputs` contract (`equity_returns`, `benchmark_returns`, `fx_returns`, pre-aggregated macro scalars, provenance). Volatility/VaR/ES read the equity leg, `fx_volatility` reads the FX leg only, beta reads equity + benchmark. Log returns `ln(P_t/P_{t−1})`; beta legs inner-joined on shared dates (no forward fill).
- **D20 (macro inputs):** added `backend/data_engine/{market_inputs,macro_inputs,risk_inputs}.py` so the caller assembles typed inputs outside the engine — the engine imports no fetcher, cache or SQL code (R3 preserved).
- **D21 (weights):** `WeightsRef` added as a carried contract only; persistence and APIs deferred to Phase 10.
- Floors: `MIN_BETA_ALIGNED_OBS = 120`, `MIN_VAR_ES_OBS = 60`, `MIN_VOL_OBS = 30`, `MIN_CPI_MONTHS = 24`, `MIN_FEDFUNDS_MONTHS = 60`. Mixed-currency beta legs raise `ValueError` (Q-B4).
- Tests added: `stage5_helpers.py`, `test_stage5_beta.py` (7), `test_stage5_separation.py` (2), `test_stage5_routing.py` (12), `test_stage5_adapters.py` (6); notebook `notebooks/04_quantitative_risk/02_stage5_market_inputs_validation.ipynb`.
- **Approval state: approved.** Stage 5 changed no formula, anchor, scoring or aggregation rule.

### 4C — Final documentation closure (this entry)

- Corrected `docs/04_quantitative-risk/phase-report.md`: removed the "property-based invariant tests via Hypothesis" claim (Hypothesis is neither installed nor declared — the property suite is deterministic seeded randomization), replaced the "100% formula fixture coverage" wording with 40 fixtures enforced by a registry-walking test (40/40), replaced "Limitations & Deviations: none" with the recorded corrections and ambiguities, and recorded that the golden baselines exist in the working tree but are untracked.
- Recorded the three approved interpretation items: **Q-M1** — the 30-observation volatility floor is retained and the longer-history expectation stays an open specification reconciliation item requiring explicit approval before any change; **Q-M2** — VaR and ES use the company/equity return leg, FX returns are isolated to FX volatility, benchmark returns are used for beta only; **Q-C1** — `margin_gap = Δgross_margin − ΔCPI`, a signed gap. Supporting decisions Q-C2 (24-month CPI and 60-observation FEDFUNDS floors) and Q-B4 (mixed-currency beta legs rejected) are recorded as well.
- Added implementation-status sections to `docs/01_architecture/risk-engine.md` (§11–§13) and `docs/01_architecture/testing.md` (§7); synchronized status in `README.md`, `docs/master-project-specification.md`, `docs/01_architecture/project-overview.md` and `omnirush.md`.
- Evidence at closure: **223 tests passing** (196 pre-Stage-5 baseline + 27 Stage 5); `risk_engine` coverage **94%**; registry coverage **40/40**; contribution reconciliation **5/5** (`abs_tol = 1e-9`); golden profiles 1001–1005 unchanged; Ruff and Ruff-format clean on the code targets (`backend/`, `scripts/` — `ruff check .` additionally reports 19 notebook-cell findings from the intentional `sys.path` bootstrap, recorded as a known condition); Mypy clean (83 files); Phase 4 and Stage 5 notebooks pass fresh-kernel execution; determinism reconfirmed.
- No implementation file, dependency, schema, API, agent, simulation or frontend change was made in this step, and nothing was committed.

### Deferred (recorded, not implemented)

- `AggregationWeights` persistence, weights API and `analyses.weights_id` writes → Phase 10.
- Series-selector UI for choosing benchmark/FX series → Phase 11.
- Everything from Phase 5 onward.

### Approval gate

**PHASE 4 DOCUMENTATION CLOSURE COMPLETE — WAITING FOR USER APPROVAL.**
**Next phase after approval: PHASE 5 — ML ENGINE (not started).**

---

## Phase 3 — Data Engineering (2026-09-29)

**Status:** Complete — approved (Phase 4 was executed after this gate).

### Summary

- Completed source-neutral Phase 3 contracts and typed data-quality findings.
- Preserved the deterministic synthetic generator, canonical fixture seeds 1001–1005 and labelled anomaly injection.
- Added strict all-period validation with error/warning/info severities and the frozen 70% coverage gate.
- Completed calendar-aware period and currency normalization, including debt-schedule FX conversion and missing-flow preservation.
- Added EDGAR (feature-flagged), FRED, World Bank, Stooq and optional Yahoo/yfinance adapters behind typed source-neutral contracts.
- Completed checksum/TTL/atomic offline cache and source-fetch provenance integration.
- Added canonical storage/readback for companies, periods, financials, market series and macro series without changing the Phase 2 schema.
- Added raw feature-frame preparation, reproducible generation/seeding CLIs, fixture-only adapter tests and the Phase 3 profiling notebook.
- Verified 105 tests passing, 90% total coverage, Ruff clean, formatting clean, Mypy clean and notebook execution from a fresh kernel.

### Files and directories added

`backend/data_engine/ingest/base.py` · `edgar.py` · `edgar_map.py` · `fred.py` · `stooq.py` · `world_bank.py` · `yahoo.py` ·
`backend/data_engine/storage.py` · `backend/data_engine/features.py` · `scripts/generate_company.py` · `scripts/seed_db.py` ·
`notebooks/03_data_engineering/synthetic_data_profiling.ipynb` · fixture files under `backend/tests/fixtures/` · Phase 3 test modules.

### Known limitations

- Live external endpoints were not used by normal tests; fixture parsing and explicit unavailable/degraded behavior are tested.
- EDGAR mapping is conservative and does not claim complete US-GAAP coverage.
- Stooq and Yahoo terms remain flagged; downloaded third-party payloads are not committed or redistributed.
- Docker/live PostgreSQL remain unverified locally as carried from Phase 2.
- Phase 3 feature preparation intentionally does not implement Phase 4 risk formulas or Phase 5 ML.

### Approval gate

**PHASE 3 COMPLETE — WAITING FOR USER APPROVAL FOR PHASE 4.**

---

## Phase 2 — Foundation (2026-09-21)

**Status:** Complete — awaiting approval. **First application code.**

Full planning, decisions, test results, and known issues live in
[02_foundation/phase-report.md](02_foundation/phase-report.md) (dedicated per-phase directory;
this log keeps summary entries only from Phase 2 onward).

### Summary

- Repository skeleton + root config (`pyproject.toml`, `.gitignore`, `.env.example`, `LICENSE`,
  `docker-compose.yml`, `Dockerfile`, `alembic.ini`, `requirements-lock.txt`).
- Backend foundation: `core/config.py` (frozen env contract), `core/errors.py` (frozen envelope),
  `app/logging.py` (structlog JSON + run correlation), `database/session.py`, `database/models.py`
  (9 core tables per frozen `docs/01_architecture/database.md` §6), `app/main.py` (app factory + `/api/v1/health`),
  Alembic env + migration `0001_core_tables`.
- Tests (23 passing): config/errors/logging/architecture-R3 units; models/API/migrations integration;
  Alembic upgrade↔downgrade↔schema-match roundtrip.
- Toolchain: ruff + ruff format clean; mypy clean (21 files, pydantic plugin); alembic CLI roundtrip
  verified; live uvicorn boot smoke passed.
- Environment: Python 3.12.10 installed (machine had only 3.10); Docker unavailable locally — compose
  files written but not booted (see notes §5).

### Files created

`pyproject.toml` · `.gitignore` · `.env.example` · `LICENSE` · `docker-compose.yml` · `Dockerfile` ·
`alembic.ini` · `requirements-lock.txt` · `backend/core/{config,errors}.py` ·
`backend/app/{main,logging}.py` · `backend/app/api/deps.py` · `backend/database/{session,models}.py` ·
`backend/database/migrations/{env.py,script.py.mako,versions/0001_core_tables.py}` ·
`backend/tests/conftest.py` · `backend/tests/unit/{test_config,test_errors,test_logging,test_architecture_imports}.py` ·
`backend/tests/integration/{test_models,test_api_health,test_migrations}.py` ·
`docs/02_foundation/phase-report.md`

### Files modified

`README.md` (status + roadmap rows) · `docs/development-log.md` (this entry)

### Open questions carried to Phase 3

1. Boot the compose stack on a Docker-capable machine (or CI) to verify Postgres-path behavior.
2. Commodity series decision (FRED WTI vs Stooq symbol) — now due with generator work.

---

## Phase 1 — Architecture Freeze (2026-09-21)

**Status:** Complete — awaiting approval. **No application code exists.**

### What was done

All architecture contracts frozen as documentation (10 new docs), implementing spec §36 Phase 1:

1. `docs/01_architecture/project-overview.md` — stable overview + hard rules R1–R7 + document map.
2. `docs/01_architecture/architecture.md` — 3-container topology; layer/import rules (R3 enforced by an architecture
   test); run lifecycle & states; **LLM abstraction frozen** (provider table; GLM via OpenAI-compatible
   adapter, default model `glm-5.3-flash`); frozen env-var names; error/degradation semantics.
3. `docs/01_architecture/agents.md` — **RiskState schema frozen** (field-by-field); graph topology with control limits
   (≤1 replan, ≤6 tool calls/agent, 30s/120s/run-timeout, token budget); agent output JSON contracts;
   **15-tool registry + per-agent permission matrix**; LLM call policy (temperature 0 structured /
   ≤0.3 narrative); numeric-verification algorithm (tolerances frozen); degraded modes.
4. `docs/01_architecture/data.md` — canonical wide financials schema (exact field names); source contracts with
   throttles/cache TTLs/license tags (EDGAR ≤10 req/s hard-capped at 8, FRED ≥1s, Stooq ≥2s, Yahoo ≥5s);
   validation rules incl. 70% coverage gate; synthetic generator spec; **frozen decisions FD-1
   (currency: INR default, configurable), FD-2 (EDGAR import in Phase 3, feature-flagged), FD-3
   (AI-translated scenarios always require confirmation)** — resolves Phase 0 open questions 5, 6, 8.
5. `docs/01_architecture/risk-engine.md` — **formula registry frozen**: 7 dimensions, every formula with definition,
   edge cases, exact piecewise-linear band anchors; equal default weights; ±20% sensitivity method;
   severity labels; rounding & `registry_version` rules; Altman Z variant auto-selection; Merton
   listed-mode optional; Phase 4 validation requirements.
6. `docs/01_architecture/simulation.md` — twin parameter table ([R]/[A]/[S] with defaults); monthly recursion frozen
   (supply-cap revenue channel, FX/commodity pass-through with pass-through capacity, revolver draws
   with **negative cash allowed + funding-gap breach**, no loss carryforward); scenario schema bounds
   and clamp/reject rule (≤1.25× of bound); 8 presets with exact values; stress outputs (KPI table,
   breach thresholds, EBITDA waterfall order, dimension re-scoring); 6 invariants.
7. `docs/01_architecture/api.md` — endpoint-by-endpoint JSON contracts; stable error-code table; **SSE event contract**
   (7 event types, Last-Event-ID replay); job lifecycle incl. cooperative cancel.
8. `docs/01_architecture/database.md` — DDL-level schema; **PK conventions: UUID entities, BIGINT identity logs**;
   UTC timestamptz; JSONB payloads validated by Pydantic at the boundary; migration plan per phase.
9. `docs/01_architecture/requirements.md` — FR1–FR14 / NFR1–NFR10 with priorities (MoSCoW), phases, acceptance criteria.
10. `docs/01_architecture/testing.md` — test pyramid; fixture seeds 1001–1005 (regenerated, no binaries); FakeChatModel
    + recorded transcripts + `RUN_LIVE_SMOKE` flag; golden-file regeneration policy; coverage targets;
    CI plan (Phase 12).

### Files created (10)

`docs/01_architecture/project-overview.md`, `docs/01_architecture/architecture.md`, `docs/01_architecture/agents.md`, `docs/01_architecture/data.md`,
`docs/01_architecture/risk-engine.md`, `docs/01_architecture/simulation.md`, `docs/01_architecture/api.md`, `docs/01_architecture/database.md`,
`docs/01_architecture/requirements.md`, `docs/01_architecture/testing.md`

### Files modified (3)

- `README.md` — status banner + roadmap rows (Phase 0 → Approved; Phase 1 → Complete — awaiting approval).
- `docs/master-project-specification.md` — status line: Phase 0 approved, contracts frozen in Phase 1 docs.
- `docs/development-log.md` — this entry.

### Decisions taken (beyond Phase 0's D1–D7)

| # | Decision | Rationale |
|---|---|---|
| F1 | Single-process background jobs (no Celery/Redis); queue-swappable job interface | two fewer moving parts; run = single-user interactive workflow |
| F2 | In-memory graph checkpointer; restart = fresh run | cross-restart resume adds complexity without demo value; full artifacts persist anyway |
| F3 | Piecewise-linear scoring between frozen anchors (clamped) | smooth, monotone, testable; avoids arbitrary step boundaries |
| F4 | Scenario deltas are step changes at t=1; optional `ramp_months` (default 0) | conservative stress default; flexibility preserved |
| F5 | Cash may go negative only via capped revolver draws; beyond cap = `funding_gap` hard breach | more informative than clamping; breaches never hidden |
| F6 | SQLite for tests, Postgres for dev/demo; UUID entity PKs, BIGINT log PKs | pragmatic testing; right key semantics per table class |
| F7 | Golden files regenerated only via reviewed `--regen-golden` with version bump | prevents silent drift of numeric baselines |
| F8 | Temperature 0 for structured LLM steps, ≤0.3 narrative; structured-output mode where supported | reproducibility of structured flow |
| F9 | FD-1/2/3 (above) | resolve carried open questions |

### Tests run in this phase

None — documentation phase (no code exists). Documentation consistency checks performed (see phase
report): file inventory, spec section completeness, cross-document terminology and cross-references.

### Open questions carried to Phase 2

1. Exact version pins in `pyproject.toml` (Python minor, package versions) — Phase 2.
2. Commodity price series choice (FRED WTI series vs Stooq commodity symbol) — Phase 3 prep, decide
   with the generator/injest work; FRED `DCOILWTTI` remains unverified (research doc).
3. GLM API key provisioning + official pricing verification — Phase 2 config step.
4. LICENSE file addition (MIT proposed) — Phase 2.
5. Sector GDP-elasticity defaults (manufacturing 1.2 / retail 1.0 / services 0.8) are assumptions —
   revisit during Phase 3 calibration notes.

---

## Phase 0 — Research + Master Specification (2026-09-21)

**Status:** Complete — awaiting approval. **No application code exists.**

### What was done

1. **Source-verified research** (all URLs accessed 2026-09-21; recorded in
   [phase-0-research.md](00_research/phase-0-research.md)):
   - ERM practice: ISO 31000:2018; COSO ERM 2017 (5 components / 20 principles).
   - Commercial landscape: MetricStream, ServiceNow IRM, Archer, LogicGate; Bloomberg Terminal,
     FactSet, S&P Capital IQ Pro, Moody's; Power BI/Tableau/Looker; credit methodology (Altman Z
     coefficients/zones verified; Merton DD/PD verified).
   - Regulatory stress testing: BCBS “Stress testing principles” (Oct 2018, BIS d450); Fed DFAST/CCAR
     (incl. verified 2025 severely-adverse scenario characteristics).
   - Literature verified: LangGraph (MIT, v1.2.11 on PyPI 2026-08-11), AutoGen (+AG2), CAMEL (correct
     title; ChatDev is a different paper), MetaGPT (ICLR 2024 Oral), Guo et al. survey (IJCAI 2024),
     FinRobot, FinGPT, BloombergGPT, SHAP/TreeSHAP, LIME, Breiman permutation importance, Wachter
     counterfactuals, Isolation Forest (ICDM 2008), Tao et al. digital-twin survey, SDV (**BSL, not
     MIT**), Langfuse (**MIT except `ee/`**).
   - Data sources verified source-vs-access: SEC EDGAR (keyless, User-Agent required, **10 req/s**,
     public domain, XBRL 2009+), FRED (official API + free key, attribution required; FEDFUNDS /
     CPIAUCSL / GDPC1 / UNRATE / DEXINUS verified live; DCOILWTTI unverified), Stooq (CSV, “personal
     use only” footer, no published license — flagged), Yahoo Finance vs `yfinance` (unofficial
     Apache-2.0 library; Yahoo ToS restricts automated collection; 429 throttling 2024–26), World Bank
     (official API, CC BY 4.0, indicators verified).
   - LLM provider verified: Z.ai/BigModel GLM API is OpenAI-compatible
     (`open.bigmodel.cn/api/paas/v4`, `api.z.ai/api/paas/v4`); **GLM-5.3-Flash confirmed** (announced
     2026-08-26; open weights on Hugging Face; ~320B/18B-active MoE, ~1M context).
2. **Master specification written** ([master-project-specification.md](master-project-specification.md)):
   41 sections — problem, users, gap, RQs/hypotheses/objectives, scope, modules, multi-agent
   architecture + StateGraph, quant engine registry, focused ML strategy, digital twin equations,
   scenario engine (bounded schema), stress testing, layered explainability, mitigation, 13
   guardrails, data strategy, evaluation + baselines B1–B4, security, observability, DB/API/frontend
   design, folder structure, file-by-file plan, tech stack, Phase 0–14 roadmap, DoD, risks, research
   opportunities, B.Tech documentation + viva plans.
3. **README.md** created as the entry point (status: documentation only).

### Files created (exactly four, per phase control)

- `README.md`
- `docs/00_research/phase-0-research.md`
- `docs/master-project-specification.md`
- `docs/development-log.md`

### Decisions taken

| # | Decision | Rationale |
|---|---|---|
| D1 | GLM-5.3-Flash as temporary dev model behind provider-agnostic adapters; deterministic math LLM-independent | user-approved; verified OpenAI-compatible endpoints; avoids vendor lock-in |
| D2 | Hybrid data: synthetic generator core + FRED/World Bank macro + Stooq/yfinance market (cached, terms-flagged) + optional EDGAR | licensing safety, reproducibility, controllable stress inputs |
| D3 | Frontend: React + Vite + TS, ECharts/Recharts, GSAP + ScrollTrigger, Motion, UI-UX-Pro-Max/Taste/GSAP skills | user-approved premium dashboard |
| D4 | Focused ML: Isolation Forest + SHAP + z-score baseline, retained only if it beats the baseline | user-approved; honest falsifiability |
| D5 | Roadmap frozen as Phase 0–14 (15 phases) with per-phase approval gates | user correction applied |
| D6 | Scoring: threshold bands → 0–100, equal default weights, ±20% sensitivity reporting | transparency; avoids fake “calibration” claims |
| D7 | Numeric verification guardrail: every LLM-emitted number machine-checked against engine outputs | core research contribution (RQ1/H1) |

### Open questions (carried to Phase 1 / later)

1. FRED `DCOILWTTI` (WTI) existence, or a Stooq commodity symbol — resolve in Phase 3.
2. Stooq full Terms of Service text + per-symbol history depth — Phase 3.
3. Official Z.ai pricing page for GLM-5.3-Flash — Phase 2 (when key is configured).
4. License choice (proposed MIT) — decide in Phase 2.
5. Default synthetic currency (proposed ₹ INR default, configurable; EDGAR imports USD) — confirm in
   Phase 1.
6. EDGAR real-filings import: in MVP (Phase 3) or deferred — decide in Phase 1.
7. SHAP × IsolationForest integration spike — Phase 5 (fallback documented).
8. Confirmation UX scope: AI-translated scenarios always require user confirmation before a run;
   whether form-based scenarios also need an explicit confirm step — decide in Phase 1.

### Tests run in this phase

None — Phase 0 produces no code (per phase control). Documentation only.

---
