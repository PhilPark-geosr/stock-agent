"""Add service user accounts."""

from alembic import op
import sqlalchemy as sa

revision = "0002_user_accounts"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("login_provider", sa.String(32), nullable=False),
        sa.Column("provider_subject_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("login_provider", "provider_subject_id", name="uq_user_accounts_login_identity"),
    )


def downgrade() -> None:
    op.drop_table("user_accounts")
