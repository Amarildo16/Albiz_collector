"""add qkb search run tracking

Revision ID: 9f2e4a8c1b6d
Revises: aaef71721e11
Create Date: 2026-04-23 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f2e4a8c1b6d"
down_revision: Union[str, None] = "aaef71721e11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "qkb_search_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collector_name", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("current_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qkb_search_runs")),
    )
    op.create_index(op.f("ix_qkb_search_runs_collector_name"), "qkb_search_runs", ["collector_name"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_mode"), "qkb_search_runs", ["mode"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_date_from"), "qkb_search_runs", ["date_from"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_date_to"), "qkb_search_runs", ["date_to"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_current_date"), "qkb_search_runs", ["current_date"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_status"), "qkb_search_runs", ["status"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_started_at"), "qkb_search_runs", ["started_at"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_updated_at"), "qkb_search_runs", ["updated_at"], unique=False)
    op.create_index(op.f("ix_qkb_search_runs_completed_at"), "qkb_search_runs", ["completed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_qkb_search_runs_completed_at"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_updated_at"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_started_at"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_status"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_current_date"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_date_to"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_date_from"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_mode"), table_name="qkb_search_runs")
    op.drop_index(op.f("ix_qkb_search_runs_collector_name"), table_name="qkb_search_runs")
    op.drop_table("qkb_search_runs")
