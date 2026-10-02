# Phase 6 — Business Digital Twin Completion Report

**Status:** Engineering complete — documentation closed. Awaiting approval for Phase 7.
**Scope:** `backend/simulation/` — a deterministic, LLM-independent monthly financial
recursion for one company (frozen master spec §19; `docs/01_architecture/simulation.md`
§1–§2), plus the Phase 6 validation notebook and twin trajectory goldens.
**Upstream:** Phase 3 canonical periods and Phase 4 metric calculators, consumed read-only.

---

## 1. What was built

`backend/simulation/` — three modules, matching the frozen module table in the master
specification (`assumptions.py` and `twin.py` for Phase 6; `scenarios.py`, `stress.py`
and `sensitivity.py` belong to Phases 7 and 8 and were **not** created).

| File | Responsibility |
|---|---|
| `contracts.py` | Typed contracts for assumptions, overrides, initial state, per-month output, invariants, diagnostics, summary and provenance. `TWIN_VERSION = "1.0.0"`. |
| `assumptions.py` | Derives the frozen §1 parameter table from a trailing 12-month window; records every derivation and every fallback. |
| `twin.py` | The frozen §2 monthly recursion, the per-month `MonthLedger`, Phase 4 ratio wiring, the six invariant checks and `run_twin` / `simulate`. |

The frozen `docs/01_architecture/simulation.md` is the implementation authority. It was
**not modified** by this phase.

## 2. Divergence from the planning prompt (decision D-0, approved)

The planning prompt carried a simplified equation set. The frozen §2 additionally specifies
a supply ceiling `Capacity0`, an FX demand-elasticity term, commodity and FX cost legs
damped by `(1 - ptc)`, a split floating/fixed interest basis, revolver draws against a
minimum-cash buffer, and an explicit `funding_gap` breach. **The frozen version is
implemented verbatim.** Adopting the prompt's subset would have silently deleted the
FX/commodity channels the project advertises as a research contribution in `README.md`
and would have removed the only mechanism that makes cash well-defined under stress.

All seven differences are itemised in §3 and are visible in `backend/simulation/twin.py`'s
module docstring.

## 3. Frozen equations as implemented

```text
Demand:   Rev_dem_t = Rev_{t-1}·(1+g)^(1/12)·(1+δ_rev,t)·(1 − δ_fx,t·ρ_rev·e_fx)
Supply:   Rev_sup_t = Capacity₀·(1 − δ_supplier,t)          # trailing 12-mo max revenue
Revenue:  Rev_t     = min(Rev_dem_t, Rev_sup_t)
COGS:     COGS_t    = Rev_t·c₀·(1 + δ_comm,t·κ_c·(1−ptc))·(1 + δ_fx,t·κ_fx·(1−ptc))·(1 + δ_cogs,t)
GP:       GP_t      = Rev_t − COGS_t
Opex:     Opex_t    = (F + v·Rev_t)·(1 + δ_opex,t)
EBITDA:   EBITDA_t  = GP_t − Opex_t ;  EBIT_t = EBITDA_t − DA
Interest: Interest_t = (r₀+δ_rate,t)/12·D_{t-1}·φ + r₀/12·D_{t-1}·(1−φ)
EBT/Tax:  EBT_t = EBIT_t − Interest_t ; Tax_t = max(0, EBT_t)·τ ; NI_t = EBT_t − Tax_t
NWC:      AR_t = Rev_t·(DSO+δ_ar)/30 ; Inv_t = COGS_t·DIO/30 ; AP_t = COGS_t·DPO/30
          ΔNWC_t = (AR+Inv−AP)_t − (AR+Inv−AP)_{t−1}
Cash flow: OCF_t = NI_t + DA − ΔNWC_t
           CF_t  = OCF_t − Capex₀·(1+δ_capex,t) − principal_t + draws_t − one_off_cost·1[t=1]
Cash:     Cash_t = Cash_{t-1} + CF_t          # may go negative — never clamped
Debt:     D_t = D_{t-1} − principal_t + draws_t
```

Two implementation notes that are not visible in the equations themselves:

* **`g` is applied monthly.** `g` is an annual figure; the recursion uses
  `(1+g)^(1/12)`, so a 12% annual rate compounds correctly over 12 months.
* **Scenario deltas compound.** The frozen equation applies δ to the *previous*
  month's revenue, so a persistent −20% shock gives 800 → 640 → 512 … A "step" in §2
  means the delta is fully applied from t = 1, not that revenue stays frozen. This is
  pinned by tests and is easy to misread.

## 4. Decisions taken (all ratified from the Phase 6 plan)

| ID | Decision | Rationale |
|---|---|---|
| **D-0** | Implement the frozen §2 equations, not the prompt's simplified set | §2 is the authority; the prompt itself defers to the repository. |
| **D-1** | Monthly history only; annual/quarterly sources are refused | `edgar.py` yields ANNUAL/QUARTERLY only, and `normalize/periods.py` aggregates *upward* only — no monthlyizer exists. Inventing one would fabricate inputs. Raised as `InsufficientHistoryError` (status `insufficient_history`) after 12 months; shorter windows cannot honour the trailing-12-month derivations. |
| **D-2** | Month-end date grid, advancing to the next month end | Matches `PeriodFinancials`. Leap years fall out of date arithmetic. |
| **D-3** | Default horizon 12 months, maximum 36 | The maximum is frozen (§1); 12 matches the Phase 7 scenario schema default, which is the only place the number 12 appears. |
| **D-4** | Income-statement + cash-flow projection only; no equity or balance-sheet roll-forward | §2 defines no recursion for `equity`/`total_assets`. `Assets = Liabilities + Equity` is therefore an **input** property, gated by `data_engine.validate.identities` before the run, exactly as the spec frames it ("holds on generated data"). |
| **D-5** | Added `contracts.py` beyond the frozen file table | The frozen table lists only `assumptions.py` and `twin.py`, but `data_engine`, `risk_engine` and `ml_engine` all have a `contracts.py`. Consistent with 3/3 precedent; additive and documented. |
| **D-6** | Accept `one_off_cost` and `ramp_months` as typed overrides with **no** bounds policy | They appear in the frozen §2 cash equation but are Phase 7 schema fields. Phase 6 applies them as given; clamp/reject belongs to Phase 7. |
| **D-7** | No rounding anywhere in the engine; 1e-6 relative for the cash identity, 1e-9 elsewhere | Matches §6.1 and the existing golden tolerance. |
| **D-8** | `ptc = 0.3` re-declared, not imported | `risk_engine/metrics/market.py` L65/L91 really do default `pass_through` to 0.3. Importing it would couple twin assumptions to a Phase 4 metric signature; a test asserts the two stay in sync instead. |
| **D-9** | `docs/06_digital_twin/` | Matches the most recent phase (`docs/05_ml_engine/`). |
| **D-10** | A separate `SimulationStatus` enum | `risk_engine.MetricStatus` is frozen Phase 4 vocabulary and has no name for `funding_gap` or `insufficient_history`. A separate enum leaves Phase 4 untouched. |

## 5. Phase 4 integration — reuse without modification

`risk_engine` received **zero** changes. Three frozen Phase 4 calculators are reused
directly by adapting one simulated month to their existing field names:

| Twin output | Reused calculator | Why it fits |
|---|---|---|
| `interest_coverage_t` | `calc_interest_coverage` | Needs exactly `ebit` and `interest_expense`, both of which the twin produces. A perfect fit. |
| `runway_t` | `calc_cash_runway_months` | Needs `cash` and `ocf`, both produced; the twin passes prior months as `history`. Handles the positive-OCF case itself. |
| `DSCR_t` | `calc_dscr` | Needs `ebitda`, `interest_expense` and `st_debt`. §2 never projects a short-term balance, so the month's **actual scheduled principal** is supplied as `st_debt`. The result is the standard monthly debt service coverage ratio, `EBITDA / (interest + principal)`, and the frozen formula's zero-denominator branches are reused unchanged. This mapping is documented in `_calculator_inputs` and is the one place where a semantic substitution occurs; it is deliberate and does not modify Phase 4. |

No score, band, anchor, weight, the composite, or the registry is touched. Phase 8 re-scores
the projected end-state through the existing engine for dimension deltas (§5 of
simulation.md); the twin scores nothing.

## 6. What the twin deliberately does **not** do

Phase 6 is the twin only. Explicitly not implemented and not started:

* **Scenario Engine (Phase 7):** bounded JSON schema, the 8 presets, out-of-range
  clamp/reject with `guardrail_events`, natural-language translation, human confirmation,
  and `scenarios.py` itself. Phase 6 accepts already-structured typed deltas and applies
  them without policy.
* **Stress Testing (Phase 8):** baseline-vs-stressed comparison, KPI deltas, breach
  thresholds, the EBITDA waterfall, single-factor sweeps, `stress.py` and `sensitivity.py`.
* **Nothing from Phase 9/10+:** no agents, no LangGraph, no API routes, no database
  persistence, no frontend.
* **No Monte Carlo, no stochastic process, no LLM call.** The twin is a pure function of
  its inputs; it has no seed because it has no random component.

`SimulationSummary` reports *conditions* (`breached_buffer`, `had_funding_gap`,
`funding_gap_months`, `revenue_capped_months`). Turning a condition into a reportable
breach, against a threshold, is Phase 8's policy decision and was not made here.

## 7. Honest findings — three things that did not go as expected

These are reported rather than smoothed over, in the spirit of the Phase 5 report.

### 7.1 A revenue shock can *raise* trough cash (frozen §6.3 does not hold as written)

`simulation.md` §6.3 asserts that single-factor sweeps move "trough cash and EBITDA
monotonically in the expected direction". **EBITDA does; trough cash does not.** Measured on
canonical seed 1002 with a −30% monthly revenue shock:

| Quantity | Baseline | Stressed |
|---|---|---|
| min cash | 14,107,653 | **19,533,795** (higher) |
| min DSCR | 0.597 | 0.022 (lower) |
| min interest coverage | 3.36 | 0.85 (lower) |
| lowest EBITDA | higher | lower |

The mechanism is the frozen equation itself: `OCF_t = NI_t + DA_t − ΔNWC_t`. As the business
contracts, receivables and inventory are collected faster than profit falls, so `ΔNWC` is
strongly negative (≈ −4.5M in month 1) and operating cash flow stays positive even while net
income turns negative from month 2. A shrinking business genuinely releases working capital.

This is economically coherent, not a defect, and it is pinned by
`test_a_shrinking_business_releases_working_capital`. It is recorded as deferred item
**D-6-3**: §6.3 should either be scoped to EBITDA and coverage ratios, or amended to state
that a *contraction* shock releases working capital. **It is not resolved here**, because
changing a frozen invariant requires the change-control procedure, not a coding decision.

### 7.2 `st_debt` has no monthly counterpart (the one Phase 4 substitution)

Covered in §5. `calc_dscr` is a historical-period metric; §2 has no short-term balance. The
substitution is documented at the call site and the resulting ratio is the standard monthly
debt-service-coverage definition. Flagged because it is the only place the twin feeds a
Phase 4 formula something other than what that formula was written for.

### 7.3 Annual/quarterly companies cannot use the twin yet (D-1)

`edgar.py` produces `ANNUAL` (10-K) or `QUARTERLY` (10-Q) periods; `normalize/periods.py`
aggregates sub-periods *upward* only. There is no annual→monthly decomposer anywhere in the
repository. The twin therefore requires ≥ 12 monthly periods and raises
`InsufficientHistoryError` otherwise. This is a real limitation on real-company use and the
correct home for the fix is Phase 3, not Phase 6 — inventing a decomposer here would have
been silent fabrication.

## 8. Implemented

* Deterministic monthly recursion implementing frozen §2 verbatim, in frozen equation order.
* All 18 frozen §1 parameters derived from a trailing 12-month window, with each derivation
  and each documented fallback recorded as a typed `AssumptionRecord`.
* Horizon bounded to 1..36, default 12, rejected outside.
* Six invariant checks computed from the *emitted* months (not the engine's internal
  variables): cash identity (1e-6 relative, frozen), debt roll-forward, NWC continuity,
  non-negative tax, "negative cash only via a funding gap", bounded horizon.
* Explicit missing-input behaviour: nothing is zero-filled, interpolated or forward-filled.
  A missing required series raises with the offending period named.
* Per-month Phase 4 ratios (DSCR, interest coverage, cash runway) with status semantics
  preserved, and trough/end-horizon summary values shaped for Phase 8 differencing.
* Provenance: `twin_version`, the Phase 4 `registry_version`, generator seeds, horizon,
  baseline flag, source period count.
* Frozen disclaimers on every run result: assumption-based intervention, not causal truth;
  not financial advice.
* The month-end date grid, including leap years and the December→January transition.
* Golden twin trajectories for the canonical seeds 1001–1005 in **new** files
  `twin_seed_*.json`, generated only via `pytest --regen-golden` and gated on `TWIN_VERSION`.
* Validation notebook: 27 cells (13 code), executes from a fresh kernel with **0 error
  outputs**, including a full hand-calculated month 1 that agrees with the engine to a worst
  relative residual of **1.7e-16**.

## 9. Verification

| Check | Result |
|---|---|
| `pytest backend/tests -q` | **388 passed** (270 before Phase 6 → +118) |
| `simulation` coverage | `contracts.py` 98% · `assumptions.py` 98% · `twin.py` 97% · `__init__.py` 100% — above the ≥80% NFR3 floor and above the 94–99% band of Phases 4/5 |
| `risk_engine` coverage | `scoring.py` 94% · `registry.py` 95% · `engine.py` 98% — **unchanged** |
| `ml_engine` coverage | `features.py` 97% — **unchanged** |
| `ruff check backend scripts` | All checks passed |
| `ruff format --check backend scripts` | 109 files already formatted |
| `mypy backend` | Success: no issues found in 105 source files |
| Phase 4 goldens `seed_1001..1005.json` | **byte-identical**, `git diff HEAD` empty |
| Phase 5 golden `ml_anomaly_golden.json` | **unchanged** |
| Phase 2/3/4/5 source | **unchanged**, `git diff HEAD` empty for `risk_engine`, `data_engine`, `database`, `app`, `core`, `ml_engine` |
| `pyproject.toml`, `requirements-lock.txt` | **unchanged** — no new dependency |
| R3 architecture test | Already lists `simulation`; passes with no edit |
| Notebook, fresh kernel | 27 cells, 13 code, **0 error outputs** |
| Golden regeneration | Only via `--regen-golden`; twin version gate in place |

New dependency count: **zero**. The twin needs only `pydantic`, the standard library and the
already-declared `numpy`/`pandas`.

## 10. Deferred (recorded, not implemented)

* **D-6-3** — frozen §6.3 trough-cash monotonicity does not hold for contraction shocks
  (§7.1). Needs an explicit decision: scope the invariant to EBITDA and coverage ratios, or
  amend it to acknowledge working-capital release. **Requires user approval; a frozen
  invariant may not be changed unilaterally.**
* **D-6-4** — annual→quarterly→monthly conversion for real EDGAR companies. Belongs in
  Phase 3, not here (§7.3).
* **D-6-5** — `scenarios.py` (Phase 7): bounded schema, the 8 presets, clamp/reject with
  `guardrail_events`, natural-language translation and human confirmation.
* **D-6-6** — `stress.py` and `sensitivity.py` (Phase 8): baseline-vs-stressed comparison, KPI
  deltas, breach thresholds, the EBITDA waterfall, single-factor sweeps.
* **D-6-7** — re-scoring the projected end-state through Phase 4 for per-dimension deltas
  (simulation.md §5, "Dimension deltas"). Phase 6 prepares the inputs; the comparison is
  Phase 8.
* **D-6-8** — equity / balance-sheet roll-forward, if ever specified (§D-4).
* **D-6-9** — persistence and a service/API entry point (Phase 10).
* **D-6-10** — feeding twin trajectories into the Phase 5 ML feature matrix. The two are
  siblings that both depend on `risk_engine`, so this creates no cycle, but the feature
  contract bridge belongs to a later evaluation phase.

## 11. Known limitations

1. **Monthly history required.** A company with annual or quarterly statements cannot be
   simulated yet (§7.3).
2. **No balance sheet.** The twin projects income statement, working capital, cash flow and
   debt, not equity or total assets (§D-4).
3. **`base_rate` is a documented 6% offline default**, not a market observation, because the
   twin never fetches. Any interest-rate conclusion is conditional on that assumption, and
   the assumption is surfaced in `SimulationDiagnostics.fallbacks_used`.
4. **The opex split frequently falls back** to the frozen `F = 0.5·opex₀`, `v = 0.5·opex₀/rev₀`
   form, because the fitted slope is often negative on synthetic data and the frozen `F, v ≥ 0`
   constraint forbids it. This is disclosed per run, not hidden.
5. **Scores are in-sample projections of a model**, not predictions about a real company.
6. **Not professional financial advice, not a valuation, not a forecast**, and not a
   regulatory-grade model.

## 12. Out of scope

Monte Carlo or any stochastic simulation · reverse stress testing · multi-company
simulation · scenario translation, presets and bounds policy · stress comparison, breach
policy and the EBITDA waterfall · sensitivity sweeps · LangGraph agents · REST/SSE API ·
database persistence or migrations · frontend · LLM calls of any kind · any change to the
frozen Phase 4 or Phase 5 methodology, formulas, goldens or registry.

## 13. Phase 6 Boundary

Phase 6 ends here. `scenarios.py`, `stress.py`, `sensitivity.py`, agents, the API, the
database and the frontend were **not** started. The twin is a programmatic subsystem with no
API, agent, database or production entry point — exactly as the ML engine was at Phase 5
closure, and for the same architectural reason (R3).

---

**PHASE 6 DOCUMENTATION CLOSURE COMPLETE — AWAITING USER REVIEW.**
**Next phase after approval: PHASE 7 — SCENARIO ENGINE (not started).**



