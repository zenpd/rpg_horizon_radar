"""remove demo data — fictional companies, demo logins, demo-built SWOTs

Horizon Radar no longer ships any invented data (DESIGN.md §15). This removes
what earlier versions seeded into existing databases:

- every fictional entity (``is_fictional = true``) with its raw signals,
  clusters, scores, routing links, digest items and escalation briefs, then any
  digest issue left with no items;
- every SWOT brief: all were drafted from the demo strategy-team list and demo
  deal targets;
- the radar's saved state (``connector_state`` key ``radar_mutable_state``),
  whose cases, theses and watch rules were built on demo records;
- the ``is_fictional`` column itself.

Demo reviewer logins (``@rpg-demo.local``, shared password) are disabled, not
deleted: audit rows and approvals still point at them, and the audit trail is
kept whole. Real companies, their signals and the audit log are untouched, and
so are the sector gates — opening or closing one is a compliance decision.

Downgrade restores the column only; deleted demo rows are not recreated.

Revision ID: 0004_remove_demo_data
Revises: 0003_live_signals
Create Date: 2026-10-06 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_remove_demo_data"
down_revision = "0003_live_signals"
branch_labels = None
depends_on = None

DISABLED = "!disabled: demo login removed in migration 0004"


def upgrade() -> None:
    fictional = "SELECT id FROM entities WHERE is_fictional = true"
    clusters = f"SELECT id FROM signal_clusters WHERE entity_id IN ({fictional})"
    for table in ("opportunity_scores", "cluster_subsidiary_links", "digest_items", "escalation_briefs"):
        op.execute(f"DELETE FROM {table} WHERE cluster_id IN ({clusters})")
    op.execute(f"DELETE FROM signal_clusters WHERE entity_id IN ({fictional})")
    op.execute(f"DELETE FROM raw_signals WHERE entity_id IN ({fictional})")
    op.execute("DELETE FROM entities WHERE is_fictional = true")
    op.execute("DELETE FROM digest_issues WHERE id NOT IN (SELECT DISTINCT digest_id FROM digest_items)")
    op.execute("DELETE FROM swot_briefs")
    op.execute("DELETE FROM connector_state WHERE key = 'radar_mutable_state'")
    op.execute(sa.text("UPDATE reviewers SET password_hash = :h WHERE email LIKE '%@rpg-demo.local'").bindparams(h=DISABLED))

    with op.batch_alter_table("entities") as batch:
        batch.drop_column("is_fictional")
        batch.alter_column("origin", existing_type=sa.String(length=16), server_default="manual")


def downgrade() -> None:
    with op.batch_alter_table("entities") as batch:
        batch.alter_column("origin", existing_type=sa.String(length=16), server_default="seed")
        batch.add_column(sa.Column("is_fictional", sa.Boolean(), nullable=False, server_default=sa.false()))
