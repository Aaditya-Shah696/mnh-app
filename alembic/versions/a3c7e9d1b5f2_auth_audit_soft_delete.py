"""users, sessions, audit_log, soft delete, record authorship

Revision ID: a3c7e9d1b5f2
Revises: f7c3b8e1a9d2
Create Date: 2026-09-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import AUDIT_LOG_TRIGGERS


revision: str = 'a3c7e9d1b5f2'
down_revision: Union[str, None] = 'f7c3b8e1a9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('failed_logins', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(), nullable=True),
        sa.Column('password_changed_at', sa.DateTime(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=300), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sessions_token_hash', 'sessions', ['token_hash'], unique=True)
    op.create_index('ix_sessions_user_id', 'sessions', ['user_id'], unique=False)

    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ts', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('username', sa.String(length=50), nullable=True),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('entity_type', sa.String(length=20), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('ip', sa.String(length=45), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_log_ts', 'audit_log', ['ts'], unique=False)
    op.create_index('ix_audit_log_user_id', 'audit_log', ['user_id'], unique=False)
    op.create_index('ix_audit_log_username', 'audit_log', ['username'], unique=False)
    op.create_index('ix_audit_log_action', 'audit_log', ['action'], unique=False)
    for ddl in AUDIT_LOG_TRIGGERS:
        op.execute(ddl)

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_patients_deleted_at', ['deleted_at'], unique=False)

    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('updated_by', sa.Integer(), nullable=True))
        batch_op.create_index('ix_discharge_records_deleted_at', ['deleted_at'], unique=False)
        batch_op.create_foreign_key(
            'fk_discharge_records_created_by_users', 'users',
            ['created_by'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_discharge_records_updated_by_users', 'users',
            ['updated_by'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_constraint('fk_discharge_records_updated_by_users', type_='foreignkey')
        batch_op.drop_constraint('fk_discharge_records_created_by_users', type_='foreignkey')
        batch_op.drop_index('ix_discharge_records_deleted_at')
        batch_op.drop_column('updated_by')
        batch_op.drop_column('created_by')
        batch_op.drop_column('deleted_at')

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_index('ix_patients_deleted_at')
        batch_op.drop_column('deleted_at')

    op.execute('DROP TRIGGER IF EXISTS audit_log_no_delete')
    op.execute('DROP TRIGGER IF EXISTS audit_log_no_update')
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_index('ix_audit_log_username', table_name='audit_log')
    op.drop_index('ix_audit_log_user_id', table_name='audit_log')
    op.drop_index('ix_audit_log_ts', table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index('ix_sessions_user_id', table_name='sessions')
    op.drop_index('ix_sessions_token_hash', table_name='sessions')
    op.drop_table('sessions')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_table('users')
