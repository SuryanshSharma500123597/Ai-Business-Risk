# Database Schema — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. PostgreSQL 16 (prod/demo) / SQLite (tests) via SQLAlchemy 2.0 + Alembic.
Types below are Postgres; SQLite fallbacks: `UUID→CHAR(32)`, `JSONB→JSON`, `NUMERIC→FLOAT`,
`TIMESTAMPTZ→TIMESTAMP`.

## 1. Conventions (frozen)

- **Primary keys:** `UUID` (gen_random_uuid()) for entity tables; `BIGINT GENERATED ALWAYS AS IDENTITY`
  for high-volume append-only tables (`agent_steps`, `llm_calls`, `guardrail_events`, `audit_log`,
  `source_fetch_log`).
- **Timestamps:** `TIMESTAMPTZ` UTC; `created_at TIMESTAMPSTZ NOT NULL DEFAULT now()`; `updated_at`
  where mutable. All application timestamps UTC.
- **Naming:** snake_case; tables plural; FKs `<entity>_id`; indexes on every FK; JSONB columns have
  GIN indexes only where queried (marked ◇).
- **Money:** `DOUBLE PRECISION` (float64 — consistent with engine; no arithmetic in SQL beyond sums).
- **Migrations:** Alembic only; no runtime DDL; `alembic upgrade head` in backend entrypoint.

## 2. Entity tables

**companies** — `id UUID PK` · `name TEXT NOT NULL` · `sector TEXT NOT NULL CHECK (in registry)` ·
`currency TEXT NOT NULL DEFAULT 'INR'` · `description TEXT` · `data_origin TEXT NOT NULL
CHECK (synthetic|manual|edgar)` · `generator_config JSONB ◇` (null unless synthetic) · `edgar_cik TEXT`
· timestamps.

**financial_periods** — `id UUID PK` · `company_id UUID FK→companies ON DELETE CASCADE` ·
`period_start DATE NOT NULL` · `period_end DATE NOT NULL` · `fiscal_year INT` · `quarter INT NULL` ·
`frequency TEXT NOT NULL CHECK (monthly|quarterly|annual)` · `source TEXT NOT NULL` ·
`UNIQUE(company_id, period_end, source)`.

**financials** — `id UUID PK` · `period_id UUID FK→financial_periods UNIQUE` · income statement:
`revenue, cogs, gross_profit, opex, ebitda, da, ebit, interest_expense, tax, net_income`
(`DOUBLE PRECISION`, nullable unless marked required in the coverage matrix) · balance sheet: `cash,
receivables, inventory, payables, current_assets, current_liabilities, total_assets, total_liabilities,
equity, total_debt, st_debt, lt_debt` · cash flow: `capex, ocf, fcf, dividends` · JSONB:
`customers JSONB` = `[{name_hash, share}]` · `suppliers JSONB` (same) · `products JSONB =
[{name, share}]` · `regions JSONB` (same) · `fx_exposure JSONB` = `{foreign_revenue_share,
import_cost_share}` · `commodity_exposure JSONB` = `{input, cost_share}` · `rate_exposure JSONB` =
`{floating_debt_share}` · `debt_schedule JSONB` = `[{bucket, amount}]` · `quality_flags JSONB`.

**Caches & provenance**

**market_cache** — `symbol TEXT` · `date DATE` · `close DOUBLE PRECISION` · `source TEXT` ·
`license_tag TEXT` · `PK (symbol, date, source)`.
**macro_cache** — `series_id TEXT` · `date DATE` · `value DOUBLE PRECISION` · `source TEXT` ·
`license_tag TEXT` · `PK (series_id, date, source)`.
**source_fetch_log** *(BIGINT id)* — `url TEXT` · `source TEXT` · `license_tag TEXT` · `fetched_at
TIMESTAMPTZ` · `checksum TEXT` · `status TEXT` · `detail JSONB`.

**aggregation_weights** — `id UUID PK` · `name TEXT NOT NULL` · `weights JSONB NOT NULL
CHECK (7 keys, each 0..1, sum=1)` · `is_default BOOLEAN` · `created_by UUID NULL` · timestamps.

## 3. Run & results tables

**analyses** — `id UUID PK` · `company_id FK` · `status TEXT NOT NULL CHECK (pending|running|
completed|failed|needs_review|cancelled)` · `config JSONB NOT NULL` (include_ml, scenario request,
budgets, seed) · `weights_id UUID FK NULL` · `seed INT` · `engine_version TEXT` ·
`registry_version TEXT` · `graph_version TEXT` · `input_snapshot JSONB` (reproducibility) ·
`started_at`, `finished_at TIMESTAMPTZ` · `error JSONB` · `INDEX (company_id, created_at)`.

**risk_assessments** — `id UUID PK` · `analysis_id FK` · `dimension TEXT NOT NULL` · `score DOUBLE
PRECISION NOT NULL` · `metric_scores JSONB` · `method_version TEXT` · `UNIQUE(analysis_id, dimension)`.

**risk_factors** — *(BIGINT id)* · `analysis_id FK` · `dimension TEXT` · `factor TEXT` · `value DOUBLE
PRECISION` · `score` · `severity TEXT` · `explanation TEXT` · `formula_id TEXT` · `INDEX (analysis_id)`.

**explanations** — `id UUID PK` · `analysis_id FK` · `layer TEXT CHECK (deterministic|shap|
counterfactual|narrative)` · `payload JSONB` · `caveats JSONB` · `INDEX (analysis_id, layer)`.

**scenarios** — `id UUID PK` · `analysis_id FK` · `name TEXT` · `type TEXT CHECK (preset|form|ai)` ·
`source_text TEXT` (AI mode) · `params JSONB NOT NULL` (validated) · `translation JSONB` (mapping
notes) · `status TEXT CHECK (validated|awaiting_confirmation|cancelled)` · `clamped JSONB` ·
timestamps.

**simulation_runs** — `id UUID PK` · `analysis_id FK NULL` · `scenario_id FK NULL` (null ⇒ baseline) ·
`is_baseline BOOLEAN` · `horizon_months INT` · `trajectories JSONB NOT NULL` (per-series arrays) ·
`kpis JSONB NOT NULL` · `params_snapshot JSONB NOT NULL` · `INDEX (analysis_id)`.

**stress_comparisons** — `id UUID PK` · `analysis_id FK` · `scenario_id FK` · `baseline_run_id FK →
simulation_runs` · `stressed_run_id FK` · `kpi_deltas JSONB` · `breaches JSONB` · `waterfall JSONB` ·
`dimension_deltas JSONB`.

**mitigations** — `id UUID PK` · `analysis_id FK` · `risk_factor_ref TEXT` · `library_id TEXT NOT
NULL` · `action TEXT` · `expected_effect JSONB` · `assumptions JSONB` · `trade_offs JSONB` ·
`confidence TEXT CHECK (low|medium|high)` · `verified_numbers BOOLEAN` · `status TEXT`.

**ml_artifacts** — `id UUID PK` · `company_id FK` · `model_version TEXT` · `model_type TEXT
(isolation_forest)` · `params JSONB` · `features JSONB` (feature list + ordering) · `metrics JSONB` ·
`trained_at TIMESTAMPTZ` · `artifact_path TEXT`.

## 4. Observability tables (append-only; BIGINT ids)

**agent_runs** — `id UUID PK` · `analysis_id FK` · `graph_version TEXT` · `started_at`, `ended_at` ·
`final_state JSONB` · `status TEXT`.

**agent_steps** — `id BIGINT PK` · `agent_run_id FK` · `seq INT NOT NULL` · `node TEXT` · `agent TEXT`
· `status TEXT` · `input_summary JSONB` · `output_summary JSONB` · `tool_calls JSONB` · `latency_ms
INT` · `error JSONB` · `INDEX (agent_run_id, seq)`.

**llm_calls** — `id BIGINT PK` · `agent_run_id FK` · `seq INT` · `provider TEXT` · `model TEXT` ·
`purpose TEXT` · `prompt_sha TEXT` · `response_sha TEXT` · `tokens_in INT` · `tokens_out INT` ·
`latency_ms INT` · `cost_estimate NUMERIC(10,6)` · `INDEX (agent_run_id, seq)`.

**guardrail_events** — `id BIGINT PK` · `agent_run_id FK` · `seq INT` · `rule TEXT` · `severity TEXT
CHECK (info|degrade|block)` · `action TEXT CHECK (allow|clamp|degrade|block|human_review)` · `detail
JSONB` · `INDEX (agent_run_id, seq)`.

**audit_log** — `id BIGINT PK` · `ts TIMESTAMPTZ NOT NULL DEFAULT now()` · `actor TEXT` · `action
TEXT` · `object_type TEXT` · `object_id TEXT` · `payload JSONB` · `INDEX (ts)` · append-only
(no UPDATE/DELETE grants in Phase 12 hardening).

**users** *(Phase 12)* — `id UUID PK` · `email TEXT UNIQUE NOT NULL` · `password_hash TEXT NOT NULL` ·
`role TEXT CHECK (analyst|admin)` · timestamps.

## 5. JSONB payload schemas

Structured JSONB columns are validated **at the application boundary** by the Pydantic models in
`backend/guardrails/schemas.py` before write (Postgres JSONB itself is schemaless by design). The
Pydantic models are the contract; this document fixes the column list. Key payload shapes:
`weights` = `{financial_strength, liquidity, market, credit, operational, concentration, macro}` (Σ=1);
`breaches` = `[{rule, metric, threshold, observed, periods}]`; `waterfall` =
`[{component, delta_ebitda}]` (components in frozen order, [simulation.md](simulation.md) §5).

## 6. Migration plan

Phase 2: core tables (`companies`, `financial_periods`, `financials`, caches, `source_fetch_log`,
`analyses` skeleton, `aggregation_weights`, `users` stub). Phase 10: results + observability tables
complete. Each phase's changes = one Alembic revision, reviewed in the phase report.
