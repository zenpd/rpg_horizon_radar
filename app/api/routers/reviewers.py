from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import hash_password, require_role
from api.dependencies import get_db
from api.schemas.reviewer import ReviewerCreate, ReviewerOut
from db.models import Reviewer
from services.audit import write_audit

router = APIRouter()


@router.get("", response_model=list[ReviewerOut])
async def list_reviewers(
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reviewer).order_by(Reviewer.id))
    return result.scalars().all()


@router.post("", response_model=ReviewerOut)
async def create_reviewer(
    payload: ReviewerCreate,
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(Reviewer).where(Reviewer.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="A reviewer with that email already exists")
    if payload.role not in ("corp_strategy_reviewer", "compliance_admin"):
        raise HTTPException(status_code=400, detail="role must be corp_strategy_reviewer or compliance_admin")

    reviewer = Reviewer(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        subsidiary_scopes=payload.subsidiary_scopes,
        created_at=datetime.utcnow(),
    )
    db.add(reviewer)
    await db.commit()
    await db.refresh(reviewer)

    await write_audit(
        db, admin, "admin_change", "reviewer", resource_id=reviewer.id,
        detail=f"reviewer_created:{reviewer.email}",
    )
    return reviewer


@router.delete("/{reviewer_id}", response_model=ReviewerOut)
async def delete_reviewer(
    reviewer_id: int,
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    reviewer = (await db.execute(select(Reviewer).where(Reviewer.id == reviewer_id))).scalar_one_or_none()
    if reviewer is None:
        raise HTTPException(status_code=404, detail="Reviewer not found")

    if reviewer.role == "compliance_admin":
        remaining_admins = (
            await db.execute(
                select(func.count()).select_from(Reviewer).where(
                    Reviewer.role == "compliance_admin", Reviewer.id != reviewer_id
                )
            )
        ).scalar_one()
        if remaining_admins == 0:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining compliance_admin")

    # Snapshot fields before the row disappears — the ORM instance is expired
    # after commit and its attributes can no longer be read for the response
    # or the audit detail string.
    snapshot = ReviewerOut.model_validate(reviewer).model_dump()

    await db.delete(reviewer)
    await db.commit()

    await write_audit(
        db, admin, "admin_change", "reviewer", resource_id=reviewer_id,
        detail=f"reviewer_deleted:{snapshot['email']}",
    )
    return snapshot
