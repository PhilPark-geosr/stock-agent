"""Mark analyses safe for sharing between active subscribers."""

from alembic import op
import sqlalchemy as sa

revision = "0006_shared_analysis"
down_revision = "0005_alert_condition_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_results") as batch:
        batch.add_column(
            sa.Column("shared_safe", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("analysis_results") as batch:
        batch.drop_column("shared_safe")
