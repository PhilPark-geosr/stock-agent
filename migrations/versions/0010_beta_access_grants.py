"""Persist private beta access separately from operator authorization."""
from alembic import op
import sqlalchemy as sa

revision = "0010_beta_access_grants"
down_revision = "0009_invitations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_beta_access_grants",
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("user_accounts.id"),
            primary_key=True,
        ),
        sa.Column(
            "invitation_id",
            sa.String(36),
            sa.ForeignKey("invitations.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_beta_access_grants")
