"""drop attachments table

Revision ID: f7c3b8e1a9d2
Revises: e91a5c2d4f6b
Create Date: 2026-07-21 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f7c3b8e1a9d2'
down_revision: Union[str, None] = 'e91a5c2d4f6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('attachments')


def downgrade() -> None:
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('record_id', sa.Integer(),
                  sa.ForeignKey('discharge_records.id', ondelete='CASCADE'), index=True),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('stored_name', sa.String(255), nullable=False, unique=True),
        sa.Column('content_type', sa.String(120), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
    )
