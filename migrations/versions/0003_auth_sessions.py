"""Add login attempts and service sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0003_auth_sessions"
down_revision = "0002_user_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("auth_login_attempts",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("state_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("verifier_challenge", sa.String(128), nullable=False), sa.Column("user_account_id", sa.String(36)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("consumed_at", sa.DateTime(timezone=True)))
    op.create_table("auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_account_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)))
    op.create_index("ix_auth_sessions_user_account_id", "auth_sessions", ["user_account_id"])


def downgrade() -> None:
    op.drop_table("auth_sessions"); op.drop_table("auth_login_attempts")
