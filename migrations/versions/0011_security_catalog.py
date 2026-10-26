"""Catalog identity, publication state, and immutable briefing subject index."""
from uuid import NAMESPACE_URL, uuid5
from alembic import op
import sqlalchemy as sa

revision = "0011_security_catalog"
down_revision = "0010_briefing_targets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("securities",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("country", sa.String(2), nullable=False),
        sa.Column("source", sa.String(50), nullable=False), sa.Column("source_identity", sa.String(160), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False), sa.Column("name", sa.String(255), nullable=False),
        sa.Column("exchange", sa.String(30), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("listed_on", sa.Date(), nullable=False),
        sa.Column("delisted_on", sa.Date()), sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("country", "source", "source_identity", name="uq_security_source"))
    op.create_index("ix_securities_country", "securities", ["country"])
    op.create_index("ix_securities_symbol", "securities", ["symbol"])
    op.create_table("catalog_states",
        sa.Column("country", sa.String(2), primary_key=True), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50)), sa.Column("source_date", sa.Date()), sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("token", sa.String(36)), sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("next_at", sa.DateTime(timezone=True), nullable=False), sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(100)))
    op.create_table("catalog_revisions",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("country", sa.String(2), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False), sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False), sa.Column("evidence", sa.String(500), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False), sa.UniqueConstraint("country", "version", name="uq_catalog_revision"))
    op.create_table("catalog_attempts",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("country", sa.String(2), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("error", sa.String(100)), sa.Column("version", sa.Integer()))
    op.create_index("ix_catalog_attempts_country", "catalog_attempts", ["country"])
    with op.batch_alter_table("watchlist_items") as batch:
        batch.add_column(sa.Column("security_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("security_name", sa.String(255), nullable=True))
        batch.create_foreign_key("fk_watchlist_security", "securities", ["security_id"], ["id"])
    op.create_table("briefing_subjects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("briefing_runs.id"), nullable=False),
        sa.Column("security_id", sa.String(36), sa.ForeignKey("securities.id")),
        sa.Column("symbol", sa.String(24), nullable=False), sa.Column("name", sa.String(255), nullable=False),
        sa.UniqueConstraint("run_id", "symbol", name="uq_briefing_subject"))
    op.create_index("ix_briefing_subjects_run_id", "briefing_subjects", ["run_id"])
    op.create_index("ix_briefing_subjects_security_id", "briefing_subjects", ["security_id"])
    runs = sa.table("briefing_runs", sa.column("id", sa.String), sa.column("context", sa.JSON), sa.column("status", sa.String))
    subjects = sa.table("briefing_subjects", sa.column("id"), sa.column("run_id"), sa.column("symbol"), sa.column("name"))
    bind = op.get_bind()
    # Read target snapshots only. Body mentions/current watchlists are not evidence.
    for run in bind.execute(sa.select(runs).where(runs.c.status.in_(["completed", "partial"]))):
        for symbol in sorted(set((run.context or {}).get("symbols", []))):
            bind.execute(subjects.insert().values(id=str(uuid5(NAMESPACE_URL, f"briefing-subject:{run.id}:{symbol}")),
                run_id=run.id, symbol=symbol, name=symbol))


def downgrade():
    op.drop_table("briefing_subjects")
    with op.batch_alter_table("watchlist_items") as batch:
        batch.drop_constraint("fk_watchlist_security", type_="foreignkey")
        batch.drop_column("security_id")
        batch.drop_column("security_name")
    op.drop_table("catalog_revisions")
    op.drop_table("catalog_attempts")
    op.drop_table("catalog_states")
    op.drop_table("securities")
