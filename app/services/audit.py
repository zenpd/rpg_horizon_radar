"""Audit log writer. Every read/write endpoint that touches a signal, entity,
digest, or admin action calls write_audit(). Rows are immutable — no router
anywhere exposes a delete for audit_logs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AuditLog, Reviewer


async def write_audit(
    db: AsyncSession,
    reviewer: Reviewer | None,
    action: str,
    resource_type: str,
    resource_id=None,
    detail: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        reviewer_id=reviewer.id if reviewer else None,
        reviewer_name_snapshot=reviewer.name if reviewer else "system",
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        detail=detail,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry
