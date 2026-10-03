# Phase 8 — Stress Testing & Impact Analysis Completion Report

**Status:** Engineering complete — awaiting user review before commit/push.
**Scope:** `backend/simulation/stress.py` (baseline-vs-stressed comparison,
KPI deltas, frozen breach policy, EBITDA waterfall + below-EBITDA bridge) and
`backend/simulation/sensitivity.py` (single-factor sweeps), plus unit,
property and golden tests and a validation notebook. Implementing the frozen
`docs/01_architecture/simulation.md` §5 outputs and §6 invariants.
**Upstream (read-only):** Phase 6 `simulate()` / `SimulationRunResult` /
`assumption_records`; Phase 7 `scenarios.py` (`validate_params`, `confirm`,
`to_overrides`, `FIELD_BOUNDS`, `SHOCK_FIELDS`, `list_presets`);
`backend/core/errors.py`.

---

## 1. What was built

| Element | Responsibility |
|---|---|
| `STRESS_VERSION = "1.0.0"` | Single Phase 8 scope: comparison + breach + waterfall + sensitivity (decision A) |
| `run_stress()` | Baseline (zero overrides) vs stressed (`to_overrides`) on the same deterministic `simulate()` path (decision B); refusal if either run's invariants fail |
| `compare_kpis()` | Frozen §5 KPI rows at trough and end-horizon, in frozen order; Δ absolute + Δ % with a *reason* when undefined (decision D) |
| `detect_breaches()` | Frozen §5 policy with defaults (runway 6.0, DSCR 1.2, coverage 1.5) and per-run `BreachPolicy` overrides; month-by-month periods; status/records only, no severity labels (decision E) |
| `attribute_waterfall()` | Frozen §5 order; monthly-then-sum `(Rev_s−Rev_b)·GM_b` revenue effect, input-cost, opex, other/one-off; below-EBITDA bridge interest → tax |
| `resolve_min_cash_buffer()` | Reads `B` from the run's own `assumption_records`; missing record is an internal error, never a silent 0.0 |
| `sensitivity.py` | `SWEEPABLE_FIELDS` (nine bounded shock fields), `SWEEP_POINTS = 9`, `MAX_SWEEP_RUNS = 10`, OFAT sweep from the zero-shock base, `breach_onset` |
| `_closure_ok` / `_hash_result` | Frozen 0.5% closure with an absolute floor; SHA-256 over canonical JSON (decision I) |

The frozen `docs/01_architecture/simulation.md` was **not amended**: the §5
output list and every §6 invariant stand as written. Two clearly-marked
implementation-status notes (Phase 8 delivered; D-6-3 recorded, not resolved)
were appended *after* the frozen text, following the `testing.md` §7 recorded
status precedent. No Phase 4/5/6/7 file, formula, anchor, scoring rule or
golden fixture was touched.

## 2. Locked Phase 8 decisions as implemented

| ID | Decision | Implementation |
|---|---|---|
| A | `STRESS_VERSION = "1.0.0"`, one scope | Module constant; stamped on `StressTestResult` / `SensitivityResult` |
| B | One deterministic path for both runs | `simulate()` twice: zero overrides vs `to_overrides(validated)` |
| C | Scenario horizon is the execution horizon | `_resolve_horizon`; a mismatching `horizon_override` is rejected |
| D | Undefined Δ % is `None` **with a reason** | `_pct_change` → `zero_baseline` / `unavailable_input` / `nonfinite_result` |
| E | Breach output is status/records only | `status ∈ {breached, not_breached, unevaluable}`; month lists; no severity levels |
| F | Frozen listing order, never alphabetical | `KPI_ORDER`, `BREACH_ORDER`, `WATERFALL_ORDER`, `BRIDGE_ORDER` asserted in tests |
| G | 9 inclusive-endpoint grid points + baseline | `_sweep_grid` over `FIELD_BOUNDS`; `0.0` unioned in and flagged `is_baseline_point` |
| I | SHA-256 over canonical JSON | `result_hash` (64 hex) over the result minus the hash itself; golden-pinned |
| L | No `backend/guardrails/` package | Breach logic lives in `stress.py`; package still absent (verified) |

Letters of the addendum with no Phase 8 code footprint (no new bound, no new
guardrail rule naming, no new version surface) were not forced into code to
create one; nothing was invented to satisfy a letter.

## 3. Explicit blockers, reported not hidden

1. **B1 — current-ratio proxy is `unevaluable`.** The twin projects AR /
   inventory / AP *flows* but no `current_assets` / `current_liabilities`
   *levels* (frozen §2 defines no balance-sheet recursion, decision D-4), and
   the frozen spec defines no proxy formula. Inventing one would be new
   financial methodology, so the rule is emitted as `unevaluable` with a
   machine-readable reason and stays documented as deferred.
2. **B2 — dimension deltas are deferred (D-6-7).** Re-scoring the stressed
   end-state needs a full `CompanyDataset` (equity, total assets, current
   balances) that the twin never projects. `dimension_deltas` is `None` with a
   note listing the missing projected fields; no projected balance sheet is
   fabricated.
3. **D-6-3 — the frozen §6.3 trough-cash monotonicity claim does not hold** on
   the twin. A revenue contraction on seed 1002 releases working capital, so
   trough cash *rises* while EBITDA and DSCR fall. The sweep module therefore
   *reports* the response curve and never asserts a direction of travel; the
   finding is pinned by `test_d63_trough_cash_not_monotone_documented` and by
   the golden's `sensitivity` block. Amending the frozen invariant still
   requires change control.

## 4. Verification

| Check | Result |
|---|---|
| Baseline before implementation | 444 passed (clean tree, HEAD ec5b6aa) |
| New tests | 54 (32 unit + 3 property + 19 golden cases over 7 golden tests) |
| Full suite after | **498 passed** (498 collected, 0 failed, 0 skipped) |
| `stress.py` coverage | **97%** (229 statements, 8 missed — all defensive refusal/validation branches) |
| `sensitivity.py` coverage | **97%** (72 statements, 2 missed — both twin-invariant refusal branches) |
| `simulation` package | 97–100% (unchanged elsewhere; above the ≥80% NFR3 floor) |
| Phase 4/5/6/7 suites | green; Phase 4 `seed_100*.json`, Phase 5 ML golden and Phase 6 `twin_seed_*.json` byte-identical |
| Ruff / Ruff-format / Mypy | clean; 119 files formatted; mypy clean over 115 source files |
| Import cycles (Graphify `graph.json`) | 0 strongly-connected import components over 1,318 `imports`/`imports_from` edges (2056 nodes, 5751 links) |
| Golden policy | `stress_seed_1001..1005.json` are **new** files, regenerated only via `pytest --regen-golden`, gated on `STRESS_VERSION` |
| Notebook fresh-kernel | `notebooks/08_stress_testing/01_stress_validation.ipynb` — 17 cells (8 code), **0 error outputs**; D-6-3 asserted, waterfall closure exact, hand-check residual 0.000e+00, capacity-ceiling saturation pinned |
| Determinism (R6) | byte-identical repeated runs asserted for every fuzzed scenario and sweep; `result_hash` equality asserted |
| R3 (no I/O / network / DB / LLM) | holds — imports are contracts, `scenarios`, `stress`, `twin`, `core.errors`, pydantic and stdlib only |
| Dependencies | zero new (`pyproject.toml`, `requirements-lock.txt` untouched) |

## 5. Deferred (recorded, not implemented)

- D-6-3 trough-cash monotonicity resolution (change control).
- D-6-4 annual→monthly conversion for real filings (Phase 3).
- D-6-7 dimension deltas via Phase 4 re-scoring of a projected end-state.
- D-6-8 equity / balance-sheet roll-forward; reverse stress testing.
- Live scenario translation, prompts and transcripts (Phase 9).
- Persistence of custom breach policies, services and API (Phase 10).

## 6. Known limitations

1. The current-ratio proxy breach rule cannot be evaluated (B1) and reports
   `unevaluable`; consumers must not read that as "healthy".
2. Per-dimension risk deltas are unavailable (B2); the waterfall explains the
   *financial* effect, not the risk-score effect.
3. Custom `BreachPolicy` thresholds are per-call only; nothing is persisted.
4. Sweeps are one-factor-at-a-time from the zero-shock base by frozen design;
   they do not measure interaction effects (the scenario run does that).
5. The sweep grid spans the frozen §3 bounds, so it is a global range, not a
   local derivative around the scenario's own values.
6. `one_off_cost` is not sweepable (unbounded, Phase 7 decision K) and never
   receives a ΔEBITDA attribution (frozen §2: cash-flow-only).
7. Synthetic-only validation; not a forecast, not financial advice.
8. **Capacity-ceiling saturation:** on a company already running at its
   trailing-max revenue capacity (e.g. seed 1001, every baseline month capped),
   positive `revenue_change_pct` shocks raise demand but leave revenue — and
   therefore every KPI — identical to baseline; on partially-capped seeds the
   upside responds initially and then plateaus. This is frozen twin behaviour
   (§1 `revenue_capacity`, §2 `revenue = min(demand, capacity)`), surfaced and
   pinned by the sweep rather than hidden; downside shocks are unaffected.

## 7. Out of scope

Reverse stress testing · stochastic simulation · optimization / mitigation
search · dimension re-scoring · agents/LLM · API/persistence/Streamlit ·
notebook-only claims beyond what the notebook executes · new dependencies ·
any change to frozen specs or to Phase 4/5/6/7 code and goldens.

## 8. Phase 8 boundary

Phase 8 ends here. Agents, LLM wiring, API, database and frontend were
**not** started. `stress.py`/`sensitivity.py` are programmatic subsystems with
no production entry point — the same state the twin and the scenario engine
were in at their closures, and for the same architectural reason (R3).

---

**PHASE 8 IMPLEMENTATION COMPLETE — AWAITING USER REVIEW BEFORE COMMIT/PUSH.**
**Next phase after approval: PHASE 9 — MULTI-AGENT LANGGRAPH (not started).**

