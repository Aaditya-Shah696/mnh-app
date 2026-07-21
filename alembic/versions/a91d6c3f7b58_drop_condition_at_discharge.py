"""drop condition_at_discharge

Revision ID: a91d6c3f7b58
Revises: f2c9a4d81e37
Create Date: 2026-07-19 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a91d6c3f7b58'
down_revision: Union[str, None] = 'f2c9a4d81e37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_column('condition_at_discharge')


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('condition_at_discharge', sa.Text(), nullable=True))
