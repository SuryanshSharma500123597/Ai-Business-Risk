# AI Business Risk — Master Project Specification (Phase 0)

**Project:** AI Business Risk — Autonomous Multi-Agent Business Risk Intelligence & Stress Testing Platform
**Status:** Phase 0 deliverable — **approved**. All contracts are frozen in the Phase 1 documents
(see `docs/`: architecture, agents, data, risk-engine, simulation, api, database, requirements,
testing). No application code exists yet.
**Companion document:** [phase-0-research.md](00_research/phase-0-research.md) (all external claims, citations, and licensing verdicts live there; accessed 2026-09-21).

## Locked architecture decisions (approved before this specification)

| # | Decision |
|---|---|
| D1 | **LLM layer:** GLM-5.3-Flash as the *temporary development model*, behind a **provider-agnostic LLM abstraction** (interface + adapters returning LangChain chat models). Swappable to OpenAI / Gemini / Claude / local (Ollama) without changing LangGraph agents or core logic. **All financial/risk computation is deterministic and LLM-independent.** |
| D2 | **Data strategy:** Hybrid — deterministic synthetic company generator (primary, seeded) + real macro series (FRED, World Bank) + market series (Stooq primary with terms caveat, yfinance fallback, both cached & throttled) + optional SEC EDGAR real-filings import. |
| D3 | **Frontend (Phase 11):** React + Vite + TypeScript; ECharts/Recharts; GSAP + ScrollTrigger; Motion; built with the UI UX Pro Max, Taste, and GSAP skills — a premium production-quality responsive dashboard, not a generic admin template. |
| D4 | **ML scope:** Focused — one anomaly-detection model (Isolation Forest) over engineered financial-ratio features + SHAP explainability, with a rule-based baseline and a full evaluation protocol. |
| D5 | **Roadmap:** 15 phases numbered **0–14** (see §36). Each phase ends with an explicit approval gate. |

---

## 1. Executive Summary

Businesses assess risk with fragmented tooling: qualitative GRC registers, static ratio dashboards,
disconnected spreadsheets, and — increasingly — ad-hoc LLM chats that cannot be trusted with numbers.
Regulatory-grade stress testing (BCBS 2018 principles; the Fed's DFAST/CCAR programs) demonstrates what
mature scenario analysis looks like, but is designed for bank capital, not for a general business.

**AI Business Risk** is an open, reproducible decision-support platform that produces a
multi-dimensional, explainable risk profile for a single business and propagates user-defined or
AI-translated scenarios through a **deterministic business digital twin** (income statement → cash flow
→ liquidity), comparing stressed outcomes against baseline. A **supervisor–specialist multi-agent
system (LangGraph)** orchestrates the workflow, but every number originates from deterministic
engines: a quantitative risk engine (ratios, coverage, market exposure, concentration), an ML anomaly
detector with SHAP attribution, and the digital twin. Guardrails verify schemas, bounds, permissions,
loop/timeout budgets, and — critically — **that every numeric claim an LLM emits matches a computed
value**. Structured traces make the entire run auditable, and the frontend presents profiles,
scenario labs, stress comparisons, explanations, mitigations, and the agent trace.

The research contribution is the *integrated, evaluated architecture* — deterministic-grounded agents
+ digital-twin stress propagation + guardrailed numerical faithfulness + layered explainability —
benchmarked against four baselines (rule-based ratios, standalone ML, single LLM analyst, unguarded
multi-agent). It is a B.Tech major project: research-backed, demonstrable, and honest about limits.

## 2. Simple Project Explanation

A user provides (or generates) a company's financial statements and context. The system then:

```text
BUSINESS DATA → VALIDATION → RISK DETECTION → QUANTIFICATION → EXPLANATION
   → SCENARIO GENERATION → STRESS TESTING → IMPACT SIMULATION
   → MITIGATION ANALYSIS → GUARDRAIL VALIDATION → REPORT → MONITORING
```

Concretely: upload/generate financials → the platform computes ratios and risk scores, flags anomalies
(ML), and explains the drivers. The user asks in natural language: *“What happens if revenue falls 15%
and interest rates rise 2%?”* An LLM translates that into a bounded JSON scenario
(`{"revenue_change": -0.15, "interest_rate_change_pp": 2.0}`) — the **deterministic twin** then
simulates month-by-month effects on revenue, margins, cash, and liquidity, and the platform reports
the deltas, breached thresholds, and which risks got worse, with suggested mitigations and a full
audit trace. The LLM never performs a calculation.

## 3. Real-World Problem

Rigorous problem statement (not “businesses need AI”):

1. **Fragmented risk analysis** — liquidity, leverage, market exposure, concentration, and macro
   sensitivity are computed in different tools (or not at all), with no unified profile.
2. **Heterogeneous data** — statements, market series, and macro indicators come in different schemas,
   frequencies, and licenses; there is no small-scale pipeline that validates and joins them safely.
3. **Static assessment** — periodic ratio snapshots age quickly; risk is a *trajectory*, not a photo.
4. **No scenario interaction** — managers cannot cheaply ask “what if revenue falls 20%?” and get a
   financially consistent, audited answer.
5. **Limited stress propagation** — tools that do shock one input rarely propagate it through margins,
   working capital, debt service, and cash to show second-order effects.
6. **Disconnected AI tools** — LLMs produce fluent but ungrounded analysis; ML models produce scores
   without integration into decision workflows.
7. **No auditable agent workflows** — when agents are used, their steps, tool calls, and data lineage
   are usually invisible, so results cannot be trusted or reproduced.
8. **Explainability debt** — even where scores exist, “why did risk increase?” is unanswered, and
   correlation is routinely presented as causation.

## 4. Target Users

| User | Primary need | How the platform serves them |
|---|---|---|
| Risk analyst | consolidated risk view + drivers | dimension scores, drivers, explanations, trace |
| Financial analyst / CFO team | scenario & stress answers | scenario lab, stress comparison, breach flags |
| Business manager / SME owner | “what should I worry about?” | plain-language report, mitigations |
| Enterprise risk team | evidence for ERM process (ISO 31000 assessment step) | reproducible, auditable assessments |
| Investment analyst | downside sensitivity of a company | stress tests, concentration metrics |
| Academic / researcher | reproducible evaluation testbed | seeded data, baselines, metrics, traces |

**Positioning (explicit):** decision-support and research platform. It does **not** replace
professional risk teams, is **not** investment/financial advice, and all outputs carry that disclaimer.

## 5. Existing Systems

Summarized here; full verified analysis with citations in [phase-0-research.md](00_research/phase-0-research.md) §3.

| Category | Verified examples | Core function |
|---|---|---|
| ERM / GRC platforms | MetricStream, ServiceNow IRM, Archer, LogicGate Risk Cloud | registers, workflows, compliance, audit |
| Financial analytics | Bloomberg Terminal, FactSet, S&P Capital IQ Pro, Moody's | market/company data, analytics, credit platforms |
| BI dashboards | Power BI, Tableau, Looker | visualization/distribution of computed metrics |
| Credit-risk systems | Moody's CreditLens/Lending Suite; Altman Z / Merton methodology | default-risk scoring & workflows |
| AI/ML risk systems | vendor-embedded ML & GenAI (credit workflows, “AI-powered insights”) | narrow, closed, opaque |
| LLM business analysis | direct LLM chat; BloombergGPT, FinGPT, FinRobot | fluent analysis; markets/trading focus |
| Multi-agent frameworks | LangGraph, AutoGen/AG2, CAMEL, MetaGPT | general-purpose agent orchestration |
| Simulation/stress practice | BCBS stress-testing principles; Fed DFAST/CCAR; scenario/sensitivity analysis | severe-scenario methodology for banks |

## 6. Limitations of Existing Approaches

1. **GRC:** qualitative registers; no statement-level quantification or stress propagation (§3.1).
2. **Terminals/data platforms:** cost; closed; analyst-facing tools, not autonomous end-to-end risk
   analysis for one business (§3.2).
3. **BI:** renders what upstream computes; no reasoning or simulation (§3.3).
4. **Credit systems:** single-dimension, periodic, static; no whole-business scenario view (§3.4).
5. **Industry AI:** opaque, narrow, non-reproducible (§3.5).
6. **LLM analysts:** ungrounded numerics; market/trading focus; no deterministic stress engine
   (§3.6).
7. **General agent frameworks:** orchestration only; no domain grounding, guardrails, or evaluation
   harness for business risk (§3.7).
8. **Regulatory stress testing:** bank-capital-centric; no open reference implementation for general
   businesses (§5).

## 7. Proposed Solution

A monorepo platform with five cooperating layers (all deterministic except the LLM reasoning layer):

```text
┌────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (React+Vite+TS, ECharts, GSAP/Motion) — Phase 11             │
├────────────────────────────────────────────────────────────────────────┤
│  API LAYER (FastAPI, SSE progress, auth — Phase 10/12)                 │
├────────────────────────────────────────────────────────────────────────┤
│  REASONING LAYER — LangGraph multi-agent system (Phase 9)              │
│   supervisor → specialists → deterministic aggregator →                │
│   scenario agent → [deterministic stress engine] → mitigation →        │
│   report agent → numeric-verification guardrail                        │
│   • provider-agnostic LLM adapters (GLM-5.3-Flash dev default, D1)     │
│   • permissioned tool access; every tool call traced                   │
├────────────────────────────────────────────────────────────────────────┤
│  DETERMINISTIC ENGINES                                                 │
│   • Quantitative Risk Engine (ratios, coverage, exposure,              │
│     concentration, scoring) — Phase 4                                  │
│   • ML Engine (Isolation Forest anomaly detection + SHAP) — Phase 5    │
│   • Business Digital Twin + Scenario + Stress engines — Phases 6–8     │
├────────────────────────────────────────────────────────────────────────┤
│  DATA ENGINE (ingestion, validation, normalization, caching) — Ph.3    │
│   synthetic generator • FRED • World Bank • Stooq/yfinance • EDGAR opt.│
├────────────────────────────────────────────────────────────────────────┤
│  DATABASE (PostgreSQL + SQLAlchemy/Alembic) • OBSERVABILITY • AUDIT    │
└────────────────────────────────────────────────────────────────────────┘
```

**Non-negotiable LLM responsibility principle (from the project mandate):**

```text
LLM → interpretation → structured request → deterministic tool → validated result → LLM interpretation
```

The LLM never performs financial arithmetic, portfolio/risk calculations, numerical simulation,
database writes, or policy enforcement. Where the LLM emits numbers (reports, mitigations), a
deterministic verifier checks each number against engine outputs and blocks/regenerates on mismatch.

## 8. Research Gap

(G1–G5 with citations in [phase-0-research.md](00_research/phase-0-research.md) §9.)

- **G1** Financial-agent research targets markets/trading, not whole-business risk + stress.
- **G2** GRC platforms are qualitative; terminals are analyst-facing; neither propagates shocks
  through a firm's financials.
- **G3** Regulatory stress testing is bank-centric with no open general-business reference.
- **G4** Ungrounded LLM numerics; multi-agent reliability is an open challenge; no adopted open system
  machine-verifies LLM-emitted numbers against a deterministic engine.
- **G5** Explainability is fragmented; risk support needs layered explanation (deterministic
  contribution, model attribution, scenario counterfactual) kept distinct from narrative.

## 9. Research Questions

- **RQ1 (Faithfulness):** Can a supervisor–specialist LLM agent system, constrained to deterministic
  tools, produce risk assessments whose numerical content is 100% consistent with a purely
  deterministic pipeline, and what guardrail design achieves this (measured invalid-call rate,
  verification-failure rate)?
- **RQ2 (Value over baselines):** Does the combined multi-agent + digital-twin system identify and
  rank risk drivers and scenario impacts more accurately/consistently than (B1) rule-based ratio
  analysis, (B2) standalone ML, and (B3) a single LLM analyst?
- **RQ3 (Guardrail cost/benefit):** How do guardrails (permissions, bounds, loops, verification)
  affect agent reliability, latency, and task completion versus the unguarded configuration (B4)?
- **RQ4 (Sensitivity):** How sensitive is the aggregated risk score to aggregation-weight choices, and
  how should weight sensitivity be reported to users honestly?
- **RQ5 (Propagation):** How faithfully does the deterministic twin propagate single- and multi-factor
  shocks (monotonicity, conservation, reproducibility properties)?

## 10. Hypothesis

- **H1:** With deterministic tools + verification guardrails, the agent system achieves ≥95% valid
  tool calls and ≥99% numeric-consistency in final outputs, versus materially lower for the
  unguarded single-LLM baseline (B3).
- **H2:** The combined system's scenario-impact estimates (direction and relative magnitude of KPI
  changes) match the deterministic reference implementation exactly (by construction) and are rated
  more useful/consistent by structured rubric than baselines.
- **H3:** Guardrails reduce invalid tool calls and hallucinated numbers substantially (target: to
  zero emitted unverified numerics) at a modest, quantified latency/token cost.

*Results will be measured in Phase 13; nothing is claimed in advance.*

## 11. Objectives

- **O1** Build a validated data engine (synthetic generator + FRED/World Bank/Stooq ingestion with
  licensing-safe caching).
- **O2** Implement a fully tested deterministic quantitative risk engine (formula registry with
  documented assumptions).
- **O3** Implement a focused, evaluated ML anomaly-detection layer with SHAP explanations and a
  rule-based baseline.
- **O4** Implement a deterministic business digital twin and scenario/stress engines with bounded,
  validated scenario schemas.
- **O5** Implement the LangGraph multi-agent system with permissioned tools, retries, and guardrails.
- **O6** Integrate into a FastAPI backend with a PostgreSQL store, full trace/audit persistence.
- **O7** Build the approved premium React frontend (dashboard, scenario lab, stress comparison,
  explanations, mitigations, agent trace, audit).
- **O8** Evaluate honestly against the four baselines and produce the research documentation.

## 12. Scope

**In scope:** single-company analysis; 7 risk dimensions (financial strength, liquidity, market/
external-price exposure, credit, operational, concentration, macro); monthly-horizon deterministic
simulation (≤36 months); scenario creation (UI form / presets / NL→JSON); stress comparison; anomaly
detection + SHAP; mitigation suggestions from a curated library; agent trace + audit; REST API +
SSE; PostgreSQL persistence; auth added in Phase 12; Docker Compose deployment for demo.

**Functional requirements (FR):**

| ID | Requirement |
|---|---|
| FR1 | Ingest company financials (synthetic generator or manual/EDGAR import) with validation report |
| FR2 | Compute all registry ratios/metrics with documented definitions & versions |
| FR3 | Produce 7-dimension risk profile with configurable weights + sensitivity report |
| FR4 | Detect anomalies (ML) with SHAP feature attribution + rule baseline comparison |
| FR5 | Create scenarios via form, presets, or natural language (validated, bounded, user-confirmed) |
| FR6 | Run baseline vs scenario twin simulation; report KPI deltas + threshold breaches + waterfall |
| FR7 | Generate mitigation candidates (risk, action, expected direction, assumptions, trade-offs, confidence) |
| FR8 | Produce final report whose every number is machine-verified against engine outputs |
| FR9 | Persist and expose full agent/tool/LLM/guardrail trace and audit log |
| FR10 | Stream analysis progress (SSE) and expose results via REST API |

**Non-functional requirements (NFR):**

| ID | Requirement |
|---|---|
| NFR1 | Determinism: same inputs + seed ⇒ identical engine/twin outputs (LLM temperature 0 for structured steps) |
| NFR2 | Correctness: 100% of engine formulas covered by hand-computed fixture tests |
| NFR3 | Test coverage ≥80% on `risk_engine`, `simulation`, `data_engine`, `guardrails` modules |
| NFR4 | Analysis run completes < 5 min p95 on a laptop-class machine (LLM latency dominated) |
| NFR5 | All third-party data cached with source/license/timestamp; no redistribution |
| NFR6 | Secrets only via environment; no secrets in code or docs |
| NFR7 | Code typed (mypy where practical), linted (ruff), documented, understandable to a B.Tech student |
| NFR8 | Every phase leaves docs + development log updated |

## 13. Out-of-Scope

- Real-time data streaming / live trading anything.
- Regulatory compliance certification (this is not a regulated system).
- Monte Carlo / stochastic simulation, reverse stress testing (future scope).
- Portfolio/multi-company comparison analytics (single-company focus for MVP).
- Fine-tuning any LLM; training models beyond the focused anomaly detector.
- Production-grade multi-tenant SaaS hardening (RBAC beyond two roles, SSO, K8s).
- Tax optimization, accounting-standard legal advice, or guaranteed-accuracy forecasts.
- Mobile native apps.

## 14. Core Features

| # | Feature | Phase |
|---|---|---|
| F1 | Company profile + statements ingestion with validation report | 3 |
| F2 | 7-dimension risk scoring with explainable, configurable aggregation | 4 |
| F3 | Anomaly detection (Isolation Forest) + SHAP drivers + rule baseline | 5 |
| F4 | Business digital twin: monthly P&L → cash → liquidity propagation | 6 |
| F5 | Scenario engine: presets, form-based, NL→JSON (bounded, confirmed) | 7 |
| F6 | Stress testing: baseline vs scenario deltas, breaches, EBITDA waterfall | 8 |
| F7 | Multi-agent analysis with permissioned tools and full trace | 9 |
| F8 | Backend API + job model + SSE progress | 10 |
| F9 | Premium dashboard, scenario lab, explanations, mitigation, trace, audit views | 11 |
| F10 | Auth, security hardening, observability (logs/metrics/traces) | 12 |
| F11 | Baseline & ablation experiment suite with measured results | 13 |
| F12 | Final documentation, demo script, viva pack | 14 |

## 15. System Modules

| Module | Status | Purpose | Phase |
|---|---|---|---|
| Data engine (ingest/validate/normalize/cache) | **Core** | safe, licensed, validated inputs | 3 |
| Quantitative risk engine | **Core** | all deterministic financial math | 4 |
| ML engine (anomaly + SHAP) | **Core** | unusual-pattern detection + attribution | 5 |
| Business digital twin | **Core** | deterministic business simulation | 6 |
| Scenario engine | **Core** | schema, presets, NL translation, bounds | 7 |
| Stress engine | **Core** | baseline vs scenario comparison | 8 |
| Multi-agent system (LangGraph) | **Core** | orchestration + specialist analysis | 9 |
| Guardrail engine | **Core** | validation, permissions, verification | 9 (used from 3) |
| Backend API | **Core** | contracts for frontend | 10 |
| Database layer | **Core** | persistence + audit | 2 (schema), 10 (integration) |
| LLM abstraction | **Core** | provider-agnostic adapters | 9 |
| Frontend | **Core** | decision-support UI | 11 |
| Observability (logs/metrics/traces) | **Supporting** | run visibility + eval data | 12 |
| Security (auth, hardening) | **Supporting** | demo-grade authN/Z | 12 |
| Evaluation harness (baselines/ablations) | **Core (research)** | measured comparisons | 13 |
| Monitoring/alerting daemon, scheduler | Future | continuous monitoring loop | future |
| Monte Carlo, reverse stress testing | Future | distributional methods | future |
| Multi-company portfolio view | Future | — | future |

## 16. Multi-Agent Architecture

```text
                        ┌──────────────┐
                        │  SUPERVISOR  │  (LLM; routing/planning only; no compute tools)
                        └──────┬───────┘
        ┌─────────────────┬────┴────────────┬──────────────────┐
        ▼                 ▼                 ▼                  ▼
 ┌─────────────┐   ┌─────────────┐   ┌──────────────┐  ┌─────────────┐
 │ Financial   │   │ Market &    │   │ Operational  │  │ Macro       │
 │ Risk Agent  │   │ Price Agent │   │ Agent        │  │ Agent       │
 └──────┬──────┘   └──────┬──────┘   └──────┬───────┘  └──────┬──────┘
        └─────────────────┴────────┬────────┴─────────────────┘
                                   ▼
                    ┌────────────────────────────┐
                    │ RISK AGGREGATOR (deterministic node — no LLM)
                    │ + ML anomaly findings       │
                    └──────────────┬─────────────┘
                                   ▼
                    ┌────────────────────────────┐
                    │ SCENARIO AGENT (LLM; NL→JSON; bounds-checked)  │
                    └──────────────┬─────────────┘
                                   ▼
                    ┌────────────────────────────┐
                    │ STRESS TEST ENGINE (deterministic node)        │
                    └──────────────┬─────────────┘
                                   ▼
                    ┌────────────────────────────┐
                    │ MITIGATION AGENT (LLM; library-grounded)       │
                    └──────────────┬─────────────┘
                                   ▼
                    ┌────────────────────────────┐
                    │ REPORT AGENT (LLM) → NUMERIC VERIFIER (guardrail)│
                    └────────────────────────────┘
```

**Agent contract table** (tools are deterministic wrappers; permissions enforced by the tool registry):

| Agent | LLM? | Responsibility | Allowed tools | Inputs | Outputs (state keys) |
|---|---|---|---|---|---|
| Supervisor | yes | plan sequence, delegate, detect incompleteness; max 2 replanning rounds | `get_run_status` | state summaries | `plan`, `next_agent` |
| Financial Risk Agent | yes | interpret financial-strength & credit signals; flag drivers | `get_financials`, `compute_ratios`, `compute_altman_z` | validated financials | `findings.financial`, `findings.credit` |
| Market & Price Agent | yes | interpret rate/FX/commodity exposure; (listed mode) vol/beta/VaR | `get_market_series`, `compute_market_risk`, `get_fx_commodity_exposure` | financials, market cache | `findings.market` |
| Operational Agent | yes | interpret efficiency, supplier/ops fragility | `compute_efficiency_metrics`, `get_operations_profile` | financials, ops profile | `findings.operational` |
| Macro Agent | yes | interpret macro context relevance | `get_macro_series` | macro cache | `findings.macro` |
| Risk Aggregator | **no** | compute 7 dimension scores + composite + contributions + ML flags | (internal engine calls) | ratios, ML output | `dimension_scores`, `composite_score`, `contributions` |
| Scenario Agent | yes | NL→scenario JSON; choose/parametrize presets | `validate_scenario`, `list_presets` | user text/form | `scenario` (validated) |
| Stress Test Engine | **no** | run twin baseline vs scenario; deltas; breaches; waterfall | (internal) | twin params + scenario | `simulation_baseline`, `simulation_stressed`, `stress_comparison` |
| Mitigation Agent | yes | map risk factors → curated mitigation library entries, with trade-offs | `get_risk_profile`, `search_mitigation_library` | scores, factors, scenario results | `mitigations` |
| Report Agent | yes | compose final report strictly from the structured result pack | `get_result_pack` | full state | `report` |
| Numeric Verifier | **no** | extract numbers from report/mitigations; compare to pack (tolerance) | — | report text + pack | `verification` (pass/fail + mismatches) |
| Guardrail Nodes | **no** | schema/bounds/permission/loop/timeout checks between steps | — | step I/O | `guardrail_events` |

**State transitions & control:**

1. `START → validate_data` (deterministic; fails fast with coverage report).
2. `validate_data → supervisor` → fan-out to the four specialists (sequential execution is fine on
   LangGraph; parallelism is an implementation detail) → fan-in → `ml_anomaly` (deterministic) →
   `aggregator` (deterministic).
3. `supervisor` reviews completeness; may loop back **once** (max 2 planning rounds) with targeted
   requests; further loops raise a guardrail event.
4. If a scenario is requested: `scenario_translator → guardrail_scenario_bounds → [human confirmation
   interrupt (required for AI-translated scenarios; form-based scenarios run directly)] → stress_engine`.
5. `mitigation → report → numeric_verifier`; on verification failure: regenerate (≤2 attempts) then
   flag `human_review`.
6. Every node writes an `agent_steps` row; every LLM call an `llm_calls` row; every violation a
   `guardrail_events` row. On any fatal error the run halts with a structured error state — the system
   never silently fabricates completion.

**Failure semantics:** tool error → error fed back to the calling agent (max 2 retries) then the
affected finding is marked degraded (never invented); guardrail block → step skipped or run halted
per severity; all visible in the trace.

---

## 17. Quantitative Risk Engine

A pure-function, dependency-light Python package (`backend/risk_engine`). Every formula lives in a
**formula registry** with: id, definition, inputs (with units/currency), assumptions, implementation
reference, threshold bands, and validation method. Standard definitions from
[phase-0-research.md](00_research/phase-0-research.md) §6.

### 17.1 Registry (core formulas)

| Formula | Inputs | Assumptions / notes | Validation |
|---|---|---|---|
| Current Ratio | CA, CL | point-in-time balance sheet | hand-computed fixture |
| Quick Ratio | CA, inventory, CL | excludes inventory | fixture |
| Cash Ratio | cash, CL | most conservative liquidity | fixture |
| Debt-to-Equity | total debt, equity | debt = ST + LT interest-bearing | fixture |
| Debt-to-EBITDA | total debt, EBITDA | guard: EBITDA ≤ 0 → score capped at worst, flagged | fixture + edge case |
| Interest Coverage | EBIT, interest expense | interest > 0 required; ≤0 EBIT → worst band | fixture |
| DSCR | EBITDA, interest, current portion LTD | covenant-style metric | fixture |
| Gross/Operating/Net Margin | GP/EBIT/NI, revenue | — | fixtures |
| ROA / ROE | NI, assets / equity | avg or ending balances (documented choice: ending) | fixtures |
| DSO / DIO / DPO / CCC | AR, inventory, AP, revenue, COGS | 365-day convention | fixtures |
| Cash Runway (months) | cash, avg monthly burn | burn = max(0, −trend OCF); positive OCF → `n/a` (not constrained) | fixtures |
| ST Obligation Coverage | cash, CL | proxy when facilities unknown | fixture |
| Annualized Volatility | daily log returns | √252 scaling; min window 60 obs | fixture vs numpy |
| Beta | asset returns, index returns | configurable index/window | fixture |
| Historical VaR / ES | return distribution | α configurable (default 95%); reported as positive loss | fixture vs quantile |
| HHI / CR_k | share vectors (customers, suppliers, products, geographies) | shares sum to 1 checked | fixtures incl. degenerate |
| Revenue CAGR / growth | revenue series | — | fixture |

**Reference (not core, clearly labeled):** Altman Z (1968 public-manufacturing coefficients and zones;
Z′/Z″ variants never mixed — private firms use Z′), Merton DD/PD (optional, listed mode only).

### 17.2 Scoring model (documented, configurable, honest)

- Each metric maps to a **0–100 risk score** via documented threshold bands (higher = riskier; bands
  are engineering choices documented per metric — *not statistically calibrated*, stated in reports).
- **Dimension score** = weighted mean of its metric scores (dimension-level weights documented,
  default equal). Dimensions: Financial Strength, Liquidity, Market/External-Price Exposure, Credit,
  Operational, Concentration, Macro.
- **Composite** = Σ w_d·S_d, Σw_d = 1; default weights **equal (1/7 each)** and user-adjustable; every
  weight change is versioned and recorded.
- **Sensitivity analysis:** composite recomputed under ±20% perturbation of each weight; report shows
  dimension-rank stability and score range. This answers RQ4 honestly.
- Severity labels (convention): 0–25 Low, 25–50 Moderate, 50–75 High, 75–100 Critical.

## 18. ML Strategy (focused, justified)

**Problem:** detect *unusual multi-ratio behavior* for a company (e.g., margin collapse, receivables
spike, cost explosion) that single-threshold rules miss, and attribute the drivers.

| Element | Choice |
|---|---|
| Model | Isolation Forest (`sklearn.ensemble.IsolationForest`; Liu et al., ICDM 2008) on per-period ratio vectors, normalized per company (rolling baseline) |
| Why ML at all | nonlinear joint behavior across ratios and per-company baselines; simple thresholds miss interactions. **Retained only if it beats the rule baseline in evaluation** (honest falsifiability) |
| Baseline (required) | rolling z-score / IQR rule on the same features |
| Features | the ratio registry outputs + period-over-period deltas + rolling volatility of key ratios |
| Data | synthetic generator with **injected realistic anomalies** (labeled) + optional EDGAR real statements (unlabeled exploration) |
| Evaluation | ROC-AUC, PR-AUC, F1, precision@k, recall@k vs injected labels; baseline comparison; score normalization documented. **No external benchmark is claimed.** |
| Explainability | SHAP TreeExplainer (TreeSHAP) for per-anomaly driver attribution; LIME/permutation importance as cross-checks |
| Caveats stated in outputs | prediction ≠ explanation ≠ causation; anomaly ≠ distress; low-data regimes acknowledged |

## 19. Business Digital Twin (deterministic, monthly)

A financial-layer simulation of one business. **Not** a perfect digital replica — a transparent set of
documented relationships. Monthly recursion, horizon H ≤ 36. Every parameter tagged **[R] real**
(from statements), **[A] assumption** (documented default), or **[S] scenario**.

```text
Rev_t    = Rev_{t-1} × (1+g) × (1+δ_rev)            (g [R/A]; δ_rev [S])
COGS_t   = Rev_t × c₀ × (1+δ_comm·κ_c) × (1+δ_cogs) (c₀ [R]; κ_c commodity share of COGS [R/A]; δ's [S])
GP_t     = Rev_t − COGS_t
Opex_t   = F + v·Rev_t, adjusted by (1+δ_opex)      (fixed/variable split [A]; δ [S])
EBITDA_t = GP_t − Opex_t ;  EBIT_t = EBITDA_t − DA_t (DA [R/A])
Interest_t = (r_t/12)·D_{t-1}, r_t = r₀ + δ_rate for floating share φ  (φ [R/A]; δ_rate [S])
EBT_t = EBIT_t − Interest_t ; Tax_t = max(0, EBT_t)·τ ; NI_t = EBT_t − Tax_t   (τ [R/A])
AR_t = Rev_t·DSO/30 ; Inv_t = COGS_t·DIO/30 ; AP_t = COGS_t·DPO/30 ; ΔNWC_t = Δ(AR+Inv−AP)
OCF_t = NI_t + DA_t − ΔNWC_t
Capex_t = Capex₀·(1+δ_capex) ;  Debt amortizes on schedule [R/A]
Cash_t = Cash_{t-1} + OCF_t − Capex_t − principal payments   (min cash buffer [A])
```

- **Supplier disruption [S]:** effective revenue capped by supply capacity × (1−δ_supplier) — the
  second-order demand→fulfillment→revenue effect is an explicit, documented assumption.
- **FX [S]:** import-cost share κ_fx of COGS scales with δ_fx; foreign-revenue share ρ_rev converts
  δ_fx into a revenue effect. Both shares are [R/A] inputs.
- **Outputs per period:** Rev, GP, EBITDA, EBIT, NI, Cash, Debt, AR/Inv/AP, DSCR, interest coverage,
  runway; plus trough values and end-horizon summaries.
- **Identity invariant (tested):** Cash_t = Cash_{t-1} + OCF_t − Capex_t − principal ± financing holds
  every period; balance-sheet identity Assets = Liabilities + Equity holds on generated data.

## 20. Scenario Engine

**Bounded JSON schema (guardrail-enforced):**

```json
{
  "name": "str",
  "horizon_months": "1..36",
  "revenue_change_pct":       [-50, 50],
  "cogs_change_pct":          [-50, 50],
  "opex_change_pct":          [-50, 50],
  "interest_rate_change_pp":  [-5, 5],
  "fx_change_pct":            [-50, 50],
  "commodity_price_change_pct": [-50, 100],
  "supplier_disruption_pct":  [0, 100],
  "capex_change_pct":         [-100, 100],
  "ar_days_change":           [-30, 60],
  "one_off_cost":             [0, +inf)
}
```

- **User-created:** form in the UI → validated → run.
- **Presets (template defaults, user-editable, not regulator-calibrated):** Recession (revenue −15%,
  churn-like demand softness), Inflation (COGS +12%, opex +8%), Interest-rate shock (+2pp), FX shock
  (−10% currency → import-cost effect), Commodity shock (+25% input cost), Demand collapse (−30%),
  Supplier disruption (−40% top-supply share), Combined stress (multi-factor, DFAST-patterned).
- **AI-generated:** natural language → LLM emits candidate JSON → **schema + bounds validation →
  clamp-or-reject with logged guardrail event → user confirms mapped parameters before run**
  (human-in-the-loop interrupt). Example: “Simulate a 15% revenue decline and 2% higher interest
  rates” → `{"revenue_change_pct": -15, "interest_rate_change_pp": 2.0}`.

## 21. Stress Testing

- **Baseline vs stressed:** the twin runs twice — identical parameters except scenario deltas.
- **Outputs:** KPI comparison table (baseline / stressed / Δ%) at trough and horizon; dimension-score
  deltas; **breach flags** against configurable policy thresholds (defaults: runway < 6 months,
  DSCR < 1.2, interest coverage < 1.5, cash < minimum buffer); **EBITDA waterfall** (revenue effect,
  input-cost effect, opex effect, interest effect, other) for driver decomposition; full trajectories
  for charts.
- **Multi-scenario grid:** several scenarios in one run produce a comparison matrix (future-scope
  heatmap rendering exists in the UI design; the API supports N scenarios per analysis).

## 22. Explainability (layered, causally honest)

| Layer | Mechanism | Nature |
|---|---|---|
| L1 Deterministic contribution | exact per-metric/dimension contributions to composite (additive aggregation ⇒ exact) | fact (given model) |
| L2 Model attribution | SHAP on the anomaly model (TreeSHAP); permutation-importance cross-check | prediction-local explanation |
| L3 Scenario counterfactual | twin deltas: “risk rises because revenue −15% ⇒ EBITDA −x ⇒ runway −y months” | interventional simulation (assumption-based, **not** observational causality) |
| L4 Agent narrative | LLM story composed from L1–L3 packs; numbers verified by guardrail | narrative |

Every output states which layer a claim comes from. Correlation is never presented as causation;
L3 is labeled *assumption-based intervention on the twin*, not discovered causal truth.

## 23. Mitigation Engine

- **Curated library** (in-repo, versioned YAML): risk pattern → candidate actions (e.g., high supplier
  concentration → supplier diversification; low runway → receivables acceleration / cost restructuring;
  rate exposure → fixed-rate refinancing), each with expected direction of impact, assumptions,
  trade-offs (e.g., diversification ⇒ possible procurement cost increase), and qualitative confidence.
- The Mitigation Agent **selects and contextualizes** library entries against the computed profile and
  scenario results; it may not invent actions outside the library (guardrail: library-grounded
  retrieval).
- Output contract per mitigation: `risk_addressed, action, expected_effect (direction + rough
  magnitude from twin where computable), assumptions[], trade_offs[], confidence, source: library_id`.
- **Never presented as guaranteed financial advice** — disclaimer attached to every mitigation and report.

## 24. Guardrails (deterministic controls)

| # | Guardrail | Implementation |
|---|---|---|
| 1 | Schema validation | Pydantic models on every tool I/O, API payload, DB write |
| 2 | Numerical validation | finite-value checks, division guards, currency/unit checks |
| 3 | Missing-data validation | required-concept coverage matrix; run blocked below threshold (default 70%) with explicit report |
| 4 | Source validation | source registry: license tag, fetch timestamp, checksum; stale data flagged |
| 5 | Scenario bounds | §20 schema; clamp-or-reject + `guardrail_events` row |
| 6 | Agent permissions | per-agent tool allowlist enforced centrally by the tool registry |
| 7 | Maximum loops | supervisor replanning ≤ 2; per-agent tool calls ≤ 6 |
| 8 | Timeouts | per-tool 30s, per-agent 120s, per-run 10 min (configurable) |
| 9 | Tool validation | argument schemas + range checks; invalid call → feedback (≤2 retries) → degrade |
| 10 | **Calculation verification** | every number in report/mitigations extracted and compared to the engine pack (tolerance); mismatch → regenerate (≤2) → `human_review` |
| 11 | Human-review triggers | composite > 85; ≥3 guardrail events; coverage < 70%; agents disagree on a dimension's direction |
| 12 | Prompt-injection handling | external text (news/filings) treated as data, never instructions; fixed system prompts; tool outputs never executed as directives (documented mitigation, not bulletproof) |
| 13 | Budget | max tokens per run (default 200k) + cost ceiling; abort with structured error |

## 25. Data Sources

Full verified detail (source vs access, licensing, coverage, limits) in
[phase-0-research.md](00_research/phase-0-research.md) §7. Strategy (D2):

| Role | Source | Access | License posture |
|---|---|---|---|
| Company financials (primary) | **Synthetic generator** (in-repo, seeded, sector-parameterized) | local code | none needed |
| Company financials (optional real) | SEC EDGAR XBRL company facts | official keyless API; User-Agent declared; **10 req/s max** | U.S. public domain |
| Macro (primary) | FRED (FEDFUNDS, CPIAUCSL, GDPC1, UNRATE, DEXINUS verified) | official API + free key | attribution required |
| Macro context | World Bank WDI (NY.GDP.MKTP.KD.ZG, FP.CPI.TOTL.ZG verified) | official API, no key | CC BY 4.0 |
| Market (primary) | Stooq CSV | unofficial CSV endpoints | **“personal use only” footer; no published license — terms risk flagged** |
| Market (fallback) | Yahoo Finance via `yfinance` | unofficial Apache-2.0 library | Yahoo ToS restricts automated collection; educational prototype use only |
| Synthetic augmentation (optional) | SDV | library | **BSL — not MIT; optional only** |

Rules: local cache with source/license/timestamp/checksum; throttling; attribution recorded; **no
redistribution** of any third-party data; the synthetic path must make the system fully functional
with zero network access.

## 26. Evaluation

| Subsystem | Metrics / checks |
|---|---|
| ML | ROC-AUC, PR-AUC, F1, precision@k, recall@k on injected anomalies; baseline (z-score rule) comparison; score-normalization notes |
| Risk engine | 100% hand-computed fixture coverage; property tests (scale invariance, monotonicity: cash↓ ⇒ liquidity score ↑; degenerate inputs); golden-file regression; version-tagged registry |
| Scenario/twin | reproducibility (identical outputs, same seed); cash-identity & balance-sheet invariants every period; single-factor sweeps monotone where expected; bound clamping behaves per spec |
| Agents | task-completion rubric; tool-call accuracy & invalid-call rate; **hallucination metric = numeric claims not matching engine outputs (auto-measured)**; latency per node; loop counts; token/cost per run |
| System | API p50/p95 latency; run wall-clock; test coverage (NFR3); memory/CPU profile; SSE reliability |
| Human (optional) | 2–3 reviewers, Likert rubric on usefulness/faithfulness of reports |

All results measured in Phase 13 and reported verbatim — no invented numbers anywhere in the project.

## 27. Baselines

| Baseline | Description | Compared on |
|---|---|---|
| **B1** Rule-based ratio analysis | threshold bands + composite (the engine alone, no agents/ML/twin) | risk-driver identification vs injected ground truth; scenario delta reporting (none) |
| **B2** Standalone ML | Isolation Forest without agents/explanations integration | anomaly detection metrics; usefulness of bare scores |
| **B3** Single LLM analyst | one LLM prompt with financials; no tools | numeric faithfulness (auto-checkable), coverage, consistency, hallucination rate |
| **B4** Multi-agent without guardrails | same graph, permissions/verification disabled | invalid calls, verification failures, loop overruns, latency |
| **Proposed** | full system | all of the above |

Protocol: identical inputs (seeded synthetic set + fixed scenario suite); automated scorers where
possible; every reported number measured, with scripts in `experiments/`.

## 28. Security

- **AuthN/Z (Phase 12):** JWT-based sessions; two roles (analyst, admin); password hashing (bcrypt/argon2 via passlib); no SSO.
- **Input handling:** Pydantic validation on all payloads; ORM-parameterized queries only; file uploads restricted to validated schemas (JSON/CSV allowlist, size caps).
- **Secrets:** environment variables only; `.env` git-ignored; `.env.example` documents names (no values); API keys never logged.
- **LLM-specific:** prompt-injection handling (guardrail 12); no PII in synthetic data (fictional entities); provider calls carry only necessary data.
- **Transport/deployment:** CORS allowlist; rate limiting on auth + expensive endpoints; Docker containers non-root; dependency pinning + `pip-audit` in CI (Phase 12).
- **Audit:** append-only `audit_log`; analysis runs reproducible from stored inputs + config + seed.

---

## 29. Observability

- **Structured logs:** `structlog` JSON logs with `run_id`/`analysis_id` correlation, from Phase 2.
- **Trace store (own tables, from Phase 9):** `agent_runs`, `agent_steps` (per node: input/output
  summary, tool calls, latency), `llm_calls` (provider, model, prompt/response hashes, tokens,
  latency, cost estimate), `guardrail_events`. The frontend **Agent Trace** view renders these —
  observability is a product feature, not an afterthought.
- **Optional exporter:** Langfuse (MIT core, self-hostable) behind an interface, so it can be enabled
  or removed without touching agents.
- **Metrics (Phase 12):** Prometheus `/metrics` — request rates/latencies, run counters, guardrail
  trip-counters, LLM token/cost totals.
- **Reproducibility:** every analysis stores inputs + config + seed + engine version, so any past run
  can be re-executed for debugging or viva demonstration.

## 30. Database Design (PostgreSQL 16; SQLAlchemy 2.0 + Alembic; SQLite dev fallback)

| Table | Key columns |
|---|---|
| companies | id, name, sector, currency, description, data_origin(synthetic/manual/edgar), created_at |
| financial_periods | id, company_id, period_start, period_end, fiscal_year, quarter, source |
| financials | id, period_id (FK), revenue, cogs, gross_profit, opex, ebitda, ebit, da, interest_expense, tax, net_income, cash, receivables, inventory, payables, current_assets, current_liabilities, total_assets, total_liabilities, equity, total_debt, st_debt, lt_debt, capex, ocf, concentration buckets (customers/suppliers/products/regions JSONB), fx/commodity exposures JSONB, debt_schedule JSONB |
| market_cache | symbol, date, close, source, license_tag |
| macro_cache | series_id, source, date, value, license_tag |
| source_fetch_log | url, source, license_tag, fetched_at, checksum, status |
| analyses | id, company_id, status, config JSONB, weights_id, seed, engine_version, started_at, finished_at, error |
| risk_assessments | id, analysis_id, dimension, score, method_version |
| risk_factors | id, analysis_id, dimension, factor, value, band, severity, explanation |
| aggregation_weights | id, name, weights JSONB, is_default, created_by |
| scenarios | id, analysis_id, name, type(preset/form/ai), params JSONB, source_text, validated |
| simulation_runs | id, analysis_id, scenario_id, is_baseline, results JSONB, kpis JSONB |
| stress_comparisons | id, analysis_id, scenario_id, deltas JSONB, breaches JSONB, waterfall JSONB |
| mitigations | id, analysis_id, risk_factor_id, action, expected_effect, assumptions JSONB, trade_offs JSONB, confidence, library_id, status |
| explanations | id, analysis_id, layer(deterministic/shap/counterfactual/narrative), payload JSONB |
| agent_runs | id, analysis_id, graph_version, started_at, ended_at, final_state JSONB |
| agent_steps | id, agent_run_id, seq, node, agent, input_summary, output_summary, tool_calls JSONB, latency_ms, error |
| llm_calls | id, agent_run_id, provider, model, purpose, prompt_sha, response_sha, tokens_in, tokens_out, latency_ms, cost_estimate |
| guardrail_events | id, agent_run_id, seq, rule, severity, action(allow/block/degrade/human_review), detail JSONB |
| ml_artifacts | id, company_id, model_version, params JSONB, metrics JSONB, trained_at |
| audit_log | id, ts, actor, action, object_type, object_id, payload JSONB |
| users (Phase 12) | id, email, password_hash, role |

## 31. API Design (REST, versioned `/api/v1`; SSE for progress)

| Method & path | Purpose |
|---|---|
| `POST /companies` | create company (synthetic config or manual JSON; EDGAR import later) |
| `GET /companies` / `GET /companies/{id}` | list / detail with data-coverage report |
| `POST /companies/{id}/analyses` | start analysis (config: include_ml, weights_id, scenarios[]) → `202 {analysis_id}` |
| `GET /analyses/{id}` | status + headline results |
| `GET /analyses/{id}/risks` | dimension scores, factors, contributions |
| `GET /analyses/{id}/explanations` | layered explanations |
| `GET /analyses/{id}/mitigations` | mitigation candidates |
| `GET /analyses/{id}/trace` | agent steps, LLM calls, guardrail events |
| `GET /analyses/{id}/events` | SSE progress stream |
| `GET /scenarios/presets` | preset library |
| `POST /analyses/{id}/scenarios` | create (text → validated JSON preview → confirm) |
| `POST /scenarios/{id}/simulate` | run twin for one scenario |
| `POST /analyses/{id}/stress-tests` | run baseline vs scenario comparison |
| `GET /weights` / `PUT /weights/{id}` | inspect/update aggregation weights |
| `GET /audit` | audit log query |
| `GET /health`, `GET /metrics` | liveness; Prometheus (Phase 12) |

Conventions: JSON errors with stable codes; every response carries `analysis_id` + `engine_version`;
auth headers from Phase 12.

## 32. Frontend Design (Phase 11 — approved stack D3)

- **Stack:** React + Vite + TypeScript; Tailwind CSS design tokens; **ECharts** (primary risk
  visualizations: radar for the 7-dimension profile, line for twin trajectories, waterfall for EBITDA
  bridge, heatmap for scenario grid, gauge/scorecards), **Recharts** for lightweight spots;
  **GSAP + ScrollTrigger** for scroll/timeline reveals; **Motion** for micro-interactions and page
  transitions; TanStack Query for data; React Router for routes.
- **Build-time skills:** `ui-ux-pro-max` (design/ui-styling), `taste-skill` (design-taste-frontend /
  high-end-visual-design), `gsap-skills` (core/scrolltrigger/timeline). Goal: **premium,
  production-quality, responsive** product — not a generic admin template.
- **Routes:** Dashboard (overview) · Company Workspace (profile + risk radar + drivers) · Scenario Lab
  (chat + form → parameter preview → confirm) · Stress Comparison (deltas, breaches, waterfall) ·
  Explanations (layered L1–L4) · Mitigations (cards with assumptions/trade-offs) · Agent Trace
  (node timeline + tool calls) · Audit.
- **Design principles:** clear risk semantics (consistent 0–100 scale colors), motion respects
  `prefers-reduced-motion`, WCAG AA contrast, keyboard navigable, currency/locale aware (default ₹ INR
  for synthetic examples, fully configurable).

## 33. Final Folder Structure

```text
ai-business-risk/
├── README.md  LICENSE  .gitignore  .env.example
├── pyproject.toml            # backend package + tool config (ruff, mypy, pytest)
├── docker-compose.yml        # postgres + backend + frontend (Phase 2 skeleton, Phase 12 finalize)
├── docs/                     # this documentation set (grows per phase)
├── backend/
│   ├── app/                  # FastAPI: main.py, config.py, logging setup, api/v1 routers, ws/sse
│   ├── core/                 # config, security, errors (Phase 12 security here)
│   ├── data_engine/          # ingest/{synthetic,edgar,fred,stooq,yahoo}.py, validate/, normalize/, features.py
│   ├── risk_engine/          # ratios, liquidity, leverage, profitability, market, concentration, scoring, registry
│   ├── ml_engine/            # features.py, models.py, train.py, explain.py, evaluate.py
│   ├── simulation/           # twin.py, assumptions.py, scenarios.py, stress.py, sensitivity.py
│   ├── agents/               # state.py, graph.py, supervisor.py, specialists/, aggregator.py,
│   │                         # scenario_agent.py, mitigation_agent.py, report_agent.py, tools.py, prompts/
│   ├── llm/                  # base.py, factory.py, providers/{glm,openai,gemini,anthropic,ollama}.py
│   ├── guardrails/           # schemas.py, validators.py, permissions.py, limits.py, verification.py
│   ├── database/             # models.py, session.py, migrations/ (Alembic)
│   ├── services/             # analysis_service, company_service, scenario_service, audit_service
│   ├── observability/        # tracing.py, metrics.py
│   └── tests/                # unit/, integration/, agents/, golden/
├── frontend/                 # React+Vite+TS app (created Phase 11)
├── data/                     # raw/ (cached, git-ignored), synthetic/ (generated datasets)
├── notebooks/                # exploration only, not production code
├── experiments/              # baseline/ablation configs + measured results (Phase 13)
├── scripts/                  # CLI utilities: seed_db.py, generate_company.py, run_eval.py
└── deployment/               # docker/, notes
```

## 34. File-by-File Explanation (planned; “Created” = phase)

Legend: **T** = test coverage target. Inputs/outputs abbreviated; full contracts freeze in Phase 1.

**Root & config**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| README.md | entry point, status, roadmap (exists) | 0 | — |
| pyproject.toml | backend package metadata, deps, ruff/mypy/pytest config | 2 | — |
| .env.example | required env var names (DB, LLM keys, FRED key) — no values | 2 | — |
| .gitignore | ignore .env, data/raw, caches, node_modules | 2 | — |
| docker-compose.yml | postgres + backend + frontend for demo | 2 | smoke |
| LICENSE | MIT (pending approval) | 2 | — |

**backend/app + core**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| app/main.py | FastAPI factory, router mounting, lifespan (DB init, trace hooks) | 2/10 | integration |
| app/config.py | pydantic-settings (env → typed config) | 2 | unit |
| app/logging.py | structlog JSON config w/ run_id binding | 2 | unit |
| app/api/deps.py | DI: db session, auth user (Phase 12) | 10 | integration |
| app/api/v1/*.py | routers per §31 (companies, analyses, scenarios, stress, trace, audit, health) | 10 | API tests |
| app/sse.py | SSE progress streaming from run events | 10 | integration |
| core/security.py | JWT issue/verify, password hashing, role checks | 12 | unit |

**backend/data_engine**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| ingest/synthetic.py | seeded company generator → statements + buckets (+ injectable anomalies) | 3 | unit (statistical + seed determinism) |
| ingest/edgar.py | XBRL companyfacts → internal schema mapper (throttled, User-Agent) | 3 (optional) | unit w/ cached fixture |
| ingest/fred.py | macro series fetch → cache (key, attribution) | 3 | unit w/ vcr-style fixture |
| ingest/stooq.py | market CSV fetch → cache (terms-flagged) | 3 | unit w/ fixture |
| ingest/yahoo.py | yfinance fallback (throttled, cached) | 3 | unit w/ fixture |
| validate/schema_checks.py | required-concept coverage matrix, ranges, currency/unit checks | 3 | unit |
| validate/identities.py | A=L+E, cash-flow identity, share-sum checks | 3 | unit |
| normalize/periods.py | calendarization, fiscal-period alignment | 3 | unit |
| normalize/currency.py | currency handling + FX series application | 3 | unit |
| features.py | model-ready feature frames from validated data | 3/5 | unit |

**backend/risk_engine**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| registry.py | formula registry: ids, definitions, bands, versions (doc strings) | 4 | unit |
| ratios.py | liquidity/leverage/coverage/profitability/efficiency formulas | 4 | fixtures (100%) |
| market.py | volatility, beta, VaR, ES | 4 | fixtures |
| concentration.py | HHI, CR_k per bucket | 4 | fixtures |
| scoring.py | bands → 0–100, dimension scores, composite, contributions | 4 | fixtures + properties |
| sensitivity.py | ±20% weight perturbation, rank stability | 4 | unit |
| reference_models.py | Altman Z (+variants), optional Merton — clearly labeled reference | 4 | fixtures |

**backend/ml_engine**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| features.py | ratio vectors + deltas + rolling stats per company | 5 | unit |
| models.py | Isolation Forest + z-score rule baseline wrapper | 5 | unit |
| train.py | fit + persist artifact (versioned) | 5 | integration (small) |
| explain.py | SHAP TreeExplainer + permutation cross-check | 5 | unit (small fixture model) |
| evaluate.py | ROC-AUC/PR-AUC/F1/precision@k vs injected labels | 5/13 | unit |

**backend/simulation**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| assumptions.py | parameter table ([R]/[A]/[S] tags, defaults, docs) | 6 | unit |
| twin.py | monthly recursion engine (§19 equations) | 6 | fixtures + invariants |
| scenarios.py | schema models, presets, clamp/validate | 7 | unit |
| stress.py | baseline vs scenario runner, deltas, breaches, waterfall | 8 | fixtures |
| sensitivity.py | single-factor sweeps | 8 | unit |

**backend/agents**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| state.py | RiskState schema (typed, versioned) | 9 | unit |
| graph.py | StateGraph wiring, conditional edges, interrupts, checkpointing | 9 | integration |
| supervisor.py | planning/routing node (prompt + parser + guards) | 9 | agent test |
| specialists/{financial,market,operational,macro}.py | interpretation agents over tools | 9 | agent tests |
| aggregator.py | deterministic node calling risk_engine + ml findings | 9 | unit |
| scenario_agent.py | NL→JSON + preset selection | 9 | agent test |
| mitigation_agent.py | library-grounded mitigation selection | 9 | agent test |
| report_agent.py | report composer from result pack | 9 | agent test |
| tools.py | deterministic tool wrappers (args schemas, allowlist, tracing) | 9 | unit |
| prompts/*.md | versioned system prompts per agent | 9 | — |

**backend/llm (provider-agnostic, D1)**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| base.py | provider interface + settings (model, temperature, budget) | 9 | unit |
| factory.py | config → LangChain chat model via adapter registry | 9 | unit |
| providers/glm.py | GLM-5.3-Flash via OpenAI-compatible endpoint (dev default) | 9 | contract smoke |
| providers/{openai,gemini,anthropic,ollama}.py | drop-in adapters | 9 (stubs ok) | — |

**backend/guardrails**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| schemas.py | shared Pydantic contracts (scenario, findings, packs) | 3 (scenarios) / 9 | unit |
| validators.py | numeric/coverage/source validators | 3/9 | unit |
| permissions.py | agent→tool allowlist enforcement | 9 | unit |
| limits.py | loops/timeouts/budgets | 9 | unit |
| verification.py | numeric-consistency verifier for LLM text | 9 | unit (adversarial cases) |

**backend/database, services, observability**

| File | Purpose (I/O) | Created | T |
|---|---|---|---|
| database/models.py | SQLAlchemy ORM per §30 | 2 (core tables) / 10 | integration |
| database/session.py | engine/session factory (PostgreSQL/SQLite) | 2 | unit |
| database/migrations/ | Alembic versions | 2/10 | migration run |
| services/analysis_service.py | run lifecycle: create → orchestrate graph → persist results | 10 | integration |
| services/company_service.py | company + period CRUD + coverage report | 10 | integration |
| services/scenario_service.py | scenario CRUD + validation + confirmation state | 10 | integration |
| services/audit_service.py | append-only audit writes | 10/12 | unit |
| observability/tracing.py | trace-row writers; optional Langfuse export | 9/12 | unit |
| observability/metrics.py | Prometheus counters/histograms | 12 | unit |

**frontend (created Phase 11; planned files)**

| File/area | Purpose |
|---|---|
| src/main.tsx, App.tsx, router | app shell + routes |
| src/api/client.ts, hooks/* | typed API client + TanStack Query hooks + SSE |
| src/routes/{Dashboard,Company,Risks,ScenarioLab,Stress,Explanations,Mitigations,Trace,Audit}.tsx | §32 views |
| src/components/charts/* | ECharts wrappers (radar, line, waterfall, heatmap, scorecards) |
| src/components/layout/*, ui/* | design-system components (tokens, cards, tables) |
| src/components/motion/* | GSAP ScrollTrigger sections + Motion transitions |
| src/lib/{format,riskTheme}.ts | currency/number formatting, risk-scale palette |
| tests | Vitest component tests + Playwright smoke (Phase 12) |

**Top-level**

| Path | Purpose | Created |
|---|---|---|
| data/generator configs, data/raw cache | seeded datasets; downloads (git-ignored) | 3 |
| notebooks/ | exploration (non-production) | 5+ |
| experiments/{baselines,ablations}/ | run configs + measured result tables | 13 |
| scripts/{seed_db,generate_company,run_eval}.py | CLI utilities | 3/10/13 |
| deployment/docker/ | production-ish compose/notes | 12 |
| .github/workflows/ci.yml | lint + tests on push (optional) | 12 |

## 35. Technology Stack (with justification for the viva)

| Layer | Choice | Why |
|---|---|---|
| Backend language | Python 3.11+ | quantitative + LLM ecosystem; team skill |
| API | FastAPI + Pydantic v2 | async, typed contracts (guardrails reuse), OpenAPI docs |
| Agent orchestration | LangGraph (MIT, v1.x) | stateful graphs, checkpointing, interrupts (HITL); verified current |
| LLM | **GLM-5.3-Flash (dev default, D1)** via OpenAI-compatible adapter | verified model + endpoint; flash tier cheap/fast; **provider-agnostic** by design |
| Dataframes/math | pandas, NumPy | standard, auditable |
| ML | scikit-learn (IsolationForest), shap | verified standard tools; TreeSHAP exactness |
| DB | PostgreSQL 16 + SQLAlchemy 2 + Alembic (SQLite dev fallback) | relational integrity, migrations; zero-cost dev fallback |
| Validation | Pydantic v2 | single schema language across API/guardrails/DB boundaries |
| Logging | structlog | structured JSON with correlation ids |
| Testing | pytest + pytest-cov (+ hypothesis for property tests where valuable) | standard |
| Lint/type | ruff + mypy | quality gates (NFR7) |
| Frontend | React + Vite + TypeScript + Tailwind (D3) | approved; premium UI capability |
| Charts | ECharts (primary), Recharts (light) (D3) | approved; right chart types for risk viz |
| Motion | GSAP + ScrollTrigger; Motion (D3) | approved |
| Data fetch (FE) | TanStack Query | caching, retry, SSE-friendly |
| Packaging | pip + pyproject.toml; Docker Compose | reproducible; no exotic tooling |

## 36. Development Phases (approved numbering — gates between phases)

| Phase | Name | Deliverables | Exit criteria |
|---|---|---|---|
| 0 | Research + Master Specification | this doc set | **approval** |
| 1 | Architecture Freeze | docs: architecture, agents, data, risk-engine, simulation, api, database, requirements, testing, project-overview | all contracts fixed; **approval** |
| 2 | Foundation | repo skeleton, pyproject, config, logging, DB session + core migrations, pytest harness, docker-compose skeleton, .env.example | `pytest` green on skeleton; app boots; **approval** |
| 3 | Data Engineering | synthetic generator; EDGAR/FRED/Stooq/yahoo ingest w/ cache; validation & normalization; seed script | fixture tests green; coverage report works; **approval** |
| 4 | Quantitative Risk Engine | formula registry + all §17 formulas + scoring/sensitivity | 100% fixture coverage on formulas; property tests; **approval** |
| 5 | ML Engine | features, IF model + z-score baseline, train/eval, SHAP | eval metrics reported on injected anomalies; **approval** |
| 6 | Business Digital Twin | assumptions, twin engine | invariants hold; fixture trajectories; **approval** |
| 7 | Scenario Engine | schema, presets, clamp/validate, NL→JSON translation path | bounds tests; translation round-trip tests; **approval** |
| 8 | Stress Testing | stress runner, deltas, breaches, waterfall, sweeps | comparison fixtures; reproducibility test; **approval** |
| 9 | Multi-Agent LangGraph | state, graph, supervisor, specialists, tools, prompts, guardrails wiring, LLM adapters | agent integration tests (recorded/mock LLM + live smoke); **approval** |
| 10 | Backend/API | routers, services, SSE, DB integration, audit | API tests green; end-to-end run via API; **approval** |
| 11 | Frontend | full §32 UI on approved stack | build clean; views wired to real API; **approval** |
| 12 | Testing/Observability/Security | auth, hardening, metrics, trace polish, CI, e2e+security tests | NFR3 coverage; security checklist done; **approval** |
| 13 | Evaluation/Benchmarking | B1–B4 + ablations, measured tables, sensitivity study | all results measured & written (no invented numbers); **approval** |
| 14 | Final Documentation/Viva | final report, paper draft, presentation, demo script, viva Q&A, future scope | complete doc set; **approval** |

Phase control after every phase: explain what was implemented; list files created/modified with
reasons; run tests and show results; identify unresolved issues; update docs; verify architecture
consistency; **stop and wait for approval**.

## 37. Definition of Done

**Per phase:** code + tests pass; docs and development log updated; file list with reasons reported;
architecture consistent with this spec (changes only via the change-control procedure); explicit
approval recorded.

**Overall (end of Phase 14):** `docker compose up` demo runs end-to-end (ingest → analyze → scenario →
stress → report → trace); evaluation report contains only measured results; every formula has
fixture tests; docs complete per §40; reproducible from a clean clone via README instructions; no
**NOT VERIFIED** claims remain un-rechecked in final documents.

## 38. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM API quota/latency/cost drift (GLM Flash tier) | med | med | budgets + caching + temperature 0 for structured steps; provider abstraction allows switching |
| Stooq/yfinance terms or breakage | high | low-med | synthetic path is primary; cache aggressively; both flagged; EDGAR fallback for statements |
| SHAP × IsolationForest integration friction | low | med | Phase 5 spike first; fallback: explain on surrogate / permutation importance (documented) |
| Scope creep | high | high | strict phase gates; out-of-scope list §13; change control (§36 note + mandate §28) |
| Synthetic data realism gaps | med | med | calibrate distributions to EDGAR sector medians (Phase 3 task); document as limitation |
| Over-claiming in agent text | med | high | numeric verifier (guardrail 10) + disclaimers + hallucination metric |
| Timeline (B.Tech schedule) | med | high | phased plan with smallest-demoable increments; future-scope parking lot |
| Examiner comprehension of agents | med | med | layered docs + trace UI makes reasoning visible; viva plan §41 |

## 39. Research Opportunities (beyond the required evaluation)

1. **Faithfulness methodology:** a reusable metric + harness for “LLM numeric faithfulness” in
   tool-grounded pipelines (auto-checkable hallucination rate).
2. **Guardrail ablations:** which guardrail contributes most to reliability per unit latency (B4 vs
   proposed, finer-grained).
3. **Weight-sensitivity reporting:** how aggregation-weight transparency changes user trust (small
   user study, optional).
4. **Synthetic stress benchmark:** a published, seeded scenario suite for comparing business-risk
   systems reproducibly.
5. **Digital-twin fidelity study:** how [R]/[A] assumption ratios affect stress-test conclusions.
6. **Cross-provider consistency:** same graph on GLM vs OpenAI vs Gemini — does numeric faithfulness
   hold across providers (enabled by D1)?

## 40. B.Tech Documentation Plan

| Report chapter | Source docs | Prepared in |
|---|---|---|
| Introduction, problem, objectives | spec §1–§12 | 0/14 |
| Literature review | research §3–§5 | 0/14 |
| Methodology / system design | spec §7, §15–§25; docs/01_architecture/architecture.md, agents.md | 1–9 |
| Mathematical formulation | spec §17, §19; docs/01_architecture/risk-engine.md, simulation.md | 1–8 |
| Implementation | development-log.md, per-phase reports | 2–12 |
| Results & evaluation | experiments/ outputs; spec §26–§27 | 13 |
| Limitations & future work | spec §13, §38, §39 | 14 |
| Abstract, presentation, demo | Phase 14 | 14 |

docs/ files listed in the mandate are created **only when their content exists** (per the
documentation rule), starting with Phase 1's freeze set.

## 41. Viva Preparation Plan

- **Question bank maintained per phase** in the development log: why each technology (§35 “Why”
  column), why each agent exists (§16), why ML is used and when it would be dropped (§18), why
  deterministic math (§7 principle), agent communication & state (§16), hallucination control (§24.10,
  §26), scenario generation (§20), stress testing (§21), risk calculation (§17), evaluation (§26–§27),
  genuine novelty (§8 honest scope), limitations (§13, §38).
- **Demo script (5–7 min):** generate company → run analysis → inspect risk radar + drivers → ask NL
  scenario → confirm mapped parameters → stress comparison (waterfall + breaches) → open agent trace →
  show guardrail event → audit view.
- **Anticipated tough questions** prepared with answers: “Why are the weights not learned?” (§17.2 —
  transparency + sensitivity analysis; learning is future work), “Why not real data only?” (licensing
  + controllability + reproducibility; EDGAR optional), “How is this different from FinRobot?” (§3.6,
  G1: deterministic stress propagation + verification, whole-business scope), “What if the LLM is
  down?” (degraded mode: deterministic pipeline still runs, narrative layers marked unavailable),
  “Is SHAP causal?” (no — L1/L3 vs L2 distinction, §22).
