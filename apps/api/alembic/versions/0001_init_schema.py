"""init schema

Revision ID: 0001_init_schema
Revises: 
Create Date: 2025-08-19 00:00:00.000000
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_init_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('head_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=120), nullable=False, unique=True),
        sa.Column('replicate_model', sa.String(length=255), nullable=False),
        sa.Column('trigger_token', sa.String(length=64), nullable=False),
        sa.Column('prompt_template', sa.String(length=512), nullable=False),
        sa.Column('params', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_head_profiles_name', 'head_profiles', ['name'])

    op.create_table('batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_batches_date', 'batches', ['date'])

    op.create_table('skus',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(length=120), nullable=False),
        sa.Column('batch_id', sa.Integer(), sa.ForeignKey('batches.id'), nullable=True),
        sa.Column('head_profile_id', sa.Integer(), sa.ForeignKey('head_profiles.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_skus_code', 'skus', ['code'])

    op.create_table('frames',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sku_id', sa.Integer(), sa.ForeignKey('skus.id'), nullable=False),
        sa.Column('original_key', sa.String(length=512), nullable=False),
        sa.Column('mask_key', sa.String(length=512), nullable=True),
        sa.Column('status', sa.Enum('NEW','MASKED','QUEUED','RUNNING','DONE','FAILED', name='framestatus'), server_default='NEW'),
        sa.Column('pending_params', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_frames_sku_id', 'frames', ['sku_id'])

    op.create_table('generations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('frame_id', sa.Integer(), sa.ForeignKey('frames.id'), nullable=False),
        sa.Column('status', sa.Enum('PENDING','RUNNING','COMPLETED','FAILED', name='genstatus'), server_default='PENDING'),
        sa.Column('replicate_prediction_id', sa.String(length=128), nullable=True),
        sa.Column('output_keys', sa.JSON(), nullable=True),
        sa.Column('error', sa.String(length=2048), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_generations_frame_id', 'generations', ['frame_id'])

    op.create_table('frame_output_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('frame_id', sa.Integer(), sa.ForeignKey('frames.id'), nullable=False),
        sa.Column('version_index', sa.Integer(), nullable=False),
        sa.Column('keys', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_frame_output_versions_frame_id', 'frame_output_versions', ['frame_id'])
    op.create_unique_constraint('uq_frame_version', 'frame_output_versions', ['frame_id','version_index'])

    op.create_table('frame_favorites',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('frame_id', sa.Integer(), sa.ForeignKey('frames.id'), nullable=False),
        sa.Column('key', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
    )
    op.create_index('ix_frame_favorites_frame_id', 'frame_favorites', ['frame_id'])
    op.create_unique_constraint('uq_frame_fav_key', 'frame_favorites', ['frame_id','key'])


def downgrade() -> None:
    op.drop_constraint('uq_frame_fav_key', 'frame_favorites', type_='unique')
    op.drop_table('frame_favorites')
    op.drop_constraint('uq_frame_version', 'frame_output_versions', type_='unique')
    op.drop_table('frame_output_versions')
    op.drop_index('ix_generations_frame_id', table_name='generations')
    op.drop_table('generations')
    op.drop_index('ix_frames_sku_id', table_name='frames')
    op.drop_table('frames')
    op.drop_index('ix_skus_code', table_name='skus')
    op.drop_table('skus')
    op.drop_index('ix_batches_date', table_name='batches')
    op.drop_table('batches')
    op.drop_index('ix_head_profiles_name', table_name='head_profiles')
    op.drop_table('head_profiles')
