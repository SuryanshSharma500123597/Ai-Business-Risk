# Digital Twin & Stress-Testing Validation Report (Workstream F)

**Status:** validation audit complete — read-only w.r.t. the frozen engines;
four *additive* independent checks added in
`backend/tests/unit/test_twin_stress_independent.py`.
**Frozen authority:** `docs/01_architecture/simulation.md` §1 (parameters),
§2 (monthly recursion), §5 (outputs/breaches), §6 (invariants).
**Scope:** independent numerical validation of Phases 6–8 only. No frozen file,
formula, default, threshold, schema, or golden fixture was modified.

---

## 1. What this audit is — and is not

Three different kinds of validation are kept apart:

1. **Implementation correctness** — does the code compute exactly what its
   documented contract specifies? *(This workstream's focus.)*
2. **Financial coherence** — do the calculations satisfy defensible accounting
   and financial relationships under the stated assumptions? *(Also addressed.)*
3. **Empirical validity** — do outputs correspond to real-world outcomes?
   ***Not* established here.** The twin runs on synthetic data; no real-world
   validation set is used. Passing these tests does **not** establish real-world
   financial predictive accuracy.

---

## 2. Implementation map and calculation flow

All in `backend/simulation/` (there is no `backend/stress/` package — a
documented decision; stress logic lives in `stress.py` and `sensitivity.py`).

### 2.1 Monthly recursion — `twin.py::step_month` (§2, frozen order)

Each step consumes only what earlier steps produced:

| Stage | Formula (frozen §2) |
|---|---|
| demand | `Rev_dem,t = Rev_{t-1} · (1+g)^(1/12) · (1 + Δrev·ramp)` then minus `Δfx·fx_rev_share·elasticity·Rev_dem` |
| supply / revenue | `Rev = min(Rev_dem, Capacity·(1 − supplier_disruption·ramp))` |
| COGS | `Rev·cogs_ratio · (1 + Δcomm·comm_share·(1−ptc)) · (1 + Δfx·imp_share·(1−ptc)) · (1 + Δcogs)` |
| gross profit | `Rev − COGS` |
| opex | `(fixed + var_ratio·Rev)·(1 + Δopex·ramp)` |
| EBITDA / EBIT | `GP − opex`; `EBIT = EBITDA − da` |
| interest | split on **opening** debt: `rate/12·floating + base_rate/12·fixed` |
| EBT / tax / NI | `EBT = EBIT − interest`; `tax = max(0, EBT)·tax_rate`; `NI = EBT − tax` |
| working capital | `AR = Rev·DSO/30`, `Inv = COGS·DIO/30`, `AP = COGS·DPO/30`, `NWC = AR+Inv−AP` |
| OCF | `NI + da − ΔNWC` |
| capex / principal | `capex·(1+Δcapex·ramp)`; `principal = min(schedule(t), opening_debt)` |
| cash / debt | `cash_before = cash + OCF − capex − principal − one_off`; `shortfall = max(0, B − cash_before)`; `draws = min(shortfall, RC)`; `funding_gap = shortfall > RC`; `cash = cash_before + draws` (**never clamped**); `debt = max(0, opening − principal + draws)` |

The per-month `MonthLedger` keeps the financing/channel detail beside the state,
which is what lets the cash identity be re-checked independently instead of
being a tautology of the same variables.

### 2.2 Six invariants — `twin.py::check_invariants` (§6)

`cash_identity` (≤1e-6 rel), `debt_roll_forward` (≤1e-9), `nwc_continuity`
(≤1e-9), `tax_non_negative`, `negative_cash_only_via_funding_gap`,
`horizon_bounded` (≤36).

### 2.3 Ratios — Phase 4 calculators, wired by `_calculator_inputs`

`calc_dscr` (financial_strength.py) and `calc_interest_coverage` consume the
month; `st_debt` is supplied as the month's **actual scheduled principal**, so
the twin yields the standard monthly `DSCR = EBITDA/(interest+principal)` while
reusing the frozen formula and its zero-denominator branches unchanged.
`calc_cash_runway_months` (liquidity.py) supplies runway.

### 2.4 Stress pipeline — `stress.py`

`run_stress` runs `simulate()` twice (baseline zero-overrides, stressed with
`to_overrides`), refuses the comparison if either run's invariants fail, then:
`compare_kpis` (trough+end, frozen `KPI_ORDER`), `resolve_min_cash_buffer`
(reads the run's own buffer record; missing → `INTERNAL_ERROR`, never silent 0),
`detect_breaches` (month-by-month, frozen `BREACH_ORDER` + defaults runway 6.0 /
DSCR 1.2 / coverage 1.5), `attribute_waterfall` (monthly-then-sum + bridge),
and SHA-256 result hashing.

### 2.5 Sensitivity — `sensitivity.py`

One-factor-at-a-time sweep from a zero-shock base on a 9-point inclusive-endpoint
grid. It asserts determinism/ordering/cap/bounds but **deliberately never asserts
direction** (see D-6-3).

---

## 3. Existing validation coverage vs. the four additive checks

The existing suite already covers, exhaustively: hand month-1/2 arithmetic,
growth compounding, GP/EBITDA/EBIT, tax floor, interest split, zero-debt,
WC/DSO/DIO/DPO, ΔNWC, OCF, capacity cap, revenue decline, FX, commodity, cogs
ordering, opex, AR days, ramps, one-off, capex, draws/shortfall/revolver/
funding-gap, negative-cash-only-via-gap, principal, DSCR/runway per month,
horizons 1/36 and rejection of >36/0, determinism, all six invariants, cash-identity
residual, nonfinite, summary, trajectory, `simulate` end-to-end, reproducibility
across canonical seeds, working-capital release, D-6-3, D-6-7 deferral,
current-ratio proxy unevaluable, breach order/chronology, waterfall closure and
presets, bridge-to-NI, one-off-never-attributed, custom/invalid policy, the
sensitivity grid/OFAT/baseline, breach-iff, and the full property suite.

The four **additive** independent checks fill genuine gaps:

| # | Gap in existing coverage | What the new test proves |
|---|---|---|
| G1 | missing-required-input rejection untested | revenue/cash/debt each refused; no imputation; completeness path carries exact values |
| G2 | zero/negative-denominator ratio behaviour untested *through the twin outputs* (only at calculator level) | DSCR sentinel on zero debt service; coverage sentinel on zero interest with positive service; negative DSCR; negative coverage |
| G3 | only `revenue_effect` bucket + closure independently checked (partly self-referential) | **all four** waterfall buckets **and** the below-EBITDA bridge recomputed from raw monthly records |
| G4 | DSCR identity not hand-pinned at twin level | `DSCR == EBITDA/(interest+principal)` for a positive-denominator month |

*Not* added as twin tests: "mixed currencies" (a `CompanyDataset` carries one
profile currency — a `data_engine` concern, not a twin input) and invalid
scenario bounds (owned and tested by `scenarios.py`).

---

## 4. D-6-3 — working-capital release raises trough cash under contraction

* **Invariant originally asserted** (frozen `simulation.md` §6.3): sweeps move
  trough cash and EBITDA monotonically in the expected direction.
* **Mechanism that breaks it:** under a revenue contraction, receivables
  (`Rev·DSO/30`) and inventory (`COGS·DIO/30`) shrink. If working capital is
  *released* faster than cash is consumed, `OCF = NI + da − ΔNWC` rises (ΔNWC is
  negative), so trough **cash can rise while EBITDA falls**.
* **Economically coherent:** yes — releasing working capital under contraction is
  standard corporate behaviour. The naive monotonicity invariant is the incorrect
  part, not the engine.
* **Independently confirmed by existing artifacts (no new run needed):**
  golden `test_golden_pins_d63_non_monotone_trough_cash` (seed 1002:
  `cash[0] > cash[baseline]`, `ebitda[0] < ebitda[baseline]`); unit guard
  `test_d63_trough_cash_not_monotone_documented`
  (`stressed_at(-37.5, min_cash) > stressed_at(0.0, min_cash)`);
  `test_a_shrinking_business_releases_working_capital`; and `sensitivity.py`
  asserts determinism/ordering, never direction.
* **Correct stronger invariant (already enforced):** the structural identities
  (cash identity, debt roll-forward, NWC continuity, tax ≥ 0,
  negative-cash-only-via-gap). Direction-of-travel is a *pinned finding*, not an
  invariant. **No code or golden change is required or permitted.**

This is **resolved-as-documented**, not an open defect.

---

## 5. D-6-7 — dimension deltas and current-ratio proxy remain unevaluable

* **Dimension deltas:** `dimension_deltas = None` with a machine-readable
  `dimension_deltas_note` listing the projected balance-sheet fields the twin
  never emits (equity, total_assets, current_assets/liabilities,
  total_liabilities, st_debt, lt_debt). Re-scoring needs a full
  `CompanyDataset`; the twin projects no balance-sheet levels, and Phase 8 does
  not fabricate them (asserted by `test_dimension_deltas_deferred_with_missing_fields`).
* **Current-ratio proxy breach:** reported `unevaluable`. The twin projects
  AR/Inv/AP **flows**, not current-asset/liability **levels**; the frozen spec
  defines no proxy, and inventing one would be new methodology (asserted by
  `test_breach_order_and_proxy_unevaluable`).

Both are honest limitations, not defects.

---

## 6. Independent formulas and expected-value derivations (G1–G4)

All expected numbers below are derived by hand from the frozen formulas and
round inputs (`revenue 1000`, `cogs_ratio 0.50`, `var_ratio 0.10`,
`base_rate 0.12`, `floating 1.0`, `tax 0.25`), **not** read from engine output.

* **G1** — `build_initial_state_from_period` raises
  `ValueError("… missing inputs are never imputed")` when any of revenue / cash /
  total_debt is `None`; a complete period populates the state verbatim.
* **G2a** — `initial_debt 0` ⇒ interest 0, principal 0 ⇒ debt_service 0 ⇒
  `DSCR = 999.0` (sentinel); zero interest ⇒ `coverage = 999.0`.
* **G2b** — `base_rate 0` with `initial_debt 1200` + 0-3m bucket (400/mo) ⇒
  interest 0, principal 400 ⇒ `DSCR = EBITDA/400` (a real ratio, **not** 999),
  `coverage = EBIT/0 = 999.0`.
* **G2c** — `var_ratio 2.0` ⇒ opex 2000, `EBITDA = 500 − 2000 = −1500`; with
  debt service `12 + 400` ⇒ `DSCR = −1500/412 = −3.6408 < 0` (real negative).
* **G2d** — `da_monthly 1000` ⇒ `EBIT = 400 − 1000 = −600`; interest 12 ⇒
  `coverage = −600/12 = −50 < 0`.
* **G4** — `initial_debt 1200` @ 12% + 0-3m bucket ⇒ interest `0.12/12·1200 = 12`,
  principal 400, `EBITDA = 1000 − 500 − 100 = 400` ⇒
  `DSCR = 400/(12+400) = 0.970873786…`.
* **G3** — per month, from raw records:
  `GM_b=(Rev_b−COGS_b)/Rev_b`, `CR_b=COGS_b/Rev_b`,
  `revenue_effect += (Rev_s−Rev_b)·GM_b`,
  `input_cost_effect += (Rev_s−Rev_b)·CR_b − (COGS_s−COGS_b)`,
  `opex_effect += −(Opex_s−Opex_b)`,
  `other += ΔEBITDA − ΔRev·GM_b − (ΔRev·CR_b − ΔCOGS) + ΔOpex`,
  `interest_effect += −(Int_s−Int_b)`, `tax_effect += −(Tax_s−Tax_b)`.
  Each emitted bucket equals that hand sum; the interaction residual equals the
  four-bucket closure and stays within the frozen 0.5 % tolerance; the bridge
  residual equals `ΔNI − (ΔEBITDA + interest + tax)` and is float dust (≤1e-6).

---

## 7. Confirmed findings, limitations, remaining gaps

* **Confirmed:** the frozen twin and stress pipeline compute exactly their
  documented contract on the tested cases (G1–G4 all pass); the missing-input
  guard, ratio sentinels/negative branches, DSCR identity, and full waterfall
  decomposition are all correct and independently reproduced.
* **Documented limitations:** D-6-3 monotonicity (resolved-as-documented); D-6-7
  dimension-delta and current-ratio proxy (deferred/unevaluable); simplified
  tax (flat, on positive EBT only), interest accrual, financing order, and runway
  conventions — these are modelling simplifications, not a full accounting system.
* **Remaining gaps (out of scope, feature work):** no projected balance sheet
  (hence no dimension deltas / current-ratio proxy); no empirical validation set.
* **Empirical validity is not claimed.** Synthetic stress scenarios do not
  validate historical predictive performance.

---

## 8. Reproducibility

```bash
python -m pytest backend/tests/unit/test_twin_stress_independent.py -v
python -m pytest -q            # full suite
python -m ruff check backend
python -m mypy                 # configured: files=['backend']
git diff --check
```

Frozen phases 4–8, golden fixtures, and both raw datasets are unchanged (verified
by hash and by `git diff --name-only` over the frozen directories).
