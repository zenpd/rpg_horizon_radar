"""remove approvals — no roles, no sector gates, no watchlist approval

Horizon Radar no longer has a compliance step (DESIGN.md §4): every signed-in
user sees every RPG company and every watched company, and a company found by
discovery is watched at once. This removes:

- ``reviewers.role`` and ``reviewers.subsidiary_scopes``: users have no roles
  or per-company scopes;
- ``subsidiaries.compliance_gate``: every company's sectors are ingested;
- ``entities.approved_by_id``: there is no approver. ``approved_at`` becomes
  ``watched_since``, and every ``proposed`` company becomes ``watching``
  (``watched_since`` = now). ``dismissed`` stays, so discovery never re-adds a
  company someone removed.

The audit log is kept as the activity history.

Downgrade re-adds the columns: every user becomes a ``compliance_admin``
(so nobody is locked out), every gate is closed, and nothing is re-proposed.

Revision ID: 0005_remove_approvals
Revises: 0004_remove_demo_data
Create Date: 2026-10-07 00:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_remove_approvals"
down_revision = "0004_remove_demo_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE entities SET approved_at = CURRENT_TIMESTAMP WHERE status = 'proposed' OR approved_at IS NULL")
    op.execute("UPDATE entities SET status = 'watching' WHERE status = 'proposed'")
    with op.batch_alter_table("entities") as batch:
        batch.drop_constraint("ck_entity_status", type_="check")
        batch.drop_constraint("fk_entities_approved_by", type_="foreignkey")
        batch.drop_column("approved_by_id")
        batch.alter_column("approved_at", new_column_name="watched_since", existing_type=sa.DateTime(), existing_nullable=True)
        batch.create_check_constraint("ck_entity_status", "status in ('watching', 'dismissed')")
    with op.batch_alter_table("subsidiaries") as batch:
        batch.drop_column("compliance_gate")
    with op.batch_alter_table("reviewers") as batch:
        batch.drop_column("subsidiary_scopes")
        batch.drop_column("role")


def downgrade() -> None:
    with op.batch_alter_table("reviewers") as batch:
        batch.add_column(sa.Column("role", sa.String(length=32), nullable=False, server_default="compliance_admin"))
        batch.add_column(sa.Column("subsidiary_scopes", sa.JSON(), nullable=False, server_default="[]"))
    with op.batch_alter_table("subsidiaries") as batch:
        batch.add_column(sa.Column("compliance_gate", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("entities") as batch:
        batch.drop_constraint("ck_entity_status", type_="check")
        batch.alter_column("watched_since", new_column_name="approved_at", existing_type=sa.DateTime(), existing_nullable=True)
        batch.add_column(sa.Column("approved_by_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_entities_approved_by", "reviewers", ["approved_by_id"], ["id"])
        batch.create_check_constraint("ck_entity_status", "status in ('watching', 'proposed', 'dismissed')")
