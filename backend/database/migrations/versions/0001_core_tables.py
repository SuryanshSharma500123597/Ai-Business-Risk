"""core tables (Phase 2)

companies, financial_periods, financials, market_cache, macro_cache,
source_fetch_log, aggregation_weights, analyses (skeleton), users (stub) —
frozen schema: docs/01_architecture/database.md.

Revision ID: 0001
Revises:
Create Date: 2026-09-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mirror backend.database.models type helpers (JSONB on PG, JSON on SQLite).
JSONType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_origin", sa.Text(), nullable=False),
        sa.Column("generator_config", JSONType, nullable=True),
        sa.Column("edgar_cik", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "data_origin IN ('synthetic', 'manual', 'edgar')",
            name="ck_companies_data_origin",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_companies"),
    )

    op.create_table(
        "financial_periods",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("quarter", sa.Integer(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "frequency IN ('monthly', 'quarterly', 'annual')",
            name="ck_financial_periods_frequency",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_financial_periods"),
        sa.UniqueConstraint("company_id", "period_end", "source", name="uq_company_period_source"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_financial_periods_company_id_companies",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_financial_periods_company_id", "financial_periods", ["company_id"], unique=False
    )

    op.create_table(
        "financials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("period_id", sa.Uuid(), nullable=False),
        sa.Column("revenue", sa.Double(), nullable=True),
        sa.Column("cogs", sa.Double(), nullable=True),
        sa.Column("gross_profit", sa.Double(), nullable=True),
        sa.Column("opex", sa.Double(), nullable=True),
        sa.Column("ebitda", sa.Double(), nullable=True),
        sa.Column("da", sa.Double(), nullable=True),
        sa.Column("ebit", sa.Double(), nullable=True),
        sa.Column("interest_expense", sa.Double(), nullable=True),
        sa.Column("tax", sa.Double(), nullable=True),
        sa.Column("net_income", sa.Double(), nullable=True),
        sa.Column("cash", sa.Double(), nullable=True),
        sa.Column("receivables", sa.Double(), nullable=True),
        sa.Column("inventory", sa.Double(), nullable=True),
        sa.Column("payables", sa.Double(), nullable=True),
        sa.Column("current_assets", sa.Double(), nullable=True),
        sa.Column("current_liabilities", sa.Double(), nullable=True),
        sa.Column("total_assets", sa.Double(), nullable=True),
        sa.Column("total_liabilities", sa.Double(), nullable=True),
        sa.Column("equity", sa.Double(), nullable=True),
        sa.Column("total_debt", sa.Double(), nullable=True),
        sa.Column("st_debt", sa.Double(), nullable=True),
        sa.Column("lt_debt", sa.Double(), nullable=True),
        sa.Column("capex", sa.Double(), nullable=True),
        sa.Column("ocf", sa.Double(), nullable=True),
        sa.Column("fcf", sa.Double(), nullable=True),
        sa.Column("dividends", sa.Double(), nullable=True),
        sa.Column("customers", JSONType, nullable=True),
        sa.Column("suppliers", JSONType, nullable=True),
        sa.Column("products", JSONType, nullable=True),
        sa.Column("regions", JSONType, nullable=True),
        sa.Column("fx_exposure", JSONType, nullable=True),
        sa.Column("commodity_exposure", JSONType, nullable=True),
        sa.Column("rate_exposure", JSONType, nullable=True),
        sa.Column("debt_schedule", JSONType, nullable=True),
        sa.Column("quality_flags", JSONType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_financials"),
        sa.UniqueConstraint("period_id", name="uq_financials_period_id"),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["financial_periods.id"],
            name="fk_financials_period_id_financial_periods",
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "market_cache",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("close", sa.Double(), nullable=False),
        sa.Column("license_tag", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "date", "source", name="pk_market_cache"),
    )

    op.create_table(
        "macro_cache",
        sa.Column("series_id", sa.Text(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("license_tag", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("series_id", "date", "source", name="pk_macro_cache"),
    )

    op.create_table(
        "source_fetch_log",
        sa.Column("id", BigIntPK, nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("license_tag", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("detail", JSONType, nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_source_fetch_log"),
    )

    op.create_table(
        "aggregation_weights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("weights", JSONType, nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_aggregation_weights"),
    )

    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("config", JSONType, nullable=False),
        sa.Column("weights_id", sa.Uuid(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("engine_version", sa.Text(), nullable=True),
        sa.Column("registry_version", sa.Text(), nullable=True),
        sa.Column("graph_version", sa.Text(), nullable=True),
        sa.Column("input_snapshot", JSONType, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", JSONType, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'needs_review', 'cancelled')",
            name="ck_analyses_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analyses"),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name="fk_analyses_company_id_companies"
        ),
        sa.ForeignKeyConstraint(
            ["weights_id"],
            ["aggregation_weights.id"],
            name="fk_analyses_weights_id_aggregation_weights",
        ),
    )
    op.create_index(
        "ix_analyses_company_id_created_at", "analyses", ["company_id", "created_at"], unique=False
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('analyst', 'admin')", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_index("ix_analyses_company_id_created_at", table_name="analyses")
    op.drop_table("analyses")
    op.drop_table("aggregation_weights")
    op.drop_table("source_fetch_log")
    op.drop_table("macro_cache")
    op.drop_table("market_cache")
    op.drop_table("financials")
    op.drop_index("ix_financial_periods_company_id", table_name="financial_periods")
    op.drop_table("financial_periods")
    op.drop_table("companies")
