"""Persist private beta invitations without plaintext codes."""
from alembic import op
import sqlalchemy as sa

revision = '0009_invitations'
down_revision = '0008_user_alert_evaluation'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'invitations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('code_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('invitations')
