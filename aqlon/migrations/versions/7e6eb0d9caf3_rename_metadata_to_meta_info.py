"""rename_metadata_to_meta_info

Revision ID: 7e6eb0d9caf3
Revises: dfd71c6ea5f7
Create Date: 2025-06-07 19:35:15.988559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e6eb0d9caf3'
down_revision: Union[str, None] = 'dfd71c6ea5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename metadata column to meta_info in goal_history table
    op.alter_column('goal_history', 'metadata', new_column_name='meta_info', 
                    existing_type=sa.dialects.postgresql.JSONB,
                    nullable=True)


def downgrade() -> None:
    # Rename meta_info column back to metadata in goal_history table
    op.alter_column('goal_history', 'meta_info', new_column_name='metadata',
                    existing_type=sa.dialects.postgresql.JSONB,
                    nullable=True)
