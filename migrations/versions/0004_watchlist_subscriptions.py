"""Scope watchlist subscriptions to user accounts."""

from alembic import op
import sqlalchemy as sa

revision = "0004_watchlist_subscriptions"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    constraint_names = {
        item["name"] for item in inspector.get_unique_constraints("watchlist_items")
    }
    index_names = {item["name"] for item in inspector.get_indexes("watchlist_items")}
    with op.batch_alter_table("watchlist_items") as batch:
        if "uq_watchlist_items_symbol" in constraint_names:
            batch.drop_constraint("uq_watchlist_items_symbol", type_="unique")
        elif "uq_watchlist_items_symbol" in index_names:
            batch.drop_index("uq_watchlist_items_symbol")
        batch.add_column(sa.Column("user_account_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_watchlist_items_user_account_id", "user_accounts", ["user_account_id"], ["id"]
        )
        batch.create_index("ix_watchlist_items_user_account_id", ["user_account_id"])
    op.create_index(
        "uq_watchlist_items_active_owner_symbol",
        "watchlist_items",
        ["user_account_id", "symbol"],
        unique=True,
        sqlite_where=sa.text("ended_at IS NULL AND user_account_id IS NOT NULL"),
        postgresql_where=sa.text("ended_at IS NULL AND user_account_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_watchlist_items_active_owner_symbol", table_name="watchlist_items")
    with op.batch_alter_table("watchlist_items") as batch:
        batch.drop_index("ix_watchlist_items_user_account_id")
        batch.drop_constraint("fk_watchlist_items_user_account_id", type_="foreignkey")
        batch.drop_column("ended_at")
        batch.drop_column("user_account_id")
        batch.create_unique_constraint("uq_watchlist_items_symbol", ["symbol"])
