"""Merge catalog and main beta/briefing histories without rewriting applied revisions."""

revision = "0012_merge_catalog_beta"
down_revision = ("0011_security_catalog", "0011_merge_beta_briefing")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
