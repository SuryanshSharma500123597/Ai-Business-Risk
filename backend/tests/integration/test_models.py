"""Core-table model tests against SQLite (frozen schema: docs/01_architecture/database.md §2)."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.models import (
    AggregationWeights,
    Analysis,
    Company,
    FinancialPeriod,
    Financials,
    MacroCache,
    MarketCache,
    User,
)


def make_company(**overrides: object) -> Company:
    values: dict[str, object] = {
        "name": "Acme Manufacturing",
        "sector": "manufacturing",
        "currency": "INR",
        "data_origin": "synthetic",
    }
    values.update(overrides)
    return Company(**values)  # pyright: ignore[reportCallIssue]


def test_company_period_financials_roundtrip(db_session: Session) -> None:
    company = make_company(generator_config={"seed": 1001, "sector": "manufacturing"})
    db_session.add(company)
    db_session.flush()

    period = FinancialPeriod(
        company_id=company.id,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        fiscal_year=2024,
        quarter=None,
        frequency="monthly",
        source="synthetic",
    )
    db_session.add(period)
    db_session.flush()

    financials = Financials(
        period_id=period.id,
        revenue=1_000_000.0,
        cogs=600_000.0,
        cash=150_000.0,
        interest_expense=8_000.0,
        customers=[{"name_hash": "h1", "share": 0.6}, {"name_hash": "h2", "share": 0.4}],
        fx_exposure={"import_cost_share": 0.15, "foreign_revenue_share": 0.05},
    )
    db_session.add(financials)
    db_session.commit()

    loaded = db_session.get(Financials, financials.id)
    assert loaded is not None
    assert loaded.customers is not None
    assert loaded.fx_exposure is not None
    assert loaded.revenue == 1_000_000.0
    assert loaded.customers[0]["share"] == 0.6
    assert loaded.fx_exposure["import_cost_share"] == 0.15
    loaded_company = db_session.get(Company, company.id)
    assert loaded_company is not None
    assert loaded_company.data_origin == "synthetic"


def test_invalid_data_origin_rejected(db_session: Session) -> None:
    db_session.add(make_company(data_origin="guessed"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_period_rejected(db_session: Session) -> None:
    company = make_company()
    db_session.add(company)
    db_session.flush()
    for _ in range(2):
        db_session.add(
            FinancialPeriod(
                company_id=company.id,
                period_start=date(2024, 1, 1),
                period_end=date(2024, 1, 31),
                frequency="monthly",
                source="synthetic",
            )
        )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_invalid_frequency_rejected(db_session: Session) -> None:
    company = make_company()
    db_session.add(company)
    db_session.flush()
    db_session.add(
        FinancialPeriod(
            company_id=company.id,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 1, 31),
            frequency="weekly",
            source="synthetic",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_market_cache_composite_pk(db_session: Session) -> None:
    row = MarketCache(
        symbol="^spx",
        date=date(2026, 1, 5),
        source="stooq",
        close=5_800.0,
        license_tag="personal-use-flagged",
    )
    db_session.add(row)
    db_session.commit()
    db_session.add(
        MarketCache(
            symbol="^spx",
            date=date(2026, 1, 5),
            source="stooq",
            close=5_801.0,
            license_tag="personal-use-flagged",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    # same (symbol, date) under a different source is a distinct row
    db_session.rollback()
    db_session.expunge_all()
    db_session.add(
        MarketCache(
            symbol="^spx",
            date=date(2026, 1, 5),
            source="yahoo",
            close=5_800.5,
            license_tag="tos-restricted-flagged",
        )
    )
    db_session.commit()
    assert db_session.query(MarketCache).count() == 2


def test_macro_cache_roundtrip(db_session: Session) -> None:
    db_session.add(
        MacroCache(
            series_id="FEDFUNDS",
            date=date(2026, 8, 1),
            source="fred",
            value=3.63,
            license_tag="attribution-required",
        )
    )
    db_session.commit()
    row = db_session.scalar(select(MacroCache).where(MacroCache.series_id == "FEDFUNDS"))
    assert row is not None and row.value == 3.63


def test_analysis_weights_user_roundtrip(db_session: Session) -> None:
    company = make_company()
    db_session.add(company)
    db_session.flush()

    dimensions = (
        "financial_strength",
        "liquidity",
        "market",
        "credit",
        "operational",
        "concentration",
        "macro",
    )
    weights = AggregationWeights(
        name="default",
        weights={d: 1 / 7 for d in dimensions},
        is_default=True,
    )
    db_session.add(weights)
    db_session.flush()

    analysis = Analysis(
        company_id=company.id,
        config={"include_ml": True, "scenario": {"mode": "none"}},
        weights_id=weights.id,
        seed=42,
    )
    db_session.add(analysis)
    db_session.add(User(email="analyst@example.com", password_hash="argon2id$...", role="analyst"))
    db_session.commit()

    loaded = db_session.get(Analysis, analysis.id)
    assert loaded is not None
    assert loaded.status == "pending"
    assert loaded.weights_id == weights.id
    user = db_session.scalar(select(User).where(User.email == "analyst@example.com"))
    assert user is not None and user.role == "analyst"


def test_invalid_analysis_status_rejected(db_session: Session) -> None:
    company = make_company()
    db_session.add(company)
    db_session.flush()
    db_session.add(Analysis(company_id=company.id, config={}, status="finished"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_user_email_rejected(db_session: Session) -> None:
    for _ in range(2):
        db_session.add(User(email="dup@example.com", password_hash="x", role="analyst"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_uuid_defaults_generated(db_session: Session) -> None:
    company = make_company()
    db_session.add(company)
    db_session.flush()
    assert isinstance(company.id, uuid.UUID)
    assert company.created_at is not None
