"""per-section record vectors replace the single embedding column

Revision ID: c9f4a2d7e815
Revises: b8d2e5f1c3a7
Create Date: 2026-10-12 18:00:00.000000

Existing embeddings are copied in as the "summary" section with an empty
text_hash. The app's startup backfill sees the hash mismatch and re-embeds
them, adding the new sections; similar cases keep working meanwhile.
The keyword search index (FTS5 table record_search) is derived data: the
app creates and fills it at startup, so it is not part of this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9f4a2d7e815'
down_revision: Union[str, None] = 'b8d2e5f1c3a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'record_vectors',
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('section', sa.String(length=20), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('text_hash', sa.String(length=64), nullable=False),
        sa.Column('vector', sa.LargeBinary(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['record_id'], ['discharge_records.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('record_id', 'section'),
    )
    op.execute(
        "INSERT INTO record_vectors (record_id, section, model, text_hash, vector, updated_at) "
        "SELECT id, 'summary', embedding_model, '', embedding, CURRENT_TIMESTAMP "
        "FROM discharge_records WHERE embedding IS NOT NULL AND embedding_model IS NOT NULL"
    )
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.drop_column('embedding_model')
        batch_op.drop_column('embedding')


def downgrade() -> None:
    with op.batch_alter_table('discharge_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('embedding', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('embedding_model', sa.String(length=100), nullable=True))
    op.execute(
        "UPDATE discharge_records SET "
        "embedding = (SELECT vector FROM record_vectors v "
        "             WHERE v.record_id = discharge_records.id AND v.section = 'summary'), "
        "embedding_model = (SELECT model FROM record_vectors v "
        "                   WHERE v.record_id = discharge_records.id AND v.section = 'summary')"
    )
    op.drop_table('record_vectors')
    # Derived keyword index; the newer app version recreates it on startup.
    for table in ('record_search',):
        op.execute(f"DROP TABLE IF EXISTS {table}")
