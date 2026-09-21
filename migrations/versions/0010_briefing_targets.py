"""Remember each user's selected briefing targets without changing existing runs."""
from alembic import op
import sqlalchemy as sa

revision = "0010_briefing_targets"
down_revision = "0009_continuous_briefing"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("briefing_preferences", sa.Column("symbols", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("briefing_preferences", "symbols")
