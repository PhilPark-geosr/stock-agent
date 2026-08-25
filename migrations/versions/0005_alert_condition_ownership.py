"""Scope user alert conditions to watchlist subscriptions."""

from alembic import op
import sqlalchemy as sa

revision = "0005_alert_condition_ownership"
down_revision = "0004_watchlist_subscriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    constraint_names = {
        item["name"] for item in inspector.get_unique_constraints("custom_alert_conditions")
    }
    index_names = {item["name"] for item in inspector.get_indexes("custom_alert_conditions")}
    with op.batch_alter_table("custom_alert_conditions") as batch:
        if "uq_custom_alert_conditions_symbol_rule" in constraint_names:
            batch.drop_constraint("uq_custom_alert_conditions_symbol_rule", type_="unique")
        elif "uq_custom_alert_conditions_symbol_rule" in index_names:
            batch.drop_index("uq_custom_alert_conditions_symbol_rule")
        batch.add_column(sa.Column("watchlist_subscription_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_custom_alert_conditions_subscription",
            "watchlist_items",
            ["watchlist_subscription_id"],
            ["id"],
        )
        batch.create_index(
            "ix_custom_alert_conditions_watchlist_subscription_id",
            ["watchlist_subscription_id"],
        )
    op.create_index(
        "uq_custom_alert_conditions_active_subscription_rule",
        "custom_alert_conditions",
        ["watchlist_subscription_id", "user_rule"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL AND watchlist_subscription_id IS NOT NULL"),
        postgresql_where=sa.text("ended_at IS NULL AND watchlist_subscription_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_custom_alert_conditions_active_subscription_rule",
        table_name="custom_alert_conditions",
    )
    with op.batch_alter_table("custom_alert_conditions") as batch:
        batch.drop_index("ix_custom_alert_conditions_watchlist_subscription_id")
        batch.drop_constraint("fk_custom_alert_conditions_subscription", type_="foreignkey")
        batch.drop_column("ended_at")
        batch.drop_column("watchlist_subscription_id")
        batch.create_unique_constraint(
            "uq_custom_alert_conditions_symbol_rule", ["symbol", "user_rule"]
        )
