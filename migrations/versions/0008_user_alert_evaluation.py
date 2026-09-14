"""Add per-condition user alert evaluations and evaluation-backed deliveries."""

from alembic import op
import sqlalchemy as sa


revision = "0008_user_alert_evaluation"
down_revision = "0007_notification_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("analysis_id", sa.Integer(), sa.ForeignKey("analysis_results.id"), nullable=False),
        sa.Column("condition_id", sa.Integer(), sa.ForeignKey("custom_alert_conditions.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("matched", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notification_message", sa.Text(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "analysis_id", "condition_id", name="uq_alert_evaluation_analysis_condition"
        ),
    )
    op.create_index("ix_alert_evaluations_analysis_id", "alert_evaluations", ["analysis_id"])
    op.create_index("ix_alert_evaluations_condition_id", "alert_evaluations", ["condition_id"])

    with op.batch_alter_table("notification_deliveries") as batch:
        batch.drop_constraint(
            "uq_notification_delivery_recipient_analysis_kind", type_="unique"
        )
        batch.add_column(sa.Column("evaluation_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_notification_deliveries_evaluation_id",
            "alert_evaluations",
            ["evaluation_id"],
            ["id"],
        )
    op.create_index(
        "ix_notification_deliveries_evaluation_id",
        "notification_deliveries",
        ["evaluation_id"],
    )
    op.create_index(
        "uq_notification_delivery_default_alert",
        "notification_deliveries",
        ["recipient_id", "analysis_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'default_alert'"),
        postgresql_where=sa.text("kind = 'default_alert'"),
    )
    op.create_index(
        "uq_notification_delivery_user_alert",
        "notification_deliveries",
        ["evaluation_id", "connection_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'user_alert'"),
        postgresql_where=sa.text("kind = 'user_alert'"),
    )


def downgrade() -> None:
    op.drop_index("uq_notification_delivery_user_alert", table_name="notification_deliveries")
    op.drop_index("uq_notification_delivery_default_alert", table_name="notification_deliveries")
    op.drop_index("ix_notification_deliveries_evaluation_id", table_name="notification_deliveries")
    with op.batch_alter_table("notification_deliveries") as batch:
        batch.drop_constraint("fk_notification_deliveries_evaluation_id", type_="foreignkey")
        batch.drop_column("evaluation_id")
        batch.create_unique_constraint(
            "uq_notification_delivery_recipient_analysis_kind",
            ["recipient_id", "analysis_id", "kind"],
        )
    op.drop_table("alert_evaluations")
