"""add OpenCorporates financial enrichment tables

Revision ID: d4e8f1a6c2b9
Revises: c91d7a0e5b3f
Create Date: 2026-06-19 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e8f1a6c2b9"
down_revision: Union[str, None] = "c91d7a0e5b3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opencorporates_company_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nipt", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("page_found", sa.Boolean(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=True),
        sa.Column("has_financial_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_revenue_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_profit_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("financial_year_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("min_financial_year", sa.Integer(), nullable=True),
        sa.Column("max_financial_year", sa.Integer(), nullable=True),
        sa.Column("financial_document_links_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("historical_extract_links_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("visible_csv_json_controls", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("parse_status", sa.String(length=50), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opencorporates_company_profiles")),
        sa.UniqueConstraint("nipt", name="uq_opencorporates_company_profile_nipt"),
    )
    with op.batch_alter_table("opencorporates_company_profiles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_opencorporates_company_profiles_nipt"), ["nipt"], unique=False)
        batch_op.create_index(batch_op.f("ix_opencorporates_company_profiles_parse_status"), ["parse_status"], unique=False)
        batch_op.create_index(batch_op.f("ix_opencorporates_company_profiles_last_fetched_at"), ["last_fetched_at"], unique=False)

    op.create_table(
        "opencorporates_financial_years",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nipt", sa.String(length=64), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("revenue_raw", sa.Text(), nullable=True),
        sa.Column("revenue_amount", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("profit_before_tax_raw", sa.Text(), nullable=True),
        sa.Column("profit_before_tax_amount", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False, server_default="opencorporates_html"),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opencorporates_financial_years")),
        sa.UniqueConstraint(
            "nipt",
            "year",
            "source_type",
            name="uq_opencorporates_financial_year_nipt_year_source",
        ),
    )
    with op.batch_alter_table("opencorporates_financial_years", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_opencorporates_financial_years_nipt"), ["nipt"], unique=False)
        batch_op.create_index(batch_op.f("ix_opencorporates_financial_years_year"), ["year"], unique=False)
        batch_op.create_index(batch_op.f("ix_opencorporates_financial_years_fetched_at"), ["fetched_at"], unique=False)


def downgrade() -> None:
    op.drop_table("opencorporates_financial_years")
    op.drop_table("opencorporates_company_profiles")
