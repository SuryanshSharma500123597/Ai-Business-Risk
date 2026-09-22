# Requirements — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. Expands spec §12 with acceptance criteria. Priority: **M** = must
(MVP-blocking), **S** = should, **C** = could (defer gracefully). Phases reference the approved
0–14 roadmap.

## 1. Functional requirements

| ID | Requirement | Priority | Phase | Acceptance criteria |
|---|---|---|---|---|
| FR1 | Ingest company financials (synthetic generator or manual JSON; EDGAR optional flagged) with validation + coverage report | M | 3 | POST /companies returns 201 with coverage_report; invalid input → 422 with details; synthetic output reproducible for fixed seed |
| FR2 | Compute all registry formulas with versioned definitions | M | 4 | every formula returns value + score + `registry_version`; 100% fixture tests pass |
| FR3 | Produce 7-dimension profile + composite with exact contributions and configurable weights | M | 4 | /risks returns dimensions, contributions, weights_version; weight change ⇒ new version row |
| FR4 | Anomaly detection (Isolation Forest) with SHAP drivers + z-score rule baseline | M | 5 | /explanations includes shap layer; evaluation report shows model vs baseline metrics on injected anomalies |
| FR5 | Scenario creation: presets, form params, natural language → validated bounded JSON | M | 7 | text mode always returns `awaiting_confirmation` (FD-3); out-of-bounds clamped/rejected per [simulation.md](simulation.md) §3 |
| FR6 | Baseline vs scenario stress test: trajectories, KPI deltas, breaches, waterfall | M | 8 | /stress-tests returns all §5 outputs; waterfall closes within 0.5%; reproducible |
| FR7 | Mitigation candidates from versioned library with assumptions/trade-offs | M | 9 | every mitigation references a `library_id`; no library match ⇒ explicit `NONE_FOUND`, never invented |
| FR8 | Final report with machine-verified numbers | M | 9 | numeric verifier passes; mismatches ⇒ regeneration then `needs_review` (never silent) |
| FR9 | Persist + expose full trace (steps, LLM calls, guardrail events) and audit log | M | 9/10 | /trace returns complete run; audit rows exist for every mutating action |
| FR10 | SSE progress streaming + REST results | M | 10 | events received in order with monotonic seq; replay via Last-Event-ID |
| FR11 | Weight management API (create/update/version) | S | 10 | Σ=1 enforced; old analyses keep their weights_version |
| FR12 | EDGAR import (real filings) | S | 3 | feature-flagged; ≤10 req/s respected; us-gaap mapping documented; works for ≥3 test CIKs |
| FR13 | Deterministic-only mode (no LLM configured) | S | 9 | numeric pipeline completes; narrative layers `unavailable` |
| FR14 | Multi-scenario comparison matrix (N scenarios per analysis) | C | 10+ | API accepts scenario list; UI renders heatmap (Phase 11) |

## 2. Non-functional requirements

| ID | Requirement | Priority | Phase | Acceptance criteria |
|---|---|---|---|---|
| NFR1 | Determinism (R6) | M | 3–8 | same seed + inputs ⇒ byte-identical engine/twin outputs (asserted in tests) |
| NFR2 | Formula correctness | M | 4 | 100% registry coverage by hand-computed fixtures; property tests pass |
| NFR3 | Coverage ≥ 80% on `risk_engine`, `simulation`, `data_engine`, `guardrails` | M | 12 | pytest-cov report in Phase 12 |
| NFR4 | p95 run wall-clock < 5 min (LLM-dominated) | S | 12 | measured in Phase 12 report |
| NFR5 | Licensing-safe data handling (R5) | M | 3 | every cached file has license_tag + timestamp; no third-party data in git; attribution in outputs |
| NFR6 | Secrets only via env | M | 2 | no secret literals in repo; `.env.example` names only |
| NFR7 | Code quality: typed, linted, documented (R-series rules) | M | 2+ | ruff + mypy clean on CI (Phase 12); R3 import test passes |
| NFR8 | Docs + log updated per phase | M | all | phase reports include file lists with reasons |
| NFR9 | Provider-agnostic LLM (R7) | M | 9 | agent tests pass with FakeChatModel and with GLM adapter behind same interface |
| NFR10 | Offline capability (R4) | M | 3+ | full analysis completes with network disabled (synthetic path, degraded market/macro) |

## 3. Constraints & assumptions (frozen)

- Single-company analysis per run; monthly horizon ≤ 36 months; scenario bounds per
  [simulation.md](simulation.md) §3.
- GLM-5.3-Flash is the development LLM; the system must not depend on provider-specific features
  beyond the OpenAI-compatible chat interface.
- Threshold bands, twin assumptions, breach defaults are engineering choices — always disclosed in
  outputs (never presented as calibrated).
- The platform is decision support; outputs carry the not-financial-advice disclaimer (spec §23).
