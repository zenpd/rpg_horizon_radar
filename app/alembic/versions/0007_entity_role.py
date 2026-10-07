"""entity role — competitor or acquisition target

A watched company is either a competitor (found by watchlist discovery or added by hand) or an
acquisition target (found by target discovery, agents/target_discovery.py). Only targets that are
plausibly acquirable — at most half the size of the RPG company — become M&A signals.

Revision ID: 0007_entity_role
Revises: 0006_opportunity_findings
Create Date: 2026-10-07 18:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_entity_role"
down_revision = "0006_opportunity_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("entities") as batch:
        batch.add_column(sa.Column("role", sa.String(length=16), nullable=False, server_default="competitor"))


def downgrade() -> None:
    with op.batch_alter_table("entities") as batch:
        batch.drop_column("role")
