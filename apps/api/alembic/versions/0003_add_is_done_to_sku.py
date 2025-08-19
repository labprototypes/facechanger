"""add is_done to sku

Revision ID: 0003_add_is_done_to_sku
Revises: 0002_add_brand_to_sku
Create Date: 2025-08-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_is_done_to_sku'
down_revision = '0002_add_brand_to_sku'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add column with default False; set server_default then drop it for cleanliness
    op.add_column('skus', sa.Column('is_done', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Optional: remove server_default to avoid locking in a default at DB level
    with op.batch_alter_table('skus') as batch_op:
        batch_op.alter_column('is_done', server_default=None)


def downgrade() -> None:
    op.drop_column('skus', 'is_done')
