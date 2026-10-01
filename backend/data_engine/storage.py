"""Canonical repositories over the existing schema; never commit or create tables.

The caller owns the transaction and must roll it back after a database failure.
No nested transaction/savepoint is opened (SQLite's legacy transaction mode can
otherwise commit a released first savepoint outside the caller's transaction).
Explicit company IDs are immutable: identical retries are no-ops, conflicting
payloads fail before writes. Concurrent insertion races are resolved by the DB's
unique constraints; the losing caller must rollback and retry.

Series tables retain only observation, source and license. Fetch URL, checksum,
TTL and retrieval time live in source_fetch_log/raw cache, not these tables.
Reads therefore mark freshness UNKNOWN (stale/degraded), never infer freshness
from the observation date or invent a successful fetch timestamp.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.data_engine.contracts import CompanyDataset, CompanyProfile, PeriodFinancials
from backend.data_engine.ingest.base import (
    MacroObservation,
    MacroSeries,
    MarketObservation,
    MarketSeries,
    SourceMetadata,
    SourceStatus,
)
from backend.data_engine.validate.schema_checks import enforce_coverage_gate, validate_dataset
from backend.database.models import Company, FinancialPeriod, Financials, MacroCache, MarketCache

PERIOD_FIELDS = ("period_start", "period_end", "fiscal_year", "quarter", "frequency", "source")
FINANCIAL_FIELDS = tuple(f for f in PeriodFinancials.model_fields if f not in PERIOD_FIELDS)


def save_company(
    session: Session, dataset: CompanyDataset, *, company_id: UUID | None = None
) -> UUID:
    """Validate every period, persist and flush; an explicit ID makes retries safe."""
    # Revalidate even model_copy/model_construct inputs before touching the session.
    dataset = CompanyDataset.model_validate(dataset.model_dump(mode="json"))
    enforce_coverage_gate(validate_dataset(dataset))
    if company_id is not None:
        existing = load_company(session, company_id)
        if existing is not None:
            if existing.model_dump(mode="json") != dataset.model_dump(mode="json"):
                raise ValueError(f"company {company_id} already exists with a different dataset")
            return company_id

    row = Company(
        **dataset.profile.model_dump(mode="json"),
        generator_config=(
            dataset.generator_config.model_dump(mode="json")
            if dataset.generator_config is not None
            else None
        ),
        edgar_cik=dataset.edgar_cik,
    )
    if company_id is not None:
        row.id = company_id
    session.add(row)
    session.flush()
    for period in dataset.periods:
        values = period.model_dump()
        period_row = FinancialPeriod(
            company_id=row.id, **{field: values[field] for field in PERIOD_FIELDS}
        )
        session.add(period_row)
        session.flush()
        # JSON mode serializes nested Pydantic exposures/buckets, keeping nulls.
        financials = period.model_dump(mode="json")
        session.add(
            Financials(
                period_id=period_row.id,
                **{field: financials[field] for field in FINANCIAL_FIELDS},
            )
        )
    session.flush()
    return row.id


def load_company(session: Session, company_id: UUID) -> CompanyDataset | None:
    """Return a canonical dataset in ascending period order, or None if absent."""
    row = session.get(Company, company_id)
    if row is None:
        return None
    records = session.execute(
        select(FinancialPeriod, Financials)
        .outerjoin(Financials, Financials.period_id == FinancialPeriod.id)
        .where(FinancialPeriod.company_id == company_id)
        .order_by(FinancialPeriod.period_end, FinancialPeriod.source)
    )
    periods = []
    for period, financials in records:
        if financials is None:
            raise ValueError(f"period {period.id} has no financials row")
        periods.append(
            PeriodFinancials.model_validate(
                {
                    **{field: getattr(period, field) for field in PERIOD_FIELDS},
                    **{field: getattr(financials, field) for field in FINANCIAL_FIELDS},
                }
            )
        )
    return CompanyDataset(
        profile=CompanyProfile.model_validate(
            {field: getattr(row, field) for field in CompanyProfile.model_fields}
        ),
        periods=periods,
        generator_config=row.generator_config,
        edgar_cik=row.edgar_cik,
    )


def _check_series(series: MacroSeries | MarketSeries) -> None:
    import math

    if not series.metadata.source.strip() or not series.metadata.license_tag.strip():
        raise ValueError("series source and license_tag must not be empty")
    dates = [point.date for point in series.observations]
    if len(set(dates)) != len(dates):
        raise ValueError("duplicate observation dates")
    for point in series.observations:
        value = point.value if isinstance(point, MacroObservation) else point.close
        if not math.isfinite(value):
            raise ValueError("observation values must be finite")


def save_macro_series(session: Session, series: MacroSeries) -> None:
    """Upsert provided dates only; preserve other sources and unmentioned dates."""
    _check_series(series)
    for point in series.observations:
        session.merge(
            MacroCache(
                series_id=series.series_id,
                date=point.date,
                value=point.value,
                source=series.metadata.source,
                license_tag=series.metadata.license_tag,
            )
        )
    session.flush()


def save_market_series(session: Session, series: MarketSeries) -> None:
    """Upsert provided dates only; preserve other sources and unmentioned dates."""
    _check_series(series)
    for point in series.observations:
        session.merge(
            MarketCache(
                symbol=series.symbol,
                date=point.date,
                close=point.close,
                source=series.metadata.source,
                license_tag=series.metadata.license_tag,
            )
        )
    session.flush()


def _database_metadata(source: str, licenses: set[str]) -> SourceMetadata:
    if len(licenses) != 1:
        raise ValueError("mixed license tags in stored series; cannot assign one series license")
    return SourceMetadata(
        source=source,
        license_tag=next(iter(licenses)),
        url="",
        retrieved_at=datetime(1970, 1, 1, tzinfo=UTC),
        status=SourceStatus.STALE_CACHE,
        cache_status="database_unverified",
        detail={
            "freshness": "unknown",
            "retrieved_at_known": False,
            "warning": "database stores no fetch metadata; epoch timestamp means unknown",
        },
    )


def load_macro_series(session: Session, series_id: str, *, source: str) -> MacroSeries | None:
    rows = session.scalars(
        select(MacroCache)
        .where(MacroCache.series_id == series_id, MacroCache.source == source)
        .order_by(MacroCache.date)
    ).all()
    if not rows:
        return None
    return MacroSeries(
        series_id=series_id,
        observations=[MacroObservation(date=row.date, value=row.value) for row in rows],
        metadata=_database_metadata(source, {row.license_tag for row in rows}),
    )


def load_market_series(session: Session, symbol: str, *, source: str) -> MarketSeries | None:
    rows = session.scalars(
        select(MarketCache)
        .where(MarketCache.symbol == symbol, MarketCache.source == source)
        .order_by(MarketCache.date)
    ).all()
    if not rows:
        return None
    return MarketSeries(
        symbol=symbol,
        observations=[MarketObservation(date=row.date, close=row.close) for row in rows],
        metadata=_database_metadata(source, {row.license_tag for row in rows}),
    )


# Verbose aliases make the transaction boundary obvious to service callers.
persist_company = save_company
read_company = load_company
persist_macro_series = save_macro_series
read_macro_series = load_macro_series
persist_market_series = save_market_series
read_market_series = load_market_series
