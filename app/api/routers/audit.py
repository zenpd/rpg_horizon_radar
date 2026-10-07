"""The activity history (who did what, when), readable by every user."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.schemas.audit import AuditLogOut
from db.models import AuditLog, Reviewer

router = APIRouter()


@router.get("", response_model=list[AuditLogOut])
async def list_audit_log(
    limit: int = 100,
    action: str | None = None,
    reviewer_id: int | None = None,
    user: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if reviewer_id:
        query = query.where(AuditLog.reviewer_id == reviewer_id)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()
