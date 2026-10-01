# Quantitative Risk Engine — Formula Registry (Phase 1 freeze)

**Status:** Frozen at Phase 1. Pure functions in `backend/risk_engine/`. Definitions follow standard
conventions (see [phase-0-research.md](../00_research/phase-0-research.md) §6). Every formula has a
hand-computed fixture test enforced against the registry (NFR2, implemented in Phase 4). The frozen
anchors and formulas in §1–§10 are unchanged; the **implemented** state, the Stage 5 market-input routing
and the recorded interpretation notes are documented in **§11–§13**.

## 1. Scoring method (frozen)

- Each metric maps to a **0–100 risk score** by **piecewise-linear interpolation** over frozen anchor
  points `(metric_value → score)`, clamped at the ends. Anchors below are **defaults**, overridable via
  the registry file; any override is versioned and stamped into outputs.
- Higher score = higher risk. **Severity labels:** 0–25 Low, 25–50 Moderate, 50–75 High, 75–100
  Critical.
- **Dimension score** = mean of its metric scores (metric weights equal by default; configurable in
  the registry, versioned). **Composite** = Σ w_d·S_d over the 7 dimensions, Σ w_d = 1, default
  w_d = 1/7 each; user-adjustable and versioned (`aggregation_weights` table).
- **Contributions:** aggregation is additive, so each metric's contribution to its dimension and each
  dimension's contribution to the composite is **exact** — explanation layer L1 (spec §22).
- **Sensitivity (frozen method):** recompute the composite with each w_d perturbed ±20% (renormalized);
  report the composite range and dimension-rank stability (spec RQ4).
- **Rounding:** compute float64; store raw; round only at presentation (ratios 2 dp, percentages 1 dp,
  currency per locale). Scores stored as float, displayed as integers.
- **Versioning:** `registry_version` bumps on any formula/band change; every output row stores it.

## 2. Dimension: Financial Strength

| Formula id | Definition | Inputs | Edge cases | Band anchors (value→score) |
|---|---|---|---|---|
| `gross_margin` | gross_profit / revenue | period | revenue=0 → 100, flagged | 10→90, 20→65, 30→45, 40→25 (percent) |
| `operating_margin` | ebit / revenue | period | revenue=0 → 100 | 2→90, 5→70, 10→45, 15→25, 20→15 |
| `net_margin` | net_income / revenue | period | revenue=0 → 100 | 0→85, 3→65, 6→45, 10→25, 15→15; <0 linear to (−10→100) |
| `roa` | net_income / total_assets | period | assets=0 → 100 | −5→95, 0→80, 3→55, 6→35, 10→15 |
| `roe` | net_income / equity | period | equity≤0 → 100, flagged | −10→95, 0→80, 8→55, 15→35, 25→15 |
| `debt_to_equity` | total_debt / equity | period | equity≤0 → 100 | 0.5→15, 1→30, 2→55, 3→75, 4→90 |
| `debt_to_ebitda` | total_debt / ebitda | period | ebitda≤0 → 100 | 1→15, 3→35, 5→60, 7→85 |

## 3. Dimension: Liquidity

| Formula id | Definition | Edge cases | Anchors |
|---|---|---|---|
| `current_ratio` | current_assets / current_liabilities | CL=0 → score 5 (surplus), flagged | 0.5→95, 1.0→75, 1.5→45, 2.0→25, 3.0→10 |
| `quick_ratio` | (current_assets − inventory) / current_liabilities | as above | 0.3→95, 0.8→70, 1.2→40, 1.5→20 |
| `cash_ratio` | cash / current_liabilities | as above | 0.1→95, 0.3→70, 0.5→45, 1.0→15 |
| `cash_runway_months` | cash / avg monthly burn; burn = max(0, −trend ocf) | ocf ≥ 0 → score 5, `n/a` label | 0→100, 3→90, 6→70, 12→45, 24→20 |
| `st_obligation_coverage` | cash / current_liabilities (facility-aware when data present) | — | 0.2→95, 0.5→75, 1.0→50, 1.5→30, 2.0→15 |

## 4. Dimension: Market / External-Price Exposure

| Formula id | Definition | Notes | Anchors |
|---|---|---|---|
| `rate_sensitivity` | floating_debt_share × total_debt × elasticity 1.0 interest-expense per pp → expressed as % of EBITDA | uses `rate_exposure`; EBITDA≤0 → 100 | 2→20, 5→40, 10→65, 15→85 |
| `fx_exposure_score` | 100 × (0.6×import_cost_share + 0.4×foreign_revenue_share) × (1 − pass_through_capacity) | pass-through [A] 0.3 default | 10→20, 25→40, 40→60, 60→85 |
| `commodity_exposure_score` | 100 × cost_share × (1 − pass_through_capacity) | uses `commodity_exposure` | same anchors as fx |
| `revenue_volatility` | annualized σ of monthly revenue (√12); needs ≥24 periods | private-firm substitute for equity vol | 5→20, 10→35, 20→55, 30→75 |
| `equity_volatility` | stdev(daily log returns)×√252 | **listed mode only** | 15→15, 25→30, 40→50, 60→70, 80→85 |
| `beta` | Cov(r_i, r_m)/Var(r_m), 252d window, configurable index | **listed mode only**; min 120 obs | 0.5→20, 1.0→30, 1.5→50, 2.0→70 |
| `var_95` / `es_95` | historical VaR / ES on the market series, α = 0.95 | **listed mode only** | % of exposure: 2→20, 5→40, 10→65, 15→85 |

Dimension score = mean of available metrics; without market series (private firm) the equity metrics
are skipped and the score rests on the exposure metrics — disclosed in outputs.

## 5. Dimension: Credit

| Formula id | Definition | Notes | Anchors |
|---|---|---|---|
| `dso` | receivables / revenue × 365 | — | 30→20, 45→35, 60→50, 90→70, 120→85 |
| `receivables_concentration` | HHI of customer shares | reuses `hhi`; excluded from Concentration mean (no double counting) | hhi anchors |
| `receivable_trend` | 12-mo slope of DSO (days/year) | needs ≥8 periods | 0→25, 10→40, 20→55, 30→70 |
| `altman_z_distance` | map Z to score: Z ≥ 2.99 → 10; Z = 1.81 → 60; below 1.81 linear to 100 | **variant auto-selected:** public manufacturer → original Z (market equity); private → Z′ (book equity, cutoffs 2.675/1.23 mapped proportionally); non-manufacturer → Z″ (4-ratio, cutoffs 2.6/1.1). Selection recorded. | — |
| `merton_dd` (optional) | DD = [ln(V/D)+(μ−σ²/2)T]/(σ√T); PD = Φ(−DD) | **listed mode only, off by default**; reference-only (V, σ unobservable) | DD: 3→20, 2→45, 1→70, 0.5→90 |

## 6. Dimension: Operational

| Formula id | Definition | Notes | Anchors |
|---|---|---|---|
| `dio` | inventory / cogs × 365 | cogs=0 → skip | 30→20, 60→40, 90→60, 120→75 |
| `dpo` | payables / cogs × 365 | two-sided U: too low = cash pressure, too high = supplier strain | 15→60, 30→40, 45→25, 60→20, 90→35, 120→50 |
| `ccc` | dso + dio − dpo | — | 15→20, 30→30, 45→45, 60→60, 90→80, 120→90 |
| `supplier_concentration` | HHI of supplier shares | reuses `hhi`; excluded from Concentration mean | hhi anchors |
| `opex_rigidity` | F/(F + v·Rev) fixed share of opex (twin split per [data.md](data.md)) | rigid base amplifies demand shocks | 0.3→20, 0.5→40, 0.7→60, 0.85→80 |
| `single_source_flags` | count of input categories with top-supplier share > 0.6 | from operations profile | 0→10, 1→55, 2→80, ≥3→95 |

## 7. Dimension: Concentration

| Formula id | Definition | Notes | Anchors |
|---|---|---|---|
| `hhi` | Σ sᵢ² per bucket (0–1) | customers / suppliers / products / regions averaged | 0.15→15, 0.25→35, 0.45→60, 0.6→80 |
| `cr1` | largest share, averaged across buckets | — | 0.3→20, 0.5→45, 0.7→70, 0.9→90 |
| `cr3` | top-3 share sum, averaged | — | 0.5→20, 0.7→40, 0.9→65, 1.0→75 |

## 8. Dimension: Macro

| Formula id | Definition | Notes | Anchors |
|---|---|---|---|
| `inflation_passthrough` | \|Δgross_margin\| vs ΔCPI over 24 mo | **labeled correlation, not causation**; needs CPI cache | margin-gap pp: 0→15, −2→45, −5→75 |
| `rate_environment` | current FEDFUNDS vs trailing 5-yr median | shapes refinancing risk | pp: 0→15, 2→35, 4→60, 6→80 |
| `fx_volatility` | annualized σ of DEXINUS (configured pair) | 252d | 3→20, 6→40, 10→65 |
| `gdp_sensitivity` | sector GDP-elasticity [A: manufacturing 1.2, retail 1.0, services 0.8] × recent GDP volatility | assumption-based, disclosed | 0.5→20, 1.0→45, 1.5→70 |

## 9. Reference models (frozen scope)

- **Altman Z** (Altman 1968): public-manufacturing coefficients `1.2/1.4/3.3/0.6/1.0` (X4 = market
  equity), zones **>2.99 safe / 1.81–2.99 grey / <1.81 distress**; **Z′** private firms
  `0.717/0.847/3.107/0.420/0.998` (X4 = book equity), cutoffs 2.675/1.23; **Z″** non-manufacturers
  4-ratio `6.56/3.26/6.72/1.05`, cutoffs 2.6/1.1. Variants are never mixed; auto-selection per §5.
- **Merton DD/PD**: listed mode only, optional, reference-only.

## 10. Validation requirements (frozen for Phase 4)

1. **Fixtures:** ≥2 hand-computed cases per formula (typical + the edge case from its table row).
2. **Property tests:** monotonicity (worse value ⇒ score non-decreasing in the band direction);
   clamping at extremes; continuity at anchors; scale invariance for pure ratios (currency cancels).
3. **Golden files:** one composite profile per canonical fixture company (seeds 1001–1005), regenerated
   only with explicit review ([testing.md](testing.md)).

## 11. Implementation status (recorded at Phase 4 documentation closure)

The frozen method of §1 is implemented in `backend/risk_engine/` and verified. This section records what
exists, so this document is not read as a plan.

- **Scoring:** `interpolate_score` performs piecewise-linear interpolation over the frozen `(value, score)`
  anchors, **clamped** between anchors and at the ends, so every score stays within 0–100. Frozen edge
  cases (`revenue=0 -> 100`, `CL=0 -> score 5`, …) are applied verbatim as a `forced_score` instead of
  being interpolated, so zero-denominator cases never emit non-finite values.
- **Severity bands:** `get_severity_label` (0–25 Low, 25–50 Moderate, 50–75 High, 75–100 Critical) with
  clamping; `SeverityLabel` is carried on every metric, dimension and composite result.
- **Dimension aggregation:** `aggregate_dimension` averages available metric scores (equal metric weights,
  `weight_in_dimension` recorded); unavailable metrics are excluded, never zero-filled.
- **Composite aggregation:** `aggregate_composite` computes Σ w_d·S_d with weights normalized over the
  **available** dimensions.
- **Configurable weights / configured-vs-effective:** `custom_weights` can be supplied per run; each
  `DimensionResult` reports `weight` (the configured weight actually used) and `effective_weight` (the
  re-normalized share applied after excluding missing dimensions). With no missing dimensions they coincide.
- **`registry_version`:** `REGISTRY_VERSION = "1.0.0"` (`backend/risk_engine/contracts.py`, re-exported by
  `registry.py`) is stamped on every metric, dimension and composite result and on the top-level report; a
  golden baseline whose version differs from the code fails the golden test.
- **Sensitivity analysis:** `run_sensitivity_analysis` perturbs each dimension weight by ±20% with
  re-normalization and reports the composite range plus Spearman rank stability.
- **Exact contributions:** metric contributions sum to the dimension score and dimension contributions sum
  to the composite (Σ C_d = S_composite, reconciled at `abs_tol = 1e-9`).
- **Determinism:** identical inputs/seeds produce identical outputs; repeated evaluations of one dataset
  return the same scores and severities (asserted in fixture, golden and property tests).
- **Altman handling:** variant auto-selection (public manufacturer → Z, private → Z′, non-manufacturer →
  Z″), each variant using **its own** cut-offs, mapped to a 0–100 score (safe zone → low score, distress
  zone → high score, linear to 100 below the distress cut-off). The selected variant is recorded.
- **Missing-input behavior:** missing or invalid inputs return `MISSING_INPUT`, `INVALID_INPUT`,
  `UNAVAILABLE` or `INSUFFICIENT_HISTORY` with `value=None`/`score=None`; an entirely-missing profile
  yields a composite score of `None` rather than a fabricated mid-range value.
- **Guardrails:** metric floats are validated as finite; `market_inputs` and `market_series` are mutually
  exclusive; mixed-currency beta legs raise `ValueError`; the package imports no FastAPI, LangGraph, LLM,
  datastore or Phase 3 fetcher code (R3, enforced by the architecture test).
- **Verification:** 40 hand-computed metric fixtures enforced by a registry-walking test (40/40 registry
  metrics), deterministic seeded property tests (clamping, monotonicity, anchor continuity, scale
  invariance, additive reconciliation, two-sided metrics), golden composite baselines for seeds 1001–1005,
  `risk_engine` line coverage 94%, Ruff/Ruff-format clean, Mypy clean.

## 12. Stage 5 market-input routing (D18–D21, approved)

Stage 5 added the typed `RiskEngineMarketInputs` contract and a Phase 3→Phase 4 adapter
(`backend/data_engine/{market_inputs,macro_inputs,risk_inputs}.py`). No formula or anchor changed.

```text
equity_returns    -> equity_volatility, var_95, es_95     (company/equity leg; log returns)
benchmark_returns -> beta (together with equity_returns)  (asset leg x benchmark leg)
fx_returns        -> fx_volatility                        (FX leg only)
cpi_change / gross_margin_change      -> inflation_passthrough
fedfunds_current / trailing 5y median -> rate_environment
gdp_volatility (+ sector elasticity)  -> gdp_sensitivity
```

- `beta` is computed from **two distinct legs** (`calc_beta(equity_returns, benchmark_returns)`, asset leg
  first), so the former degenerate `calc_beta(series, series)` β = 1.0 result cannot recur. With a single
  leg the metric is `UNAVAILABLE`/`MISSING_INPUT`. The deprecated `market_series` argument feeds equity-leg
  metrics only and never beta.
- **VaR and ES use the equity leg only**; FX returns never reach equity metrics and benchmark returns never
  reach VaR/ES.
- Frozen floors: `MIN_VOL_OBS = 30`, `MIN_VAR_ES_OBS = 60`, `MIN_BETA_ALIGNED_OBS = 120`,
  `MIN_CPI_MONTHS = 24`, `MIN_FEDFUNDS_MONTHS = 60` (`backend/risk_engine/contracts.py`).
- Series are log returns `ln(P_t / P_{t−1})`; beta legs are **inner-joined on shared dates** (no forward
  fill) and the joined observation count is reported in `inputs_used["joined_obs"]`.
- **Provenance:** one `SeriesProvenance` record per supplied leg (series id, source, as-of date, observation
  count) is stamped into the routed metric's `inputs_used` — `series_id`/`source` for single-leg metrics,
  `asset_symbol`/`benchmark_symbol`/`joined_obs` for beta. Nothing is overwritten.
- **No I/O:** aligned return series and pre-aggregated macro scalars are produced by the adapter, so the
  engine performs no HTTP, cache or SQL access (R3). `WeightsRef` is a carried contract only; its
  persistence is deferred to Phase 10.

## 13. Recorded interpretation notes (approved at Phase 4 documentation closure)

These are recorded ambiguities/interpretations, not silent changes. The implementation is retained as
approved; changing any of them requires separate explicit approval.

- **Q-M1 — volatility observation floor.** The implemented floor for `equity_volatility` and
  `fx_volatility` is **30 observations** (`MIN_VOL_OBS = 30`). No methodology change was made during
  Stage 5. The longer-history expectation remains a documentation/specification reconciliation item.
- **Q-M2 — VaR / ES market-series interpretation.** `var_95` and `es_95` both consume the company/equity
  return leg; FX returns are isolated to `fx_volatility`; benchmark returns are used for `beta` only.
- **Q-C1 — inflation passthrough / margin-gap sign.** The gap is **signed**:
  `margin_gap = Δgross_margin − ΔCPI`. In the §8 table row the notation "|Δgross_margin|" is read as that
  signed difference, **not** as an absolute value.
- **Q-C2 (supporting decision).** `inflation_passthrough` requires 24 monthly CPI observations and
  `rate_environment` requires 60 FEDFUNDS observations; shorter histories report `MISSING_INPUT`.
- **Q-B4 (supporting decision).** Beta legs in different currencies raise `ValueError` instead of being
  converted inside the risk calculation.
