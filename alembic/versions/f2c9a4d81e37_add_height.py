"""add height next to weight

Revision ID: f2c9a4d81e37
Revises: e7a3f2b91c04
Create Date: 2026-07-19 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2c9a4d81e37'
down_revision: Union[str, None] = 'e7a3f2b91c04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('height', sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_column('height')
