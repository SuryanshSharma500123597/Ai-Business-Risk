"""Shared pytest fixtures.

DATABASE_URL is set at module import time (before any backend import) so
module-level singletons like backend.app.main.app see the test database.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from backend.core.config import get_settings  # noqa: E402
from backend.database.models import Base  # noqa: E402
from backend.database.session import reset_engine_cache  # noqa: E402

GOLDEN_UPDATE_OPTION = "--regen-golden"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--regen-golden`` (testing.md §4).

    Golden files are committed JSON and are regenerated *only* through this flag,
    with the regeneration diff reviewed and noted in the development log.
    """
    parser.addoption(
        GOLDEN_UPDATE_OPTION,
        action="store_true",
        default=False,
        help="Regenerate the committed golden baselines in backend/tests/golden/.",
    )


@pytest.fixture()
def regen_golden(request: pytest.FixtureRequest) -> bool:
    """True when the run was invoked with ``--regen-golden``."""
    return bool(request.config.getoption(GOLDEN_UPDATE_OPTION))


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Each test gets a fresh Settings/engine cache bound to an in-memory DB."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    get_settings.cache_clear()
    reset_engine_cache()
    yield
    get_settings.cache_clear()
    reset_engine_cache()


@pytest.fixture()
def db_session() -> Iterator[Session]:
    """Isolated SQLite session with all tables created via ORM metadata."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()
