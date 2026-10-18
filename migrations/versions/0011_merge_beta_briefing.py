"""Merge private beta access and continuous briefing migration histories."""

revision = "0011_merge_beta_briefing"
down_revision = ("0010_beta_access_grants", "0010_briefing_targets")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
