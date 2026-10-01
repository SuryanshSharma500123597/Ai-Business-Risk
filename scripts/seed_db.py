#!/usr/bin/env python3
"""Validate, normalize and persist canonical company JSON through Alembic schema."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config

from backend.core.config import get_settings
from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.data_engine.normalize.periods import sort_periods
from backend.data_engine.storage import save_company
from backend.database.session import get_session_factory, reset_engine_cache

REPO_ROOT = Path(__file__).resolve().parents[1]


def _alembic_upgrade(database_url: str) -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")


def _load_payload(path: Path) -> tuple[dict, UUID | None]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input JSON must be an object")
    explicit_id = UUID(payload.pop("id")) if payload.get("id") else None
    return payload, explicit_id


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("input", type=Path, help="canonical company JSON")
    result.add_argument("--database-url", default=None)
    result.add_argument("--company-id", type=UUID, default=None)
    result.add_argument(
        "--generate", action="store_true", help="treat input as SyntheticCompanyConfig JSON"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        database_url = (
            args.database_url or os.environ.get("DATABASE_URL") or get_settings().database_url
        )
        _alembic_upgrade(database_url)
        # Keep the ORM session on the same migrated URL when --database-url is used.
        os.environ["DATABASE_URL"] = database_url
        get_settings.cache_clear()
        reset_engine_cache()
        payload, file_id = _load_payload(args.input)
        from backend.data_engine.contracts import CompanyDataset
        from backend.data_engine.validate.schema_checks import (
            enforce_coverage_gate,
            validate_dataset,
        )

        if args.generate:
            company = generate_company(SyntheticCompanyConfig.model_validate(payload))
            dataset = CompanyDataset.model_validate(company.model_dump(mode="json"))
        else:
            dataset = CompanyDataset.model_validate(payload)
        dataset = dataset.model_copy(update={"periods": sort_periods(dataset.periods)})
        report = validate_dataset(dataset)
        print(json.dumps(report.summary, indent=2))
        enforce_coverage_gate(report)
        company_id = args.company_id or file_id
        with get_session_factory()() as session:
            persisted_id = save_company(session, dataset, company_id=company_id)
            session.commit()
        print(f"seeded company {persisted_id} ({len(dataset.periods)} periods)")
        return 0
    except Exception as exc:  # CLI must give a clear failure without traceback by default.
        print(f"seed failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
