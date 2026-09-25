"""rpg horizon radar schema — subsidiaries, entities, signals, digests, audit

Revision ID: 0002_horizon_radar
Revises: 0001_initial
Create Date: 2026-09-25 00:00:00

Regenerate for further model changes with:
    alembic revision --autogenerate -m "your change"
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_horizon_radar"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subsidiaries",
        sa.Column("code", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sectors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("compliance_gate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signal_focus", sa.Text(), nullable=False, server_default=""),
    )

    op.create_table(
        "reviewers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("subsidiary_scopes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reviewers_email", "reviewers", ["email"])

    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sectors", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("category", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("is_fictional", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("is_fictional = true", name="ck_entity_must_be_fictional"),
    )

    op.create_table(
        "raw_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("headline", sa.String(length=512), nullable=False),
        sa.Column("source_excerpt", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_url", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_raw_signals_entity_id", "raw_signals", ["entity_id"])

    op.create_table(
        "signal_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_id", sa.Integer(), sa.ForeignKey("entities.id"), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("window_end", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="live"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("evaluated_by_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_signal_clusters_entity_id", "signal_clusters", ["entity_id"])

    op.create_table(
        "opportunity_scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("signal_clusters.id"), nullable=False, unique=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("signal_types_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "cluster_subsidiary_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("signal_clusters.id"), nullable=False),
        sa.Column("subsidiary_code", sa.String(length=32), sa.ForeignKey("subsidiaries.code"), nullable=False),
    )
    op.create_index("ix_cluster_subsidiary_links_cluster_id", "cluster_subsidiary_links", ["cluster_id"])
    op.create_index("ix_cluster_subsidiary_links_subsidiary_code", "cluster_subsidiary_links", ["subsidiary_code"])

    op.create_table(
        "digest_issues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=True),
    )

    op.create_table(
        "digest_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("digest_id", sa.Integer(), sa.ForeignKey("digest_issues.id"), nullable=False),
        sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("signal_clusters.id"), nullable=False),
        sa.Column("subsidiary_code", sa.String(length=32), sa.ForeignKey("subsidiaries.code"), nullable=False),
    )
    op.create_index("ix_digest_items_digest_id", "digest_items", ["digest_id"])
    op.create_index("ix_digest_items_cluster_id", "digest_items", ["cluster_id"])
    op.create_index("ix_digest_items_subsidiary_code", "digest_items", ["subsidiary_code"])

    op.create_table(
        "escalation_briefs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.Integer(), sa.ForeignKey("signal_clusters.id"), nullable=False, unique=True),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("escalated_by_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=True),
        sa.Column("pros", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("cons", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("directional_considerations", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("deal_complexity", sa.String(length=16), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=True),
        sa.Column("reviewer_name_snapshot", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("escalation_briefs")
    op.drop_index("ix_digest_items_subsidiary_code", table_name="digest_items")
    op.drop_index("ix_digest_items_cluster_id", table_name="digest_items")
    op.drop_index("ix_digest_items_digest_id", table_name="digest_items")
    op.drop_table("digest_items")
    op.drop_table("digest_issues")
    op.drop_index("ix_cluster_subsidiary_links_subsidiary_code", table_name="cluster_subsidiary_links")
    op.drop_index("ix_cluster_subsidiary_links_cluster_id", table_name="cluster_subsidiary_links")
    op.drop_table("cluster_subsidiary_links")
    op.drop_table("opportunity_scores")
    op.drop_index("ix_signal_clusters_entity_id", table_name="signal_clusters")
    op.drop_table("signal_clusters")
    op.drop_index("ix_raw_signals_entity_id", table_name="raw_signals")
    op.drop_table("raw_signals")
    op.drop_table("entities")
    op.drop_index("ix_reviewers_email", table_name="reviewers")
    op.drop_table("reviewers")
    op.drop_table("subsidiaries")
