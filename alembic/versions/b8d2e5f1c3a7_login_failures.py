"""per-address login failures

Revision ID: b8d2e5f1c3a7
Revises: a3c7e9d1b5f2
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d2e5f1c3a7'
down_revision: Union[str, None] = 'a3c7e9d1b5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'login_failures',
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=False),
        sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('username', 'ip'),
    )
    op.create_index(
        'ix_login_failures_last_failure_at', 'login_failures', ['last_failure_at'], unique=False,
    )
    op.execute("UPDATE users SET failed_logins = 0, locked_until = NULL")


def downgrade() -> None:
    op.drop_index('ix_login_failures_last_failure_at', table_name='login_failures')
    op.drop_table('login_failures')
