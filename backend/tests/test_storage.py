from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.data_engine.contracts import CompanyDataset, SyntheticCompanyConfig
from backend.data_engine.ingest.base import (
    MacroObservation,
    MacroSeries,
    MarketObservation,
    MarketSeries,
    SourceMetadata,
    SourceStatus,
)
from backend.data_engine.ingest.synthetic import generate_company
from backend.data_engine.storage import (
    load_company,
    load_macro_series,
    load_market_series,
    save_company,
    save_macro_series,
    save_market_series,
)
from backend.database.models import Company


def _series_metadata(source: str = "fixture") -> SourceMetadata:
    return SourceMetadata(
        source=source,
        url="fixture://local",
        license_tag="test",
        retrieved_at=datetime.now(UTC),
        cache_status="fixture",
        status=SourceStatus.FETCHED,
    )


def test_save_load_preserves_nulls_and_is_idempotent(db_session: Session) -> None:
    generated = generate_company(SyntheticCompanyConfig(seed=1001))
    dataset = CompanyDataset.model_validate(generated.model_dump(mode="json"))
    dataset.periods[0] = dataset.periods[0].model_copy(update={"dividends": None})
    company_id = uuid4()
    assert save_company(db_session, dataset, company_id=company_id) == company_id
    db_session.commit()
    assert save_company(db_session, dataset, company_id=company_id) == company_id
    assert db_session.scalar(select(func.count()).select_from(Company)) == 1
    loaded = load_company(db_session, company_id)
    assert loaded is not None
    assert loaded.periods[0].dividends is None
    assert len(loaded.periods) == len(dataset.periods)


def test_caller_can_roll_back_uncommitted_company(db_session: Session) -> None:
    generated = generate_company(SyntheticCompanyConfig(seed=1006))
    dataset = CompanyDataset.model_validate(generated.model_dump(mode="json"))
    company_id = uuid4()
    save_company(db_session, dataset, company_id=company_id)
    db_session.rollback()
    assert db_session.get(Company, company_id) is None


def test_conflicting_explicit_id_fails_without_overwrite(db_session: Session) -> None:
    generated = generate_company(SyntheticCompanyConfig(seed=1001))
    dataset = CompanyDataset.model_validate(generated.model_dump(mode="json"))
    company_id = uuid4()
    save_company(db_session, dataset, company_id=company_id)
    db_session.commit()
    conflicting_profile = dataset.profile.model_copy(update={"name": "Other"})
    conflicting = dataset.model_copy(update={"profile": conflicting_profile})
    with pytest.raises(ValueError, match="different dataset"):
        save_company(db_session, conflicting, company_id=company_id)
    assert (
        db_session.scalar(select(Company.name).where(Company.id == company_id))
        == dataset.profile.name
    )


def test_series_upsert_and_metadata_semantics(db_session: Session) -> None:
    metadata = _series_metadata()
    save_macro_series(
        db_session,
        MacroSeries(
            series_id="CPI",
            observations=[MacroObservation(date="2024-01-01", value=1.2)],
            metadata=metadata,
        ),
    )
    save_market_series(
        db_session,
        MarketSeries(
            symbol="ABC",
            observations=[MarketObservation(date="2024-01-01", close=10.0)],
            metadata=metadata,
        ),
    )
    db_session.commit()
    macro = load_macro_series(db_session, "CPI", source="fixture")
    market = load_market_series(db_session, "ABC", source="fixture")
    assert macro is not None and macro.observations[0].value == 1.2
    assert market is not None and market.observations[0].close == 10.0
    assert macro.metadata.detail["freshness"] == "unknown"
    assert market.metadata.license_tag == "test"
