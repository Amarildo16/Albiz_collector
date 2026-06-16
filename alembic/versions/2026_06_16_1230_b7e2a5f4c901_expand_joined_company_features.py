"""expand joined company features

Revision ID: b7e2a5f4c901
Revises: 4c03a1b8f2d4
Create Date: 2026-06-16 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7e2a5f4c901"
down_revision: Union[str, None] = "4c03a1b8f2d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("joined_company_features", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_row_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("registration_year", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("has_activity_text", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("has_ownership_text", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("first_procurement_year", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("last_procurement_year", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("active_year_span", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("active_procurement_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("cancelled_procurement_rate", sa.Numeric(10, 4), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("suspended_procurement_rate", sa.Numeric(10, 4), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("active_total_budget_limit_amount", sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("active_total_winner_value_amount", sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("cancelled_total_budget_limit_amount", sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("cancelled_total_winner_value_amount", sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("safe_winner_to_budget_ratio_avg", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("safe_winner_to_budget_ratio_min", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("safe_winner_to_budget_ratio_max", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("purchase_tickets_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("purchase_tickets_total_winner_value", sa.Numeric(18, 2), nullable=True))
        batch_op.add_column(sa.Column("zero_budget_with_winner_value_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("zero_budget_with_winner_value_rate", sa.Numeric(10, 4), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("distinct_contracting_authority_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("distinct_procedure_type_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("distinct_contract_type_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("has_small_value_procedures", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("has_open_local_procedures", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("rows_with_winner_value_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("rows_with_budget_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("rows_with_valid_ratio_count", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("joined_company_features", schema=None) as batch_op:
        batch_op.drop_column("rows_with_valid_ratio_count")
        batch_op.drop_column("rows_with_budget_count")
        batch_op.drop_column("rows_with_winner_value_count")
        batch_op.drop_column("has_open_local_procedures")
        batch_op.drop_column("has_small_value_procedures")
        batch_op.drop_column("distinct_contract_type_count")
        batch_op.drop_column("distinct_procedure_type_count")
        batch_op.drop_column("distinct_contracting_authority_count")
        batch_op.drop_column("zero_budget_with_winner_value_rate")
        batch_op.drop_column("zero_budget_with_winner_value_count")
        batch_op.drop_column("purchase_tickets_total_winner_value")
        batch_op.drop_column("purchase_tickets_count")
        batch_op.drop_column("safe_winner_to_budget_ratio_max")
        batch_op.drop_column("safe_winner_to_budget_ratio_min")
        batch_op.drop_column("safe_winner_to_budget_ratio_avg")
        batch_op.drop_column("cancelled_total_winner_value_amount")
        batch_op.drop_column("cancelled_total_budget_limit_amount")
        batch_op.drop_column("active_total_winner_value_amount")
        batch_op.drop_column("active_total_budget_limit_amount")
        batch_op.drop_column("suspended_procurement_rate")
        batch_op.drop_column("cancelled_procurement_rate")
        batch_op.drop_column("active_procurement_count")
        batch_op.drop_column("active_year_span")
        batch_op.drop_column("last_procurement_year")
        batch_op.drop_column("first_procurement_year")
        batch_op.drop_column("has_ownership_text")
        batch_op.drop_column("has_activity_text")
        batch_op.drop_column("registration_year")
        batch_op.drop_column("source_row_count")
