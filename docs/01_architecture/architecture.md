# System Architecture — AI Business Risk (Phase 1 freeze)

**Status:** Frozen at Phase 1. Changes require the change-control procedure (state the change, impact,
affected files, replacement — wait for approval).

## 1. Topology

Single-host, three-container deployment for development and demo (production hardening is Phase 12):

```text
┌──────────────┐   HTTP/SSE /api/v1   ┌──────────────────────┐    SQLAlchemy    ┌────────────┐
│   frontend   │ ───────────────────▶ │  backend (FastAPI)   │ ───────────────▶ │ PostgreSQL │
│ React+Vite+TS│ ◀─────────────────── │  + LangGraph runtime │ ◀─────────────── │     16     │
└──────────────┘                      └──────────┬───────────┘                  └────────────┘
                                                 │ HTTPS (adapter per LLM_PROVIDER)
                                                 ▼
                                     ┌──────────────────────┐
                                     │  LLM provider (GLM-  │
                                     │  5.3-Flash dev dflt) │
                                     └──────────────────────┘
                                     Local disk: data/raw cache (FRED/Stooq/EDGAR downloads)
```

- `docker-compose.yml`: services `db` (postgres:16), `backend` (uvicorn), `frontend` (Vite dev server
  in dev; static build + nginx for demo). All backend state in PostgreSQL; third-party downloads
  cached on a mounted volume `data/raw`.
- The backend is a single Python process (no Celery/Redis): analysis runs execute in a background task
  with an in-process event bus feeding SSE. Deliberate simplification — a run is a single-user
  interactive workflow, and this removes two moving parts. The job interface is designed so a queue
  can be swapped in later without API changes (frozen interface:
  `analysis_service.start(...) -> analysis_id`; events flow through a publish/subscribe interface).

## 2. Layers and import rules (frozen)

```text
backend/
├── app/            FastAPI application (routers, SSE, DI)          → may import everything below
├── core/           config, security, errors                        → nothing internal except config
├── services/       run lifecycle, company/scenario/audit use-cases → engines, agents, database
├── agents/         LangGraph system (the only LLM consumer)        → llm, guardrails, engines (via tools), database
├── llm/            provider-agnostic adapters                      → langchain libraries only
├── guardrails/     pure validation/verification                    → pydantic only (no LLM, no DB)
├── risk_engine/    pure functions                                  → numpy/pandas only
├── ml_engine/      training + inference                            → sklearn/shap/pandas
├── simulation/     twin, scenarios, stress                         → numpy/pandas only
├── data_engine/    ingestion/validation/normalization/cache        → httpx/pandas/pydantic (no LLM)
├── database/       ORM + migrations                                → sqlalchemy/alembic
└── observability/  trace writers, metrics                          → database, structlog
```

**Architecture rule R3 (tested):** `risk_engine`, `simulation`, `ml_engine`, `data_engine`,
`guardrails` must never import from `agents`, `llm`, `app`, or `services`. Enforced by
`backend/tests/unit/test_architecture_imports.py` (created in Phase 2).

## 3. Request lifecycle (analysis run)

```text
POST /companies/{id}/analyses
  → 202 {analysis_id}                      (row in analyses: status=pending)
  → background task: load config + validated data from DB
  → LangGraph stream: every node emits node_started / node_completed / guardrail_event
  → event bus → SSE /analyses/{id}/events  (agent_steps / llm_calls / guardrail_events rows persist)
  → terminal: status = completed | failed | needs_review
  → results persisted (risk_assessments, risk_factors, explanations, mitigations, stress rows)
```

Run states (frozen): `pending → running → completed | failed | needs_review`, plus `cancelled`.
`needs_review` is a valid terminal state when human-review triggers fire (spec §24.11).

## 4. Determinism boundary

- Deterministic core = `data_engine` (normalization), `risk_engine`, `ml_engine` (inference),
  `simulation`, `guardrails`, `database`. No LLM calls; no wall-clock-dependent behavior except
  explicit timestamps; no randomness except the seeded synthetic generator (seeded ⇒ reproducible, R6).
- LLM usage is confined to `agents/` + `llm/`. Structured LLM steps (scenario translation, tool
  argument emission) request JSON/structured output with **temperature 0**; narrative steps use
  **temperature ≤ 0.3** (frozen defaults; per-run overrides allowed within guardrail limits).
- Every run persists its inputs snapshot, config, seed, and engine/registry/graph versions →
  re-executable for debugging or demonstration.

## 5. LLM abstraction (frozen design)

```python
# backend/llm/base.py — contract frozen here; implemented in Phase 9
class ProviderSettings(BaseModel):
    provider: Literal["glm", "openai", "gemini", "anthropic", "ollama"]
    model: str
    api_key_env: str
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int = 4096

def get_chat_model(settings: ProviderSettings) -> BaseChatModel: ...   # factory + registry
```

| Provider | Adapter | Mechanism | Notes |
|---|---|---|---|
| **glm (default)** | `providers/glm.py` | `langchain_openai.ChatOpenAI` with `base_url` from config | OpenAI-compatible endpoint (verified in [phase-0-research.md](../00_research/phase-0-research.md) §8): `https://api.z.ai/api/paas/v4` (international) or `https://open.bigmodel.cn/api/paas/v4` (domestic); default model `glm-5.3-flash` |
| openai | `providers/openai.py` | `langchain_openai.ChatOpenAI` | drop-in |
| gemini | `providers/gemini.py` | `langchain_google_genai.ChatGoogleGenerativeAI` | drop-in |
| anthropic | `providers/anthropic.py` | `langchain_anthropic.ChatAnthropic` | drop-in |
| ollama | `providers/ollama.py` | `langchain_ollama.ChatOllama` | local/offline |

- Agents never see provider details; they receive a LangChain `BaseChatModel`.
- `FakeChatModel` (same interface, scripted responses) lives in `backend/tests/` — see [testing.md](testing.md).
- Provider failures raise typed `LLMProviderError`; the agent node retries per policy (2 retries,
  backoff 2s/8s), then the run degrades (narrative layers marked `unavailable`) or fails per severity.
  Deterministic-only mode (no LLM key configured) runs the full numeric pipeline and marks narrative
  layers `unavailable` — the system remains useful (R4).

## 6. Configuration & secrets (frozen env names)

`pydantic-settings` reads env vars (documented in `.env.example`, values never committed):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://abr:abr@localhost:5432/abr` | Postgres DSN (`sqlite:///./abr_dev.db` in tests) |
| `LLM_PROVIDER` | `glm` | adapter selection |
| `GLM_API_KEY` / `GLM_MODEL` / `GLM_BASE_URL` | — / `glm-5.3-flash` / `https://api.z.ai/api/paas/v4` | GLM adapter |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL` | — | alternate providers |
| `FRED_API_KEY` | — | FRED macro ingestion |
| `DATA_CACHE_DIR` | `data/raw` | third-party download cache (git-ignored) |
| `RUN_BUDGET_TOKENS` | `200000` | guardrail 13 (token budget) |
| `RUN_TIMEOUT_SECONDS` | `600` | guardrail 8 (per-run timeout) |
| `LOG_LEVEL` | `INFO` | structlog level |
| `RUN_LIVE_SMOKE` | `0` | enables live-LLM smoke tests ([testing.md](testing.md)) |

## 7. Technology stack (frozen choices)

As frozen in [master-project-specification.md](../master-project-specification.md) §35, with freeze
pin-points: Python **3.11+**, PostgreSQL **16**, SQLAlchemy **2.x** + Alembic, FastAPI + Pydantic
**v2**, LangGraph **1.x** (MIT), pandas/NumPy 2.x, scikit-learn 1.x + shap, structlog, pytest,
ruff + mypy. Frontend (Phase 11): React 18+, Vite 5+, TypeScript 5+, Tailwind, TanStack Query,
ECharts + Recharts, GSAP + ScrollTrigger, Motion. Exact version pins happen in `pyproject.toml`
(Phase 2) and `package.json` (Phase 11) — this document freezes *choices*, not version numbers.

## 8. Error & degradation semantics (frozen)

| Failure | Behavior |
|---|---|
| Data validation below coverage threshold | run fails fast with coverage report (`failed`, code `DATA_COVERAGE_LOW`) |
| Tool error | error text returned to calling agent (≤2 retries); then finding marked `degraded` (never invented) |
| Guardrail block (bounds/permission/loop/timeout/budget) | `guardrail_events` row; severity `block` halts the run, `degrade` skips the step |
| Numeric verification failure | report regenerated (≤2 attempts), then terminal `needs_review` with mismatch list |
| LLM provider outage | retries, then deterministic-only completion (narrative layers `unavailable`) |
| Unexpected exception | run `failed` with structured error; partial trace preserved |

## 9. Deployment & operations (frozen scope)

Local Docker Compose for dev/demo; CLI utilities under `scripts/`; no Kubernetes. Backups, TLS, and
hosted deployment are out of scope (spec §13). Observability per spec §29: structlog JSON to stdout
(visible in compose logs); trace tables queried via API/UI; Prometheus `/metrics` added in Phase 12;
optional Langfuse export behind an interface.
