"""Ask Radar conversations — saved per user

A conversation (chat_threads) belongs to the user who started it; its turns (chat_messages)
keep the answer's cited sources (agents/ask_agent.py).

Revision ID: 0008_chats
Revises: 0007_entity_role
Create Date: 2026-10-08 18:00:00
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_chats"
down_revision = "0007_entity_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("reviewers.id"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=64), nullable=False, server_default="All"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_chat_threads_reviewer_id", "chat_threads", ["reviewer_id"])
    op.create_index("ix_chat_threads_updated_at", "chat_threads", ["updated_at"])
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.Integer(), sa.ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("company", sa.String(length=64), nullable=False, server_default="All"),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("used_web", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role in ('user', 'assistant')", name="ck_chat_role"),
    )
    op.create_index("ix_chat_messages_thread_id", "chat_messages", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_thread_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_threads_updated_at", table_name="chat_threads")
    op.drop_index("ix_chat_threads_reviewer_id", table_name="chat_threads")
    op.drop_table("chat_threads")
