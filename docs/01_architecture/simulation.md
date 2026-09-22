# Business Digital Twin, Scenario & Stress Testing (Phase 1 freeze)

**Status:** Frozen at Phase 1. Pure deterministic monthly simulation in `backend/simulation/`.

## 1. Twin parameters (frozen)

Tagged **[R]** real (from statements), **[A]** assumption (documented default), **[S]** scenario.
Horizon `H ≤ 36` months; monthly step `t = 1..H`.

| Parameter | Symbol | Tag | Default / derivation | Constraint |
|---|---|---|---|---|
| Base growth | g | [R/A] | trailing 12-mo revenue CAGR, clamped to [−5%, +15%] annual | — |
| COGS ratio | c₀ | [R] | cogs/revenue, trailing 12-mo mean | [0,1] |
| Opex split | F, v | [A] | OLS of opex on revenue over history; fallback F = 0.5·opex₀, v = 0.5·opex₀/rev₀ | F, v ≥ 0 |
| D&A monthly | DA | [R/A] | trailing da / 12 | ≥ 0 |
| Tax rate | τ | [R/A] | effective rate from history, clamped [5%, 35%]; fallback 25% | [0, 0.45] |
| Base rate | r₀ | [R/A] | FRED FEDFUNDS latest + 200 bp spread ([A] spread); offline fallback 6% | ≥ 0 |
| Floating share | φ | [R/A] | `rate_exposure.floating_debt_share`; fallback 0.5 | [0,1] |
| Debt & schedule | D₀, amort | [R/A] | from `debt_schedule`; equal amortization inside buckets | — |
| WC days | DSO, DIO, DPO | [R] | trailing 12-mo means | ≥ 0 |
| Capex monthly | Capex₀ | [R/A] | trailing mean | ≥ 0 |
| Min cash buffer | B | [A] | 1.0 × monthly opex | ≥ 0 |
| Revolver cap | RC | [A] | 3.0 × monthly opex | ≥ B |
| FX shares | κ_fx, ρ_rev | [R/A] | from `fx_exposure`; fallback 0.1 / 0.1 | [0,1] |
| Commodity cost share | κ_c | [R/A] | from `commodity_exposure`; fallback 0.2 | [0,1] |
| Pass-through capacity | ptc | [A] | 0.3 (shared with risk engine) | [0,1] |
| FX demand elasticity | e_fx | [A] | 0.5 | [0,1] |

## 2. Monthly recursion (frozen equations)

Scenario deltas enter as **step changes at t = 1** unless `ramp_months R > 0` (linear ramp over R
months).

```text
Demand:    Rev_dem_t = Rev_{t-1} · (1+g) · (1+δ_rev,t) · (1 − δ_fx,t·ρ_rev·e_fx)
Supply:    Rev_sup_t = Capacity₀ · (1 − δ_supplier,t)          # Capacity₀ = trailing 12-mo max revenue
Revenue:   Rev_t    = min(Rev_dem_t, Rev_sup_t)                # disruption caps revenue (assumption, disclosed)
COGS:      COGS_t   = Rev_t · c₀ · (1 + δ_comm,t·κ_c·(1−ptc)) · (1 + δ_fx,t·κ_fx·(1−ptc)) · (1 + δ_cogs,t)
GP:        GP_t     = Rev_t − COGS_t
Opex:      Opex_t   = (F + v·Rev_t) · (1 + δ_opex,t)
EBITDA:    EBITDA_t = GP_t − Opex_t ;   EBIT_t = EBITDA_t − DA
Interest:  Interest_t = (r₀ + δ_rate,t)/12 · D_{t-1}·φ + r₀/12 · D_{t-1}·(1−φ)
EBT/Tax:   EBT_t = EBIT_t − Interest_t ; Tax_t = max(0, EBT_t)·τ ; NI_t = EBT_t − Tax_t
NWC:       AR_t = Rev_t·(DSO+δ_ar)/30 ; Inv_t = COGS_t·DIO/30 ; AP_t = COGS_t·DPO/30
           ΔNWC_t = (AR+Inv−AP)_t − (AR+Inv−AP)_{t-1}
Cash flow: OCF_t = NI_t + DA − ΔNWC_t
           CF_t  = OCF_t − Capex₀·(1+δ_capex,t) − principal_t + draws_t − one_off_cost (t=1)
Cash:      Cash_t = Cash_{t-1} + CF_t                          # may go negative — never clamped
Debt:      D_t = D_{t-1} − principal_t + draws_t
```

Frozen interpretations:
- **Funding shortfall:** draws = shortfall vs buffer B (rate = r₀ + 200 bp stress premium [A]);
  draws ≤ revolver cap RC; beyond RC the period records a **`funding_gap`** (hard breach). Cash may go
  negative only via a funding gap; both are disclosed, never hidden.
- **Supplier disruption** binds through the supply ceiling `Capacity₀` (explicit assumption).
- **Tax** on positive EBT only; no loss carryforward (simplification, disclosed).
- All scenario deltas are annual % / pp unless stated monthly.

## 3. Scenario schema (frozen — guardrail 5)

```json
{
  "name": "string (1..80)",
  "horizon_months": "int 1..36 (default 12)",
  "ramp_months": "int 0..12 (default 0 = step)",
  "revenue_change_pct": "[-50, 50]",
  "cogs_change_pct": "[-50, 50]",
  "opex_change_pct": "[-50, 50]",
  "interest_rate_change_pp": "[-5, 5]",
  "fx_change_pct": "[-50, 50]",
  "commodity_price_change_pct": "[-50, 100]",
  "supplier_disruption_pct": "[0, 100]",
  "capex_change_pct": "[-100, 100]",
  "ar_days_change": "[-30, 60]",
  "one_off_cost": "float ≥ 0 (charged at t=1, company currency)"
}
```

Out-of-range values: **clamped** with a `guardrail_events` row (severity `info`, action `clamp`) when
within 1.25× of the bound, otherwise **rejected** (`SCENARIO_OUT_OF_BOUNDS`). Unknown keys rejected.

## 4. Presets (frozen template defaults — user-editable, not regulator-calibrated)

| Preset | Params |
|---|---|
| `recession` | revenue −15%, ar_days +10 |
| `inflation` | cogs +12%, opex +8% |
| `rate_shock` | interest_rate +2pp |
| `fx_shock` | fx +10% (depreciation → import cost ↑ via κ_fx; revenue ↓ via ρ_rev·e_fx) |
| `commodity_shock` | commodity +25% |
| `demand_collapse` | revenue −30%, ar_days +15 |
| `supplier_disruption` | supplier_disruption 40% |
| `combined_stress` | revenue −20%, cogs +10%, interest +2pp, commodity +15%, ar_days +10 (DFAST-patterned multi-factor) |

## 5. Stress-test outputs (frozen)

- **Trajectories** (both runs, monthly): Rev, GP, EBITDA, EBIT, NI, Cash, Debt, AR, Inv, AP, DSCR_t,
  interest_coverage_t, runway_t.
- **KPI comparison** (trough and end-horizon): revenue, EBITDA, net income, min cash, runway, min DSCR
  — baseline / stressed / Δ absolute / Δ %.
- **Breach flags** (defaults, configurable): runway < 6 months · DSCR < 1.2 · interest coverage < 1.5 ·
  cash < buffer B · funding gap occurred · current-ratio proxy < 1.0.
- **EBITDA waterfall** (frozen order): revenue effect `(Rev_s−Rev_b)·GM_b` → input-cost effect →
  opex effect → other/one-off; below-EBITDA bridge: interest effect, tax effect (to net income).
- **Dimension deltas:** risk engine re-scores the stressed end-state (projected balance sheet at
  horizon end) → per-dimension Δ scores.

## 6. Invariants & tests (frozen for Phases 6/8)

1. **Cash identity:** `Cash_t = Cash_{t-1} + OCF_t − Capex_t − principal_t + draws_t` (±1e-6 relative).
2. **Reproducibility:** identical inputs ⇒ float-identical outputs (R6).
3. **Monotonicity sweeps:** single-factor sweeps (δ_rev −50%→+50%) move trough cash and EBITDA
   monotonically in the expected direction.
4. **Breach consistency:** breach flag exists iff its condition holds.
5. **Waterfall closure:** components sum to ΔEBITDA within 0.5%.
6. **Golden files:** baseline trajectories for fixture seeds 1001–1005 ([testing.md](testing.md)).
