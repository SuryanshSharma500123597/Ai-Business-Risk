# AI Business Risk — Development Log

Running log of phases, decisions, and open questions. Newest phase at the top.

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
