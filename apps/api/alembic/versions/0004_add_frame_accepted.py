"""add accepted to frames

Revision ID: 0004_add_frame_accepted
Revises: 0003_add_is_done_to_sku
Create Date: 2025-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_add_frame_accepted'
down_revision = '0003_add_is_done_to_sku'
branch_labels = None
depends_on = None

def upgrade() -> None:
    try:
        op.add_column('frames', sa.Column('accepted', sa.Boolean(), server_default=sa.false(), nullable=False))
    except Exception:
        pass

def downgrade() -> None:
    try:
        op.drop_column('frames', 'accepted')
    except Exception:
        pass
