"""initial migration

Revision ID: d269eff430cc
Revises: 
Create Date: 2025-08-08 12:52:22.735399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd269eff430cc'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the initial `job` table based on app.models.Job
    op.create_table(
        'job',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('progress', sa.Integer(), nullable=True),
        sa.Column('step', sa.String(length=50), nullable=True),
        sa.Column('error', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('input', sa.JSON(), nullable=True),
        sa.Column('result', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('job')
