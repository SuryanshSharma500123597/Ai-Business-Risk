# Phase 2 — Foundation: Planning & Implementation Notes

**Status:** Complete — awaiting approval.
**Scope authority:** approved roadmap (Phase 2) + frozen Phase 1 contracts
(`docs/01_architecture/architecture.md`, `docs/01_architecture/database.md`, `docs/01_architecture/requirements.md`, `docs/01_architecture/testing.md`).
This directory holds Phase 2-specific planning and decisions; the frozen Phase 0/1 documents were
not modified.

## 1. Scope executed

- Repository skeleton (backend package tree: `app`, `core`, `database`, `tests`)
- `pyproject.toml` (package metadata, deps, pytest/coverage/ruff/mypy config)
- Configuration & environment handling (`backend/core/config.py`, `.env.example`)
- Structured logging (`backend/app/logging.py` — structlog JSON + run-id contextvars)
- Error envelope (`backend/core/errors.py` — frozen `docs/01_architecture/api.md` §1 codes)
- Database foundation (`backend/database/session.py`, `models.py`, Alembic env + `0001` migration)
- FastAPI app factory + `/api/v1/health` (`backend/app/main.py`, `app/api/deps.py`)
- Docker Compose foundation (`docker-compose.yml`: db + backend; frontend commented for Phase 11)
- Dockerfile (python:3.12-slim, installs the package, runs uvicorn)
- Test infrastructure: conftest with isolated per-test engine/settings caches; unit + integration
  suites incl. the R3 architecture-import test and the Alembic upgrade/downgrade/schema-match test

## 2. Environment findings & decisions (recorded for transparency)

| # | Finding / decision |
|---|---|
| E1 | Machine default was Python 3.10.0 (< frozen 3.11 floor) and no Docker daemon/CLI is installed. **Python 3.12.10 was installed** (winget, user scope) and the venv uses it — matches the Phase 1 freeze ("3.11+, 3.12 recommended"). |
| E2 | Docker absence means the compose stack is **written but not booted** (see known issues). All DB functionality verified via SQLite + Alembic CLI instead. |
| E3 | SQLite chosen as the test/dev fallback exactly per frozen F6 (`docs/01_architecture/requirements.md` NFR-context, `docs/01_architecture/database.md` §1 dialect map). JSONB→JSON and BIGINT→INTEGER variants implemented in `models.py`. |
| E4 | Dependencies are pinned by range in `pyproject.toml` and frozen exactly in `requirements-lock.txt` (pip freeze of the working venv). |
| E5 | `docs/` excluded from ruff targets — frozen Phase 0/1 documentation contains illustrative code fences that are not lint targets. |
| E6 | Live uvicorn boot smoke performed on port 8077 with a temp SQLite file; `/api/v1/health` returned the frozen contract shape; temp files removed afterward. |

## 3. Implementation decisions (within frozen contracts — no deviations)

| # | Decision | Rationale |
|---|---|---|
| D1 | `Financials` declared as an explicit class (not dynamic `type()`) | SQLAlchemy declarative scans annotations; explicit class avoids metaclass edge cases and keeps IDE/mypy support |
| D2 | `get_db` dependency commits on success, rolls back on exception | matches frozen session contract; request-scoped transaction |
| D3 | Engines cached via `lru_cache`; `reset_engine_cache()` used by the autouse test fixture | isolation per test without re-import |
| D4 | Migration `0001` hand-written to mirror `models.py` exactly; a test asserts column-set equality both ways | guarantees migration/model agreement (frozen `docs/01_architecture/database.md` §6) |
| D5 | structlog `PrintLoggerFactory` on stdout; JSON renderer; `cache_logger_on_first_use=False` | logs visible in compose; config changes apply inside test processes |
| D6 | Alembic `env.py` resolves URL from `alembic.ini` override else `DATABASE_URL` | CLI/tests/CI can point migrations at any database without code changes |
| D7 | Health route implemented inside `create_app()` for Phase 2 (no router module yet) | first router module arrives with real endpoints in Phase 3/10; avoids an empty-file placeholder |
| D8 | `Analysis` table created now (skeleton) though runs start in Phase 10 | frozen database.md §6 puts `analyses` in the Phase 2 core set |

## 4. Test results (final)

- pytest: **23 passed** (0 failed) — unit: config(4), errors(3), logging(2), architecture imports(1);
  integration: models(10), api health(2), migrations(1)
- ruff check: **clean** · ruff format: **clean** (25 files)
- mypy: **Success: no issues found in 21 source files** (pydantic mypy plugin enabled)
- Alembic CLI: upgrade → `0001 (head)` → downgrade base → re-upgrade verified; 9 tables present
- uvicorn boot smoke: `/api/v1/health` → `{"status":"ok","db":true,"llm":"not_configured","version":"0.1.0"}`

## 5. Known issues (non-blocking)

1. **Docker not verifiable on this machine** (no CLI/daemon). `docker-compose.yml` and `Dockerfile`
   are written to the frozen topology but the stack has not been booted here. First verifiable on a
   Docker-capable machine; the SQLite/Alembic path covers the same schema and app code paths.
2. Starlette emits deprecation warnings via TestClient (httpx/anyio aliases) and alembic logged one
   config deprecation before `path_separator = os` was added — all benign, none from project code.
3. `psycopg` (v3) is installed for PostgreSQL but **no live PostgreSQL connection was exercised** on
   this machine (no server available) — SQLite served all verification. Postgres-specific behavior
   (JSONB, identity BIGINT) is guarded by the dialect variants and will be CI-verified in Phase 12
   (frozen testing.md §2).

## 6. Deviations from Phase 1

**None.** All frozen contracts respected: env-var names (`docs/01_architecture/architecture.md` §6), error codes and
health response shape (`docs/01_architecture/api.md`), core-table set and conventions (`docs/01_architecture/database.md`), test
fixture strategy (`docs/01_architecture/testing.md`), R1–R7 untouched (R3 enforced by test). One addition outside
Phase 2's literal list but required by it: `requirements-lock.txt` (exact-version record requested in
the Phase 2 authorization).
