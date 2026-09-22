# Data Architecture — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. Implements spec §25; licensing findings in
[phase-0-research.md](../00_research/phase-0-research.md) §7.

## 1. Canonical schema (frozen)

One company = many periods; one row per period in the **wide** `financials` table (JSONB for
distributional data). Field names below are the contract used by `risk_engine`, `simulation`, and the
API. Currency: values stored as float in the company's declared currency (see §5 decisions);
units = currency units (not thousands).

**Identity & calendar:** `company_id`, `period_start`, `period_end`, `fiscal_year`, `quarter`
( nullable for annual), `source`, `currency`.

**Income statement (monthly or annual native; normalized to period):**
`revenue`, `cogs`, `gross_profit`, `opex`, `ebitda`, `da` (depreciation & amortization), `ebit`,
`interest_expense`, `tax`, `net_income`.

**Balance sheet:** `cash`, `receivables`, `inventory`, `payables`, `current_assets`,
`current_liabilities`, `total_assets`, `total_liabilities`, `equity`, `total_debt`, `st_debt`,
`lt_debt`.

**Cash flow:** `capex`, `ocf` (operating cash flow), `fcf` (derived, nullable), `dividends` (nullable).

**Concentration buckets (JSONB, shares must sum to 1 — validated):**
`customers: [{name_hash, share}]`, `suppliers: [{name_hash, share}]`, `products: [{name, share}]`,
`regions: [{name, share}]`.

**Exposures (JSONB):** `fx_exposure: {foreign_revenue_share, import_cost_share}` (0–1),
`commodity_exposure: {input: str, cost_share: float}` (0–1), `rate_exposure: {floating_debt_share:
float}`, `debt_schedule: [{bucket: "0-3m|3-12m|1-3y|3y+", amount}]`.

**Name privacy:** customer/supplier names are hashed at ingestion (`name_hash`); raw names are never
stored (synthetic data uses fictional names anyway).

## 2. Source contracts (frozen)

| Source | Role | Access | Fields → canonical mapping | Throttle & cache | License tag |
|---|---|---|---|---|---|
| **synthetic** (primary) | full company datasets | in-repo generator (§4) | direct | none (local compute) | `synthetic` |
| **edgar** (secondary, optional) | real listed-company statements | official keyless XBRL `companyfacts` API, declared User-Agent | us-gaap tags → canonical (mapping table versioned in `data_engine/ingest/edgar_map.py`, e.g. `Revenues/RevenueFromContractWithCustomer→revenue`, `Assets→total_assets`) | ≤ **10 req/s** (hard cap 8 in code), cache JSON per CIK 24 h | `public-domain` |
| **fred** | macro series | official API + `FRED_API_KEY`; keyless `fredgraph.csv` fallback | `FEDFUNDS, CPIAUCSL, GDPC1, UNRATE, DEXINUS` (+ commodity series resolved in Phase 3) → `macro_cache` | ≥1 s between calls (official numeric limit unpublished — conservative fixed throttle); cache CSV/JSON per series 7 d | `attribution-required` |
| **stooq** (market primary) | daily OHLCV (indices, FX, commodities, stocks) | CSV URL pattern `q/d/l/?s=…&i=d` | close series → `market_cache` | ≥2 s between calls, cache per symbol 24 h | `personal-use-flagged` (no published license — see research §7.3) |
| **yahoo/yfinance** (market fallback) | same as stooq | unofficial Apache-2.0 library | same | ≥5 s between calls, cache 24 h, disabled when Stooq succeeds | `tos-restricted-flagged` (educational prototype use only) |
| **worldbank** | annual macro context | official API v2, no key | `NY.GDP.MKTP.KD.ZG`, `FP.CPI.TOTL.ZG` (+≤8 more) → `macro_cache` | 1 req/s, cache 30 d | `CC-BY-4.0` |

Cache layout: `data/raw/<source>/<key>.<ext>` + `data/raw/<source>/index.json` (url, fetched_at,
checksum, license_tag). Every ingestion writes a `source_fetch_log` row. **No third-party data is
committed to git** (`data/raw` is git-ignored).

## 3. Validation rules (frozen)

1. **Coverage matrix** — required concepts per analysis: `revenue, cogs, cash, current_assets,
   current_liabilities, total_assets, total_liabilities, equity, interest_expense` (required);
   `ebitda, ebit, net_income, receivables, inventory, payables, capex, ocf, concentration buckets,
   exposures` (optional — degrade the related dimensions, disclosed). Coverage % = required present /
   required total; **< 70% ⇒ run blocked** (`DATA_COVERAGE_LOW`).
2. **Accounting identities** (tolerance 0.5%): `total_assets = total_liabilities + equity`;
   `current_assets ≥ cash` and `≥ receivables`; `gross_profit ≈ revenue − cogs`; concentration shares
   sum to 1 (±0.01).
3. **Range checks**: shares ∈ [0,1]; margins ∈ [−1,1] warn outside [0,1]; growth clamped in twin per
   [simulation.md](simulation.md).
4. **Period sanity**: monotonic period ends; no duplicates; min 8 periods for ML features (else ML
   disabled with disclosure).
5. **Staleness**: market/macro older than cache TTL and offline ⇒ dimension degraded (disclosed), never
   silently substituted.
6. **Source validation**: every value row carries `source`; mixed-source periods flagged in coverage
   report.

## 4. Synthetic generator spec (frozen)

Deterministic, seeded (`numpy.random.default_rng(seed)`); output = canonical schema rows.

| Parameter | Values (defaults bold) | Notes |
|---|---|---|
| `sector` | **manufacturing**, retail, services_saas | drives margin/ CCC/ capex templates |
| `size` | small, **medium**, large | scales absolute figures |
| `health` | healthy, **stable**, stressed | drives margins/leverage/runway envelopes |
| `currency` | **INR** (see §5), USD, EUR | displayed + stored currency |
| `periods` | 12–**36** monthly or 3–**10** annual | mixes supported |
| `growth_drift` | ±[0–3%]/mo band | bounded trend |
| `seasonality` | on/**off** | retail default on |
| `concentration_profiles` | dispersed, **moderate**, concentrated | drives HHI 0.05–0.6 |
| `inject_anomalies` | none / **margin_collapse, receivable_spike, cost_explosion** (labelled) | for ML evaluation |
| `seed` | int (**canonical fixtures: 1001–1005**) | reproducibility R6 |

Calibration (Phase 3 task): sector template ranges checked against EDGAR-derived sector medians
(manufacturing/retail/services); documented as calibration notes, not claimed as statistical fitting.

## 5. Frozen decisions (resolves Phase 0 open questions)

| # | Decision |
|---|---|
| **FD-1 Currency** | Synthetic default **INR (₹)**; currency is a per-company attribute, fully configurable (USD/EUR supported). FX translation only when mixing sources (e.g., USD EDGAR company with INR display) uses `DEXINUS` as-of-period rate and is disclosed in the coverage report. |
| **FD-2 EDGAR scope** | EDGAR import **is in MVP scope (Phase 3)** as a *secondary, feature-flagged* path (`ENABLE_EDGAR=true` default off in dev). Rationale: keyless, public-domain, strengthens the research story with real filings. The synthetic path remains primary and the system must be fully functional offline (R4). |
| **FD-3 Confirm UX** | AI-translated scenarios **always** require explicit user confirmation (API `POST …/confirm`); form-based and preset scenarios run directly. Frozen in the API contract. |
