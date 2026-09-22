"""SQLAlchemy ORM models — Phase 2 core tables (frozen: docs/01_architecture/database.md §6).

Phase 2 scope: companies, financial_periods, financials, market_cache,
macro_cache, source_fetch_log, analyses (skeleton), aggregation_weights,
users (stub). Results/observability tables arrive with their phases.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSON on SQLite, JSONB on PostgreSQL (docs/01_architecture/database.md §1).
JSONType = JSON().with_variant(postgresql.JSONB(), "postgresql")

# BIGINT identity on PostgreSQL, plain INTEGER PRIMARY KEY on SQLite
# (SQLite rowid autoincrement requires exactly INTEGER).
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("data_origin IN ('synthetic', 'manual', 'edgar')", name="data_origin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="INR")
    description: Mapped[str | None] = mapped_column(Text)
    data_origin: Mapped[str] = mapped_column(Text, nullable=False)
    generator_config: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    edgar_cik: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (
        UniqueConstraint("company_id", "period_end", "source", name="uq_company_period_source"),
        CheckConstraint("frequency IN ('monthly', 'quarterly', 'annual')", name="frequency"),
        Index("ix_financial_periods_company_id", "company_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int | None]
    quarter: Mapped[int | None]
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Financials(Base):
    __tablename__ = "financials"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    period_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # --- income statement ---
    revenue: Mapped[float | None] = mapped_column(Double)
    cogs: Mapped[float | None] = mapped_column(Double)
    gross_profit: Mapped[float | None] = mapped_column(Double)
    opex: Mapped[float | None] = mapped_column(Double)
    ebitda: Mapped[float | None] = mapped_column(Double)
    da: Mapped[float | None] = mapped_column(Double)
    ebit: Mapped[float | None] = mapped_column(Double)
    interest_expense: Mapped[float | None] = mapped_column(Double)
    tax: Mapped[float | None] = mapped_column(Double)
    net_income: Mapped[float | None] = mapped_column(Double)
    # --- balance sheet ---
    cash: Mapped[float | None] = mapped_column(Double)
    receivables: Mapped[float | None] = mapped_column(Double)
    inventory: Mapped[float | None] = mapped_column(Double)
    payables: Mapped[float | None] = mapped_column(Double)
    current_assets: Mapped[float | None] = mapped_column(Double)
    current_liabilities: Mapped[float | None] = mapped_column(Double)
    total_assets: Mapped[float | None] = mapped_column(Double)
    total_liabilities: Mapped[float | None] = mapped_column(Double)
    equity: Mapped[float | None] = mapped_column(Double)
    total_debt: Mapped[float | None] = mapped_column(Double)
    st_debt: Mapped[float | None] = mapped_column(Double)
    lt_debt: Mapped[float | None] = mapped_column(Double)
    # --- cash flow ---
    capex: Mapped[float | None] = mapped_column(Double)
    ocf: Mapped[float | None] = mapped_column(Double)
    fcf: Mapped[float | None] = mapped_column(Double)
    dividends: Mapped[float | None] = mapped_column(Double)
    # --- concentration buckets / exposures (JSONB on PG) ---
    customers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    suppliers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    products: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    regions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    fx_exposure: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    commodity_exposure: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    rate_exposure: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    debt_schedule: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    quality_flags: Mapped[list[str] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MarketCache(Base):
    __tablename__ = "market_cache"

    symbol: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    close: Mapped[float] = mapped_column(Double, nullable=False)
    license_tag: Mapped[str] = mapped_column(Text, nullable=False)


class MacroCache(Base):
    __tablename__ = "macro_cache"

    series_id: Mapped[str] = mapped_column(Text, primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[float] = mapped_column(Double, nullable=False)
    license_tag: Mapped[str] = mapped_column(Text, nullable=False)


class SourceFetchLog(Base):
    __tablename__ = "source_fetch_log"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    license_tag: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    checksum: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONType)


class AggregationWeights(Base):
    __tablename__ = "aggregation_weights"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'needs_review', 'cancelled')",
            name="status",
        ),
        Index("ix_analyses_company_id_created_at", "company_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    weights_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("aggregation_weights.id"), nullable=True
    )
    seed: Mapped[int | None]
    engine_version: Mapped[str | None] = mapped_column(Text)
    registry_version: Mapped[str | None] = mapped_column(Text)
    graph_version: Mapped[str | None] = mapped_column(Text)
    input_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('analyst', 'admin')", name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="analyst")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
