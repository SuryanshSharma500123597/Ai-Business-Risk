# Testing Strategy — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. Executed from Phase 2 onward. Framework: pytest (+ pytest-cov,
hypothesis where valuable — a Phase-1 plan only, see the note below). Frontend: Vitest + Playwright (Phase 11/12).

> **Implementation note (recorded at Phase 4 closure):** Hypothesis was **not** adopted. It is not
> installed and not declared in `pyproject.toml`, and no test imports it. `backend/tests/property/`
> implements the property suite with plain deterministic seeded randomization (`random.Random(42)`).
> §7 records what is actually implemented and measured.

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

## 7. Implementation status (recorded at Phase 4 documentation closure)

This section records what the repository actually contains and what was actually run; it supersedes any
"planned" reading of §1–§6. No claim in this section is aspirational.

| Area | Actual status | Where |
|---|---|---|
| Hand-computed fixtures | 40 fixtures — one per registry formula, each with the exact expected value and the formula's frozen edge case | `backend/tests/unit/test_risk_fixtures.py` |
| Registry-walking coverage | Fixture-existence, orphan, anchor-table well-formedness, endpoint-clamping and version-stamping tests ⇒ **40/40** formulas covered (NFR2 enforced mechanically) | `backend/tests/unit/test_registry_coverage.py` |
| Property tests | Deterministic **seeded** invariants (`random.Random(42)`): clamping, monotonicity, anchor continuity, U-shaped (two-sided) DPO non-monotonicity, scale invariance of pure ratios, additive dimension/composite reconciliation. **Hypothesis is not used.** | `backend/tests/property/test_risk_properties.py` (8 tests) |
| Golden baselines | JSON per canonical seed 1001–1005, compared at `abs_tol = 1e-9`, regenerated only through `pytest --regen-golden`; a registry-version mismatch fails the golden test | `backend/tests/golden/test_golden_profiles.py` + `seed_100*.json` |
| Engine behaviour | Interpolation, severity labels, full engine execution, sensitivity not corrupting contributions, all-missing behavior, configured-vs-effective weights, custom-weight reconciliation | `backend/tests/unit/test_risk_engine.py` (21 tests) |
| Stage 5 routing | Distinct beta legs, hand-computed covariance/variance, perfect correlation, zero benchmark variance, 120-observation boundary, inner join + joined count, missing legs, mixed-currency rejection, legacy `market_series` cannot force β = 1.0, input mutual exclusion, VaR/ES equity leg, macro routing, macro short history, provenance stamping, `WeightsRef` contract-only, FX/equity separation, adapter log-return and helper math | `backend/tests/unit/test_stage5_*.py` (27 tests) |
| Canonical-seed engine smoke | Structural and determinism assertions for seeds 1001–1005 | `backend/tests/unit/test_golden_risk.py` (5 tests) |
| Notebook execution | Fresh-kernel top-to-bottom execution of the Phase 3, Phase 4 and Stage 5 notebooks | `notebooks/03_data_engineering/`, `notebooks/04_quantitative_risk/` |

Measured at Phase 4 closure:

```text
pytest -q                    -> 223 passed
risk_engine line coverage    -> 94%    (NFR3 target >= 80%)
registry coverage            -> 40/40
contribution reconciliation  -> 5/5    (abs_tol = 1e-9)
golden baselines             -> 5/5    (seeds 1001-1005)
ruff check backend scripts   -> All checks passed!
ruff format --check backend  -> 87 files already formatted
mypy backend                 -> Success: no issues found (83 files)
```

Ruff is run over the Python code targets (`backend/`, `scripts/`). Ruff also lints **notebook cell code**
by default, and `ruff check .` reports 19 notebook-cell findings (E402/I001/E501 caused by the
intentional `sys.path` bootstrap in the notebooks' setup cells) plus 3 notebooks that `ruff format .`
would reformat. This is recorded as a known condition; no code-target file has a Ruff finding.

Not yet implemented — these must not be claimed as done:

- Hypothesis property testing (see the implementation note in the header).
- Coverage is measured for `risk_engine` at 94%; the NFR3 targets for `simulation`, `data_engine` and
  `guardrails` belong to the phases that create those packages, and there is no "100% generic coverage"
  claim anywhere.
- Golden baselines currently cover composite **risk** profiles for the canonical seeds; twin-trajectory
  goldens arrive with the digital twin (Phase 6).
- CI workflow, Postgres-marked suite, `FakeChatModel` agent tests, recorded transcripts and
  `RUN_LIVE_SMOKE` runs are Phase 9/12 items and do not exist yet.

## 7. What is explicitly not tested / deferred

- Long-running soak/performance benches (only NFR4 measurement in Phase 12).
- Multi-tenant/security pentesting (out of scope, spec §13).
- LLM output *quality* judgments (evaluated separately in Phase 13 experiments — measured, not
  asserted in tests).
