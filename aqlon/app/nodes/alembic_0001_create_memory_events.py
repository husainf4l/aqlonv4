"""
Revision ID: 0001_create_memory_events
Revises: 
Create Date: 2025-06-07 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy.dialects.postgresql as pg

def upgrade():
    op.create_table(
        'memory_events',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('timestamp', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('goal_id', pg.UUID(as_uuid=True), nullable=True),
        sa.Column('step_id', pg.UUID(as_uuid=True), nullable=True),
        sa.Column('agent_action', sa.Text, nullable=False),
        sa.Column('vision_state', sa.Text, nullable=True),
        sa.Column('terminal_output', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('meta', pg.JSONB, nullable=True),
    )

def downgrade():
    op.drop_table('memory_events')
