"""ripple effects — subsidiary dependency fabric + escalation brief field

Adds SubsidiaryDependency (a hand-curated table of each subsidiary's known
raw-material suppliers, byproduct consumers, and shared services/vendors,
seeded in db/seed.py) and a ripple_effects column on EscalationBrief,
populated by services/ripple.py's pure keyword/sector template-matching —
never an LLM guess, same "no fabrication" discipline as the brief's existing
pros/cons/directional_considerations fields.

Revision ID: 0004_ripple_effects
Revises: 0003_live_signals
Create Date: 2026-10-06 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_ripple_effects"
down_revision = "0003_live_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subsidiary_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subsidiary_code", sa.String(length=32), sa.ForeignKey("subsidiaries.code"), nullable=False),
        sa.Column("dependency_type", sa.String(length=32), nullable=False),
        sa.Column("counterparty_name", sa.String(length=255), nullable=False),
        sa.Column("counterparty_kind", sa.String(length=16), nullable=False),
        sa.Column("counterparty_subsidiary_code", sa.String(length=32), sa.ForeignKey("subsidiaries.code"), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_subsidiary_dependencies_subsidiary_code", "subsidiary_dependencies", ["subsidiary_code"])

    with op.batch_alter_table("escalation_briefs") as batch:
        batch.add_column(sa.Column("ripple_effects", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("escalation_briefs") as batch:
        batch.drop_column("ripple_effects")
    op.drop_index("ix_subsidiary_dependencies_subsidiary_code", table_name="subsidiary_dependencies")
    op.drop_table("subsidiary_dependencies")
