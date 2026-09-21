"""Continuous briefing inputs, prompt versions, preferences and delivery history."""
from alembic import op
import sqlalchemy as sa

revision = "0009_continuous_briefing"
down_revision = "0008_user_alert_evaluation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("briefing_preferences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("n", sa.Integer(), nullable=True),
        sa.Column("pre_market_enabled", sa.Boolean(), nullable=False),
        sa.Column("post_market_enabled", sa.Boolean(), nullable=False),
        sa.Column("kakao_enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("owner_id", "market"))
    op.create_table("briefing_prompt_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("briefing_prompt_activations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(64), sa.ForeignKey("briefing_prompt_versions.id"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("briefing_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("request_key", sa.String(180), nullable=False),
        sa.Column("request_data", sa.JSON(), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("trade_date", sa.String(10), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("prompt_id", sa.String(64), sa.ForeignKey("briefing_prompt_versions.id"), nullable=False),
        sa.Column("previous_id", sa.String(36), sa.ForeignKey("briefing_runs.id"), nullable=True),
        sa.Column("original_id", sa.String(36), sa.ForeignKey("briefing_runs.id"), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("owner_id", "request_key"))
    op.create_table("briefing_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("briefing_runs.id"), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("notification_connections.id"), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("attempts", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("claim_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "channel"))
    for table, columns in {
        "briefing_preferences": ["owner_id"], "briefing_runs": ["owner_id", "trade_date"],
        "briefing_deliveries": ["owner_id", "run_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ("briefing_deliveries", "briefing_runs", "briefing_prompt_activations",
                  "briefing_prompt_versions", "briefing_preferences"):
        op.drop_table(table)
