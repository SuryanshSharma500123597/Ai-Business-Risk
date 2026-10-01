# Project Overview — AI Business Risk

**AI Business Risk — Autonomous Multi-Agent Business Risk Intelligence & Stress Testing Platform**

A decision-support and research platform that produces a multi-dimensional, explainable risk profile
for a single business and propagates user-defined or AI-translated scenarios through a deterministic
business digital twin. LLM agents orchestrate and narrate; **every number comes from deterministic,
tested engines** (quantitative risk engine, ML anomaly detector, business digital twin).

**Status:** Phase 5 — ML Engine is **engineering-complete and documentation-closed** (see [05_ml_engine/phase-report.md](../05_ml_engine/phase-report.md)). Phase 4 — Quantitative Risk Engine is **engineering-complete and documentation-closed** (Stage 5 D18–D21 approved; see [04_quantitative-risk/phase-report.md](../04_quantitative-risk/phase-report.md)). Phases 0–3 are complete/approved. The architecture remains frozen; the frozen Phase 1 contracts below are unchanged.

## What it does

1. **Ingest & validate** a company's financial statements (synthetic generator by default; SEC EDGAR
   import as an optional secondary path) plus macro/market context (FRED, World Bank, Stooq/yfinance —
   cached, license-tagged).
2. **Quantify risk** across 7 dimensions — Financial Strength, Liquidity, Market/External-Price
   Exposure, Credit, Operational, Concentration, Macro — into a 0–100 composite with exact, layered
   explanations.
3. **Detect anomalies** with Isolation Forest + SHAP attribution, benchmarked against a rule baseline.
4. **Simulate scenarios** — form-based, preset, or natural language translated to a bounded JSON
   schema (user-confirmed) — through a monthly deterministic digital twin.
5. **Stress test** baseline vs scenario: KPI deltas, threshold breaches, EBITDA waterfall.
6. **Recommend mitigations** from a curated, versioned library (with assumptions and trade-offs,
   never presented as guaranteed financial advice).
7. **Prove the work**: full agent/tool/LLM/guardrail trace, audit log, reproducible runs.

## Who it is for

Risk analysts, financial analysts / CFO teams, business managers and SME owners, enterprise risk
teams, investment analysts, and researchers. **It is decision support, not a replacement for
professional risk teams, and not financial advice.**

## Hard architectural rules (frozen)

| Rule | Statement |
|---|---|
| R1 | The LLM never performs arithmetic, risk calculation, simulation, database writes, or policy enforcement |
| R2 | Every LLM-emitted number is machine-verified against engine outputs before it reaches a user |
| R3 | Deterministic modules (`risk_engine`, `simulation`, `ml_engine`, `data_engine`, `guardrails`) never import LLM/agent code (enforced by an architecture test) |
| R4 | The system is fully functional offline via the synthetic data path |
| R5 | Third-party data is cached locally with source/license/timestamp and never redistributed |
| R6 | Same inputs + seed ⇒ identical deterministic outputs (reproducibility) |
| R7 | The LLM provider is swappable via adapters (GLM-5.3-Flash is the development default only) |

## Document map

| Document | Contents |
|---|---|
| [../../README.md](../../README.md) | Entry point, roadmap |
| [phase-0-research.md](../00_research/phase-0-research.md) | Verified research: platforms, literature, data licensing |
| [master-project-specification.md](../master-project-specification.md) | Phase 0 master specification (41 sections) |
| [requirements.md](requirements.md) | Frozen functional & non-functional requirements |
| [architecture.md](architecture.md) | Frozen system architecture & technology stack |
| [agents.md](agents.md) | Frozen agent architecture: state schema, agents, tools, permissions, guardrail wiring |
| [data.md](data.md) | Frozen data architecture: canonical schema, source contracts, validation |
| [risk-engine.md](risk-engine.md) | Frozen quantitative engine: formula registry, scoring model |
| [simulation.md](simulation.md) | Frozen digital twin, scenario schema & presets, stress methodology |
| [api.md](api.md) | Frozen API specification |
| [database.md](database.md) | Frozen database schema |
| [testing.md](testing.md) | Frozen testing strategy |
| [development-log.md](../development-log.md) | Phase-by-phase log |
