# Testing Strategy — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. Executed from Phase 2 onward. Framework: pytest (+ pytest-cov,
hypothesis where valuable). Frontend: Vitest + Playwright (Phase 11/12).

## 1. Test pyramid (frozen)

| Level | Scope | Location | Runs |
|---|---|---|---|
| Unit | engines, guardrails, normalizers, scoring, verifier — pure functions | `backend/tests/unit/` | every commit (local + CI) |
| Property | invariants: monotonicity, identities, clamping, waterfall closure | `backend/tests/property/` | every commit |
| Golden | regression baselines for twin trajectories and composite profiles | `backend/tests/golden/` | every commit |
| Integration | DB repositories, services, SSE, API via `httpx.AsyncClient` | `backend/tests/integration/` | every commit |
| Agent | graph behavior with `FakeChatModel` + recorded transcripts | `backend/tests/agents/` | every commit |
| Live smoke | one real LLM call per agent against GLM behind `RUN_LIVE_SMOKE=1` | `backend/tests/agents/` | manual/nightly |
| E2E | compose up → scripted API flow → assertions | `backend/tests/e2e/` | Phase 12 |
| Frontend | Vitest components; Playwright smoke of the 8 routes | `frontend/` | Phase 11/12 |

## 2. Canonical fixtures (frozen)

- **Fixture companies:** generated on demand from the synthetic generator with frozen seeds
  **1001–1005** (manufacturing/healthy, manufacturing/stressed, retail/seasonal, services_saas/stable,
  manufacturing/concentrated+injected anomalies). No binary fixtures; tests regenerate deterministically
  (R6).
- **Macro/market fixtures:** tiny frozen CSVs under `backend/tests/fixtures/` (hand-written, not
  downloaded) so engine tests never touch the network.
- **DB:** integration tests run on SQLite in-memory; one Postgres-marked suite (optional locally, CI
  in Phase 12) guards Postgres-specific behavior (JSONB, identity columns).

## 3. LLM testing approach (frozen)

1. **`FakeChatModel`** (LangChain `BaseChatModel` subclass) with per-node scripted responses — tests
   the graph logic, routing, retries, guardrails deterministically.
2. **Recorded transcripts:** JSON transcripts (prompt sha → response) captured once against GLM in
   Phase 9 and replayed in CI to catch prompt/parser regressions without live calls.
3. **Live smoke** (`RUN_LIVE_SMOKE=1`, skipped by default): one real call per agent + one end-to-end
   run; asserts structured-output validity only (no quality judgment).
4. **Numeric verification tests:** adversarial cases — wrong numbers, transposed digits, unit errors,
   invented values — must be caught by the verifier (unit tests in Phase 9).

## 4. Golden-file policy (frozen)

Golden files are committed JSON (`backend/tests/golden/*.json`), regenerated only by
`pytest --regen-golden` **with the regeneration diff reviewed and noted in the development log**. A
golden change without a registry/twin version bump is a defect.

## 5. Coverage targets (frozen)

- ≥ 80% lines on `risk_engine`, `simulation`, `data_engine`, `guardrails` (NFR3) — measured Phase 12.
- 100% of registry formulas covered by fixture tests (NFR2) — enforced by a test that walks the
  registry and asserts a fixture exists per formula id.
- Agent graph: every node exercised in ≥1 FakeChatModel test; every guardrail rule has ≥1 trigger test
  and ≥1 pass-through test.

## 6. CI plan (frozen; implemented Phase 12)

GitHub Actions: ruff + mypy → pytest unit/property/golden/integration/agent (SQLite) → optional
Postgres service job → coverage report. Live smoke scheduled nightly (skipped without secrets).
Frontend: lint + Vitest on PRs from Phase 11.

## 7. What is explicitly not tested / deferred

- Long-running soak/performance benches (only NFR4 measurement in Phase 12).
- Multi-tenant/security pentesting (out of scope, spec §13).
- LLM output *quality* judgments (evaluated separately in Phase 13 experiments — measured, not
  asserted in tests).
