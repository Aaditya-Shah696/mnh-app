"""ICD-10-CM diagnosis codes on discharge records

Revision ID: e3b7c1d9a402
Revises: c9f4a2d7e815
Create Date: 2026-10-13 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3b7c1d9a402'
down_revision: Union[str, None] = 'c9f4a2d7e815'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('diagnosis_codes', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_column('diagnosis_codes')
