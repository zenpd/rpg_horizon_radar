"""live signals — real watched entities, connector state, radar SWOTs

Lifts the fictional-only CHECK on entities (see DESIGN.md §15) and replaces it
with the approval workflow: discovered companies arrive as ``proposed`` and are
ingested only once a compliance_admin sets them to ``watching``.

Revision ID: 0003_live_signals
Revises: 0002_horizon_radar
Create Date: 2026-10-01 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_live_signals"
down_revision = "0002_horizon_radar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sqlite = op.get_bind().dialect.name == "sqlite"

    if not sqlite:
        op.drop_constraint("ck_entity_must_be_fictional", "entities", type_="check")
    # SQLite cannot drop a constraint in place; batch mode rebuilds the table
    # from the column list below, leaving the old CHECK behind.
    with op.batch_alter_table("entities", recreate="always" if sqlite else "auto") as batch:
        if sqlite:
            try:
                batch.drop_constraint("ck_entity_must_be_fictional", type_="check")
            except (KeyError, ValueError):
                pass  # not reflected by this SQLite version; the rebuild drops it anyway
        batch.add_column(sa.Column("origin", sa.String(length=16), nullable=False, server_default="seed"))
        batch.add_column(sa.Column("status", sa.String(length=16), nullable=False, server_default="watching"))
        batch.add_column(sa.Column("query_name", sa.String(length=255), nullable=False, server_default=""))
        batch.add_column(sa.Column("nse_symbol", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("discovery", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("approved_by_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("approved_at", sa.DateTime(), nullable=True))
        batch.create_foreign_key("fk_entities_approved_by", "reviewers", ["approved_by_id"], ["id"])
        batch.create_check_constraint("ck_entity_status", "status in ('watching', 'proposed', 'dismissed')")

    with op.batch_alter_table("raw_signals") as batch:
        batch.add_column(sa.Column("provider", sa.String(length=64), nullable=False, server_default="mock"))

    op.create_table(
        "connector_state",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "swot_briefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subsidiary_code", sa.String(length=32), sa.ForeignKey("subsidiaries.code"), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("generated_by_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("rounds", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("content", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_swot_briefs_subsidiary_code", "swot_briefs", ["subsidiary_code"])


def downgrade() -> None:
    op.drop_index("ix_swot_briefs_subsidiary_code", table_name="swot_briefs")
    op.drop_table("swot_briefs")
    op.drop_table("connector_state")
    with op.batch_alter_table("raw_signals") as batch:
        batch.drop_column("provider")
    # Real companies cannot satisfy the restored fictional-only CHECK, so they
    # and everything derived from them go.
    real = "SELECT id FROM entities WHERE is_fictional = false"
    clusters = f"SELECT id FROM signal_clusters WHERE entity_id IN ({real})"
    for table in ("opportunity_scores", "cluster_subsidiary_links", "digest_items", "escalation_briefs"):
        op.execute(f"DELETE FROM {table} WHERE cluster_id IN ({clusters})")
    op.execute(f"DELETE FROM signal_clusters WHERE entity_id IN ({real})")
    op.execute(f"DELETE FROM raw_signals WHERE entity_id IN ({real})")
    op.execute("DELETE FROM entities WHERE is_fictional = false")
    with op.batch_alter_table("entities") as batch:
        batch.drop_constraint("ck_entity_status", type_="check")
        batch.drop_constraint("fk_entities_approved_by", type_="foreignkey")
        for col in ("approved_at", "approved_by_id", "discovery", "nse_symbol", "query_name", "status", "origin"):
            batch.drop_column(col)
        batch.create_check_constraint("ck_entity_must_be_fictional", "is_fictional = true")
