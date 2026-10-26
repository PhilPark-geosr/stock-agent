"""Retain verified delisting evidence and bounded provider diagnostics."""
from alembic import op
import sqlalchemy as sa

revision = "0013_catalog_operations"
down_revision = "0012_merge_catalog_beta"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("catalog_attempts", sa.Column("details", sa.JSON(), nullable=True))
    op.create_table("catalog_delisting_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("security_id", sa.String(36), sa.ForeignKey("securities.id"), nullable=False),
        sa.Column("effective_on", sa.Date(), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("reviewed_by", sa.String(120), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.String(1000)))
    op.create_index("ix_catalog_delisting_evidence_security_id", "catalog_delisting_evidence", ["security_id"])


def downgrade():
    op.drop_table("catalog_delisting_evidence")
    with op.batch_alter_table("catalog_attempts") as batch:
        batch.drop_column("details")
