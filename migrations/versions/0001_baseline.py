"""Baseline the original single-user schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", name="uq_watchlist_items_symbol"),
    )
    op.create_index("ix_watchlist_items_id", "watchlist_items", ["id"])
    op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"])
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_timestamp", sa.DateTime(timezone=True)),
        sa.Column("overall_judgment", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_reasons", sa.JSON(), nullable=False),
        sa.Column("risk_factors", sa.JSON(), nullable=False),
        sa.Column("support_levels", sa.JSON(), nullable=False),
        sa.Column("should_alert", sa.Boolean(), nullable=False),
        sa.Column("triggered_alerts", sa.JSON(), nullable=False),
        sa.Column("alert_reason", sa.Text()),
        sa.Column("alert_sent_at", sa.DateTime(timezone=True)),
        sa.Column("raw_result", sa.JSON()),
    )
    op.create_index("ix_analysis_results_id", "analysis_results", ["id"])
    op.create_index("ix_analysis_results_symbol", "analysis_results", ["symbol"])
    op.create_index("ix_analysis_results_analyzed_at", "analysis_results", ["analyzed_at"])
    op.create_table(
        "custom_alert_conditions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("user_rule", sa.Text(), nullable=False),
        sa.Column("normalized_rule", sa.Text()),
        sa.Column("validation_summary", sa.Text(), nullable=False),
        sa.Column("required_tools", sa.JSON(), nullable=False),
        sa.Column("related_symbols", sa.JSON(), nullable=False),
        sa.Column("news_symbols", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("symbol", "user_rule", name="uq_custom_alert_conditions_symbol_rule"),
    )
    op.create_index("ix_custom_alert_conditions_id", "custom_alert_conditions", ["id"])
    op.create_index("ix_custom_alert_conditions_symbol", "custom_alert_conditions", ["symbol"])


def downgrade() -> None:
    op.drop_table("custom_alert_conditions")
    op.drop_table("analysis_results")
    op.drop_table("watchlist_items")

