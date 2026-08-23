"""Add authenticated-account investment briefings."""

from alembic import op
import sqlalchemy as sa

revision = "0007_investment_briefings"
down_revision = "0006_shared_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_results") as batch:
        batch.add_column(
            sa.Column(
                "normalized_judgment",
                sa.String(24),
                nullable=False,
                server_default="UNKNOWN",
            )
        )
        batch.add_column(sa.Column("briefing_type", sa.String(24), nullable=True))
        batch.add_column(sa.Column("trading_date", sa.Date(), nullable=True))
        batch.create_index("ix_analysis_results_normalized_judgment", ["normalized_judgment"])
        batch.create_index("ix_analysis_results_briefing_type", ["briefing_type"])
        batch.create_index("ix_analysis_results_trading_date", ["trading_date"])

    op.create_table(
        "investment_briefings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_account_id",
            sa.String(36),
            sa.ForeignKey("user_accounts.id"),
            nullable=False,
        ),
        sa.Column("briefing_type", sa.String(24), nullable=False),
        sa.Column("exchange", sa.String(24), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("resolved_symbols", sa.JSON(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "user_account_id",
            "exchange",
            "briefing_type",
            "trading_date",
            name="uq_investment_briefing_run",
        ),
    )
    op.create_index("ix_investment_briefings_user_account_id", "investment_briefings", ["user_account_id"])

    op.create_table(
        "briefing_scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("briefing_id", sa.Integer(), sa.ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(24), nullable=False),
        sa.Column("source_value", sa.String(120), nullable=True),
        sa.Column("resolved_symbols", sa.JSON(), nullable=False),
        sa.UniqueConstraint("briefing_id", "source_type", name="uq_briefing_scope_source"),
    )
    op.create_table(
        "briefing_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("briefing_id", sa.Integer(), sa.ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("current_analysis_id", sa.Integer(), sa.ForeignKey("analysis_results.id"), nullable=False),
        sa.Column("previous_analysis_id", sa.Integer(), sa.ForeignKey("analysis_results.id"), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("current_judgment", sa.String(24), nullable=False),
        sa.Column("previous_judgment", sa.String(24), nullable=True),
        sa.Column("judgment_changed", sa.Boolean(), nullable=False),
        sa.Column("comparison_status", sa.String(24), nullable=False),
        sa.Column("judgment_distance", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("data_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("briefing_id", "symbol", name="uq_briefing_item_symbol"),
    )
    op.create_table(
        "briefing_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("briefing_id", sa.Integer(), sa.ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("briefing_id", "channel", name="uq_briefing_delivery_channel"),
    )
    op.create_table(
        "briefing_failures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("briefing_id", sa.Integer(), sa.ForeignKey("investment_briefings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("briefing_id", "symbol", name="uq_briefing_failure_symbol"),
    )


def downgrade() -> None:
    op.drop_table("briefing_failures")
    op.drop_table("briefing_deliveries")
    op.drop_table("briefing_items")
    op.drop_table("briefing_scopes")
    op.drop_index("ix_investment_briefings_user_account_id", table_name="investment_briefings")
    op.drop_table("investment_briefings")
    with op.batch_alter_table("analysis_results") as batch:
        batch.drop_index("ix_analysis_results_trading_date")
        batch.drop_index("ix_analysis_results_briefing_type")
        batch.drop_index("ix_analysis_results_normalized_judgment")
        batch.drop_column("trading_date")
        batch.drop_column("briefing_type")
        batch.drop_column("normalized_judgment")
