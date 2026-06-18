"""add app risk features

Revision ID: c91d7a0e5b3f
Revises: b7e2a5f4c901
Create Date: 2026-06-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c91d7a0e5b3f"
down_revision: Union[str, None] = "b7e2a5f4c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("app_company_features", schema=None) as batch_op:
        batch_op.add_column(sa.Column("near_budget_limit_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("near_budget_limit_rate", sa.Numeric(10, 4), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("winner_value_gt_budget_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("winner_value_gt_budget_rate", sa.Numeric(10, 4), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("top_authority_name", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("top_authority_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("top_authority_share", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("authority_hhi", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("top_procedure_type", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("top_procedure_type_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("top_procedure_type_share", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("procedure_type_hhi", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("yoy_value_jump_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("yoy_contract_count_jump_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("max_yoy_value_growth_ratio", sa.Numeric(18, 6), nullable=True))
        batch_op.add_column(sa.Column("max_yoy_contract_count_growth_ratio", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("app_company_features", schema=None) as batch_op:
        batch_op.drop_column("max_yoy_contract_count_growth_ratio")
        batch_op.drop_column("max_yoy_value_growth_ratio")
        batch_op.drop_column("yoy_contract_count_jump_count")
        batch_op.drop_column("yoy_value_jump_count")
        batch_op.drop_column("procedure_type_hhi")
        batch_op.drop_column("top_procedure_type_share")
        batch_op.drop_column("top_procedure_type_count")
        batch_op.drop_column("top_procedure_type")
        batch_op.drop_column("authority_hhi")
        batch_op.drop_column("top_authority_share")
        batch_op.drop_column("top_authority_count")
        batch_op.drop_column("top_authority_name")
        batch_op.drop_column("winner_value_gt_budget_rate")
        batch_op.drop_column("winner_value_gt_budget_count")
        batch_op.drop_column("near_budget_limit_rate")
        batch_op.drop_column("near_budget_limit_count")
