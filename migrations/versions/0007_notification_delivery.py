"""Add per-user notification connections and delivery history."""

from alembic import op
import sqlalchemy as sa

revision = "0007_notification_delivery"
down_revision = "0006_shared_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_notification_connections_owner_id",
        "notification_connections",
        ["owner_id"],
    )
    op.create_index(
        "uq_notification_connections_active_owner_channel",
        "notification_connections",
        ["owner_id", "channel"],
        unique=True,
        sqlite_where=sa.text("disconnected_at IS NULL"),
        postgresql_where=sa.text("disconnected_at IS NULL"),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recipient_id",
            sa.String(36),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analysis_results.id"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("notification_connections.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.Text()),
        sa.UniqueConstraint(
            "recipient_id",
            "analysis_id",
            "kind",
            name="uq_notification_delivery_recipient_analysis_kind",
        ),
    )
    op.create_index(
        "ix_notification_deliveries_recipient_id",
        "notification_deliveries",
        ["recipient_id"],
    )
    op.create_index(
        "ix_notification_deliveries_analysis_id",
        "notification_deliveries",
        ["analysis_id"],
    )
    with op.batch_alter_table("analysis_results") as batch:
        batch.drop_column("alert_sent_at")


def downgrade() -> None:
    with op.batch_alter_table("analysis_results") as batch:
        batch.add_column(
            sa.Column("alert_sent_at", sa.DateTime(timezone=True))
        )
    op.drop_table("notification_deliveries")
    op.drop_table("notification_connections")
