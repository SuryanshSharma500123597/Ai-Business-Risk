# Phase 4 — Quantitative Risk Engine Completion Report

**Status:** Engineering complete — documentation closed at the Phase 4 closure audit; awaiting approval for Phase 5.  
**Stage 5:** D18–D21 approved and unchanged (see §6).  
**Scope:** Pure-function deterministic quantitative financial ratios, credit metrics, market exposure metrics, 0–100 risk scoring, exact additive contributions ($L_1$ explanation layer), and weight sensitivity analysis.

## 1. Objective

Deliver an auditable, deterministic, LLM-independent quantitative risk engine (`backend/risk_engine/`) transforming validated canonical financial data into:
```text
Raw quantitative metrics -> Metric validation/results -> Risk dimensions ->
Dimension scores -> Weighted composite score -> Risk contributions ->
Severity classification -> Sensitivity analysis
```

## 2. Scope Completed

- **Pure-function Risk Engine:** Created `backend/risk_engine/` package independent of FastAPI, LangGraph, LLM, or external database sessions.
- **Formula Registry:** Central registry (`registry.py`) holding 30+ metric definitions, band anchors, formula references, and versioning metadata (`registry_version = "1.0.0"`).
- **7 Risk Dimensions:** Implemented Financial Strength, Liquidity, Market Exposure, Credit, Operational, Concentration, and Macro.
- **Reference Models:** Implemented Altman Z-score variants (Z public manufacturer, Z′ private manufacturer, Z″ non-manufacturer) and Merton Distance-to-Default / Probability-of-Default reference calculations.
- **Scoring & Interpolation:** Piecewise-linear interpolation mapping raw metrics to 0–100 risk scores with score clamping and standard severity labeling (`Low`, `Moderate`, `High`, `Critical`).
- **Exact Additive Contributions:** Full mathematical reconciliation where metric contributions sum to dimension scores, and dimension contributions sum to composite risk score ($\sum C_d = S_{\text{composite}}$).
- **Sensitivity Analysis:** Weight perturbations ($\pm 20\%$) with exact weight re-normalization, score range determination, and Spearman rank stability evaluation.
- **Verification scaffolding:** 40 hand-computed metric fixtures (one per registry formula) enforced by a registry-walking coverage test, deterministic seeded property tests, golden composite-profile baselines for canonical seeds 1001–1005, and the validation notebook `notebooks/04_quantitative_risk/01_risk_formula_validation.ipynb`.

## 3. Specification Sections Followed

- `docs/01_architecture/risk-engine.md`
- `docs/master-project-specification.md` §17 (Quantitative Risk Engine)
- `Skills/MODEL_ROUTING_POLICY.md` (Critical tier deterministic logic)

## 4. Implemented Metrics Summary

| Dimension | Metrics Implemented |
|---|---|
| **Financial Strength** | Gross Margin, Operating Margin, Net Margin, ROA, ROE, Debt-to-Equity, Debt-to-EBITDA, Interest Coverage, DSCR |
| **Liquidity** | Current Ratio, Quick Ratio, Cash Ratio, Cash Runway (Months), Short-Term Obligation Coverage |
| **Market Risk** | Interest Rate Sensitivity, FX Exposure Score, Commodity Exposure Score, Revenue Volatility, Equity Volatility, Beta, VaR 95%, ES 95% |
| **Credit** | Days Sales Outstanding (DSO), Receivables Concentration (HHI), Receivable Trend, Altman Z-Score (Z/Z'/Z''), Merton DD/PD |
| **Operational** | Days Inventory Outstanding (DIO), Days Payables Outstanding (DPO), Cash Conversion Cycle (CCC), Supplier Concentration (HHI), Opex Rigidity, Single Source Flags |
| **Concentration** | HHI (Customers/Suppliers/Products/Regions), Top-1 Concentration (CR1), Top-3 Concentration (CR3) |
| **Macro** | Inflation Pass-Through, Interest Rate Environment Gap, Macro FX Volatility, GDP Sensitivity |

## 5. Missing Data Behavior

- Missing or invalid inputs (e.g. unobservable equity series for private firms) return explicit `MetricStatus.MISSING_INPUT` or `UNAVAILABLE` with `value=None` and `score=None`.
- Missing inputs are **never defaulted to zero**.
- Missing metrics are excluded from dimension score averages.
- Dimensions with zero available metrics are excluded from composite aggregation, and remaining available dimension weights are re-normalized proportionally.
- If **every** dimension is unavailable the composite score is `None` (no fabricated 50.0 "Moderate" result); `DimensionResult.weight` always reports the configured weight used for the run and `effective_weight` the re-normalized share actually applied.
- Stage 5: when market or macro inputs are absent the affected metrics report `MISSING_INPUT`/`UNAVAILABLE` (for example `beta` without a benchmark leg), never a synthesized value.

## 6. Stage 5 — D18–D21 Market/Macro Input Integration (approved)

Stage 5 closed the gap between the Phase 3 data pipeline and the Phase 4 engine **without changing any
metric formula, anchor, aggregation rule, or scoring methodology**.

**D18 — beta.** `beta` previously received one series twice (`calc_beta(series, series)`), which made the
degenerate result β = 1.0. The engine now calls the calculator with **two distinct typed legs**
(asset/equity returns and benchmark returns) and records both in `MetricResult.inputs_used`
(`asset_symbol`, `benchmark_symbol`, `asset_source`, `benchmark_source`, `joined_obs`). With only one leg
available — or through the deprecated `market_series` alias — beta is `UNAVAILABLE`/`MISSING_INPUT`,
never a fabricated 1.0.

**D19 — series separation.** `RiskEngineMarketInputs` carries separate `equity_returns`,
`benchmark_returns` and `fx_returns` legs. Volatility, VaR and ES read the equity leg only;
`fx_volatility` reads the FX leg only; beta reads equity + benchmark only. Series are log returns
`ln(P_t / P_{t−1})`; beta legs are inner-joined on shared dates (no forward fill).

**D20 — macro inputs.** `cpi_change_pct_24m`, `gross_margin_change_pp_24m`, `fedfunds_current`,
`fedfunds_trailing_5y_median` and `gdp_volatility` are pre-aggregated by the deterministic
`backend/data_engine` adapter and passed in as scalars, so the risk engine performs no HTTP, cache or SQL
access (architecture R3). No macro input ⇒ the macro metrics report `MISSING_INPUT`, never zero.

**D21 — weights contract preparation only.** `WeightsRef` (`weights_id`, `version`, weights summing to 1)
is accepted as a carried value. Persistence, repositories, API surface and `analyses.weights_id` writes
are **deferred to Phase 10**; Stage 5 performs no database writes.

**Frozen minimums and guardrails** (`backend/risk_engine/contracts.py`): `MIN_BETA_ALIGNED_OBS = 120`,
`MIN_VAR_ES_OBS = 60`, `MIN_VOL_OBS = 30`, `MIN_CPI_MONTHS = 24`, `MIN_FEDFUNDS_MONTHS = 60`.
Mixed-currency beta legs raise `ValueError` instead of silently converting FX (approved Q-B4), and
`market_inputs` and `market_series` are mutually exclusive.

**New files:** `backend/risk_engine/contracts.py` additions (`AlignedSeries`, `SeriesProvenance`,
`RiskEngineMarketInputs`, `WeightsRef`, minimums), `backend/data_engine/market_inputs.py`,
`backend/data_engine/macro_inputs.py`, `backend/data_engine/risk_inputs.py`, four Stage 5 test modules
and `notebooks/04_quantitative_risk/02_stage5_market_inputs_validation.ipynb`.

## 7. Verification Results (at documentation closure)

All gates were run in the project virtual environment (Python 3.12) after Stage 5:

| Gate | Result |
|---|---|
| Test suite (`pytest -q`) | **223 passed** (196 pre-Stage-5 baseline + 27 Stage 5 tests) |
| `risk_engine` coverage | **94%** line coverage (NFR3 target ≥ 80%) |
| Registry coverage | **40/40** registry formulas each have a hand-computed fixture |
| Contribution reconciliation | **5/5**, `abs_tol = 1e-9` |
| Golden baselines (seeds 1001–1005) | **5/5** matches |
| Ruff (`ruff check backend scripts`) | **clean** — "All checks passed!" |
| Ruff format (`ruff format --check backend scripts`) | **clean** — 87 files already formatted |
| Ruff over notebook cells (`ruff check .`) | 19 findings in the 3 notebooks (E402/I001/E501 from the intentional `sys.path` bootstrap in their setup cells) — recorded known condition, not a code-target failure |
| Mypy (`mypy backend`) | **Success: no issues found** (83 files) |
| Phase 4 notebook (fresh kernel) | **PASSED** — `01_risk_formula_validation.ipynb` |
| Stage 5 notebook (fresh kernel) | **PASSED** — `02_stage5_market_inputs_validation.ipynb` |
| Determinism | repeated evaluations produce identical composite scores/severities |

Test layout: `backend/tests/unit/` (formula fixtures, registry coverage, routing, adapters),
`backend/tests/property/` (seeded invariants), `backend/tests/golden/` (composite baselines).

## 8. Corrections made during the Phase 4 audit/remediation ("Category A")

The engine was implemented first and then audited against the frozen specification. The corrections below
were applied during that audit, and each one is asserted by a named test. **No financial methodology
beyond these approved corrections was introduced.**

| # | Correction | Asserted by |
|---|---|---|
| D2 | `altman_z_distance` maps linearly to 100 below the distress cut-off instead of clamping artificially | `test_fixture_altman_z_distance` |
| D3 | Each Altman variant keeps its own cut-offs (Z vs Z′ vs Z″); original-Z thresholds are never reused | `test_altman_variant_cutoff_mapping` |
| D9 | An entirely-missing profile no longer fabricates a 50.0 "Moderate" composite — the composite score is `None` | `test_all_missing_dimensions_yields_no_fabricated_composite` |
| D10 | `DimensionResult.weight` reports the configured weight actually used for the run, alongside the re-normalized `effective_weight` | `test_configured_weight_is_reported_alongside_effective_weight`, `test_effective_weight_renormalises_over_available_dimensions` |
| D11 | Every metric, dimension and composite output is stamped with `registry_version` | `test_every_formula_output_is_version_stamped` |
| D12 | Anchor clamping applies at the endpoints as well as between anchors (scores always stay in 0–100) | `test_interpolate_score_clamps_out_of_range_anchors` |

### Corrected historical claims

- The first draft of this report claimed "100% formula fixture coverage" and "property-based invariant
  tests via **Hypothesis**". Hypothesis is **not** installed and is not a project dependency; the
  property tests use deterministic seeded randomization (`random.Random(42)`). The corrected statement is
  40 hand-computed fixtures enforced against the registry by a walking test, plus seeded property tests.
- The first draft recorded "Limitations & Deviations: none". Deviations and interpretation decisions do
  exist and are recorded in §9.
- Golden baselines for seeds 1001–1005 exist as JSON in `backend/tests/golden/` and are compared with
  `abs_tol = 1e-9`, regenerated only through `pytest --regen-golden` with a reviewed diff (testing.md §4).
  They are currently **untracked in git**, together with the rest of Phase 4: "golden files exist" is true
  of the working tree, not of any committed revision.
- Notebook execution is claimed only for the two Phase 4 notebooks that were actually executed
  (`01_risk_formula_validation.ipynb`, `02_stage5_market_inputs_validation.ipynb`), both from a fresh kernel.

## 9. Recorded specification ambiguities / approved interpretations

These items are **recorded, not silently changed**. The implementation is retained as approved; changing
any of them is a new, separately-approved work item.

**Q-M1 — volatility observation floor.** The frozen specification states a longer-history expectation,
while the approved implementation uses a **30-observation** floor (`MIN_VOL_OBS = 30`) for
`equity_volatility` and `fx_volatility`. *Current implementation: 30 observations. No methodology change
was made during Stage 5.* The longer-history requirement remains a documentation/specification
reconciliation item, and a future change requires explicit approval before implementation.

**Q-M2 — VaR / ES market-series interpretation.** Approved Stage 5 reading: `var_95` uses
company/equity returns and `es_95` uses company/equity returns — the **same equity-return leg**; FX
returns are isolated to `fx_volatility`; benchmark returns are used **for beta only**. No formula was
modified.

**Q-C1 — inflation passthrough / margin-gap sign.** The approved implementation preserves a **signed**
gap, `margin_gap = Δgross_margin − ΔCPI` (percentage points) — not an absolute difference. The
calculation was not changed.

**Q-C2 (supporting decision)** — `inflation_passthrough` requires 24 monthly observations and
`rate_environment` requires 60 FEDFUNDS observations; shorter histories report `MISSING_INPUT`.

**Q-B4 (supporting decision)** — asset and benchmark legs in different currencies raise `ValueError`
rather than being converted inside the risk calculation.

**Q-A1 / Q-W1** — `RiskEngineMarketInputs` is fully optional (private/offline companies leave listed-only
legs empty and receive the existing `UNAVAILABLE`/`MISSING_INPUT` statuses), and `WeightsRef` is contract
preparation only.

## 10. Deferred to later phases

- `AggregationWeights` persistence, a weights API and `analyses.weights_id` writes — **Phase 10**
  (`WeightsRef` exists only as a carried contract).
- Series-selector UI and any user-facing choice of benchmark/FX series — **Phase 11**.
- ML anomaly detection, digital twin, scenario engine, stress testing, LangGraph agents, full API and
  frontend — their own phases; none of them exist yet.

## 11. Limitations

- The engine is deterministic and unit-verified, but it has not yet been validated against real audited
  financial statements or an external risk benchmark.
- Environment/macro metrics depend on caller-supplied cached series; without them the metrics report
  `MISSING_INPUT`/`UNAVAILABLE` rather than defaulting to a value.
- Merton DD/PD remains reference-only and off by default (market value of assets and its volatility are
  unobservable).
- `backend/risk_engine/`, its tests, the golden baselines and the Stage 5 adapter layer are currently
  untracked in git; no commit was created during this closure task.

---

**PHASE 4 ENGINEERING-COMPLETE — DOCUMENTATION CLOSED — WAITING FOR USER APPROVAL.**  
**Next phase after approval: PHASE 5 — ML ENGINE.**
