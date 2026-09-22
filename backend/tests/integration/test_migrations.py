"""Migration tests: upgrade/downgrade roundtrip and schema/model agreement."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from backend.database.models import Base

REPO_ROOT = Path(__file__).resolve().parents[3]


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_upgrade_downgrade_and_schema_match(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'migration_check.db'}"
    cfg = _alembic_config(db_url)

    # --- upgrade head ---
    command.upgrade(cfg, "head")
    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = set(Base.metadata.tables) | {"alembic_version"}
        assert tables == expected, f"missing={expected - tables}, extra={tables - expected}"

        for table_name, table in Base.metadata.tables.items():
            migrated = {col["name"] for col in inspector.get_columns(table_name)}
            modeled = set(table.columns.keys())
            assert migrated == modeled, (
                f"{table_name}: missing={modeled - migrated}, extra={migrated - modeled}"
            )
    finally:
        engine.dispose()

    # --- downgrade base empties the schema (alembic keeps its version table) ---
    command.downgrade(cfg, "base")
    engine = create_engine(db_url)
    try:
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    finally:
        engine.dispose()

    # --- re-upgrade is idempotent from scratch ---
    command.upgrade(cfg, "head")
