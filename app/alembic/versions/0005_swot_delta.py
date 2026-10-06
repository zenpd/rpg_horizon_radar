"""post-acquisition SWOT delta — kind/case_id on swot_briefs

Lets one SwotBrief row be either a subsidiary's own current SWOT
(kind="baseline", the only kind before this migration) or a qualitative
projection of that SWOT for one specific deal case (kind="post_acquisition"),
built by radar/post_acquisition.py — a pure reclassification over the
baseline, never a new score or a fabricated valuation. radar/bridge.py's
baseline-reload query is updated alongside this to filter on kind="baseline"
so a projection row can never be mistaken for the current baseline.

Revision ID: 0005_swot_delta
Revises: 0004_ripple_effects
Create Date: 2026-10-06 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_swot_delta"
down_revision = "0004_ripple_effects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("swot_briefs") as batch:
        batch.add_column(sa.Column("kind", sa.String(length=16), nullable=False, server_default="baseline"))
        batch.add_column(sa.Column("case_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("swot_briefs") as batch:
        batch.drop_column("case_id")
        batch.drop_column("kind")
