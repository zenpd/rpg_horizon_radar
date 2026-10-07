"""opportunity findings — the daily Opportunity Analyst's results

One row per opportunity or threat found in a day's news for one subsidiary, with
the SWOT item it affects and the news it cites (agents/opportunity_analyst.py).

Revision ID: 0006_opportunity_findings
Revises: 0005_remove_approvals
Create Date: 2026-10-07 12:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_opportunity_findings"
down_revision = "0005_remove_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opportunity_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("subsidiary_code", sa.String(length=32), sa.ForeignKey("subsidiaries.code"), nullable=False),
        sa.Column("found_on", sa.DateTime(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("swot_ref", sa.String(length=8), nullable=True),
        sa.Column("swot_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("effect", sa.Text(), nullable=False, server_default=""),
        sa.Column("action", sa.Text(), nullable=False, server_default=""),
        sa.Column("impact", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("urgency", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("kind in ('opportunity', 'threat')", name="ck_finding_kind"),
        sa.CheckConstraint("status in ('new', 'kept', 'dismissed')", name="ck_finding_status"),
    )
    op.create_index("ix_opportunity_findings_subsidiary_code", "opportunity_findings", ["subsidiary_code"])
    op.create_index("ix_opportunity_findings_found_on", "opportunity_findings", ["found_on"])


def downgrade() -> None:
    op.drop_index("ix_opportunity_findings_found_on", table_name="opportunity_findings")
    op.drop_index("ix_opportunity_findings_subsidiary_code", table_name="opportunity_findings")
    op.drop_table("opportunity_findings")
