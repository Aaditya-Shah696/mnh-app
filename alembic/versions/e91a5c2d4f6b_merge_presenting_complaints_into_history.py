"""merge presenting_complaints into history

Revision ID: e91a5c2d4f6b
Revises: d4b6f0a3c928
Create Date: 2026-07-21 00:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e91a5c2d4f6b'
down_revision: Union[str, None] = 'd4b6f0a3c928'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE discharge_records SET history = "
        "CASE "
        "WHEN presenting_complaints IS NOT NULL AND TRIM(presenting_complaints) != '' "
        "  AND history IS NOT NULL AND TRIM(history) != '' "
        "  THEN presenting_complaints || char(10) || char(10) || history "
        "WHEN presenting_complaints IS NOT NULL AND TRIM(presenting_complaints) != '' "
        "  THEN presenting_complaints "
        "ELSE history END"
    ))
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_column('presenting_complaints')


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('presenting_complaints', sa.Text(), nullable=True))
