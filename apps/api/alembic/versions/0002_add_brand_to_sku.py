"""add brand column to skus

Revision ID: 0002_add_brand_to_sku
Revises: 0001_init_schema
Create Date: 2025-08-19
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_brand_to_sku'
down_revision = '0001_init_schema'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('skus', sa.Column('brand', sa.String(length=120), nullable=True))
    op.create_index('ix_skus_brand', 'skus', ['brand'])


def downgrade() -> None:
    op.drop_index('ix_skus_brand', table_name='skus')
    op.drop_column('skus', 'brand')
