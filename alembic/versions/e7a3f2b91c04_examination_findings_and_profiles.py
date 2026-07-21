"""examination findings, patient profiles, drop phone/allergies, ward rename

Revision ID: e7a3f2b91c04
Revises: c54c56216b70
Create Date: 2026-07-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a3f2b91c04'
down_revision: Union[str, None] = 'c54c56216b70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SIGN_COLUMNS = (
    'pallor', 'icterus', 'rash', 'cyanosis', 'meningeal_signs', 'dehydration_signs',
)
SYSTEM_COLUMNS = (
    'throat_findings', 'respiratory_system', 'cvs_system', 'abdominal_exam', 'cns_system',
)


def upgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_patients_phone'))
        batch_op.drop_column('phone')
        batch_op.add_column(sa.Column('chronic_conditions', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('past_history', sa.Text(), nullable=True))

    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_column('allergies')
        batch_op.alter_column(
            'ward_bed', new_column_name='ward', existing_type=sa.String(length=50),
            existing_nullable=True,
        )
        for name in SIGN_COLUMNS:
            batch_op.add_column(sa.Column(name, sa.String(length=3), nullable=True))
        for name in SYSTEM_COLUMNS:
            batch_op.add_column(sa.Column(name, sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        for name in reversed(SYSTEM_COLUMNS):
            batch_op.drop_column(name)
        for name in reversed(SIGN_COLUMNS):
            batch_op.drop_column(name)
        batch_op.alter_column(
            'ward', new_column_name='ward_bed', existing_type=sa.String(length=50),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column('allergies', sa.String(length=300), nullable=True))

    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_column('past_history')
        batch_op.drop_column('chronic_conditions')
        batch_op.add_column(sa.Column('phone', sa.String(length=30), nullable=True))
        batch_op.create_index(batch_op.f('ix_patients_phone'), ['phone'], unique=False)
