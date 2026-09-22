"""FastAPI application factory.

Phase 2 scope: app factory + health endpoint (docs/01_architecture/api.md §2). Routers for
companies/analyses/scenarios arrive in their phases (3, 9, 10).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text

from backend.app.logging import configure_logging
from backend.core.config import get_settings
from backend.database.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield
    get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        current = get_settings()
        with get_engine().connect() as conn:
            db_ok = conn.execute(text("SELECT 1")).scalar() == 1
        return {
            "status": "ok" if db_ok else "degraded",
            "db": db_ok,
            "llm": "configured" if current.llm_configured else "not_configured",
            "version": current.app_version,
        }

    return app


app = create_app()
