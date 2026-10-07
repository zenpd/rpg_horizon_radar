"""Users who can sign in. Any signed-in user can list, add and remove users;
there are no roles. Every change is recorded in the activity history."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer, hash_password
from api.dependencies import get_db
from api.schemas.reviewer import ReviewerCreate, ReviewerOut
from db.models import Reviewer
from services.audit import write_audit

router = APIRouter()


@router.get("", response_model=list[ReviewerOut])
async def list_reviewers(
    user: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Reviewer).order_by(Reviewer.id))
    return result.scalars().all()


@router.post("", response_model=ReviewerOut)
async def create_reviewer(
    payload: ReviewerCreate,
    user: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(Reviewer).where(Reviewer.email == payload.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="A user with that email already exists")

    reviewer = Reviewer(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        created_at=datetime.utcnow(),
    )
    db.add(reviewer)
    await db.commit()
    await db.refresh(reviewer)

    await write_audit(db, user, "user_change", "reviewer", resource_id=reviewer.id, detail=f"user_added:{reviewer.email}")
    return reviewer


@router.delete("/{reviewer_id}", response_model=ReviewerOut)
async def delete_reviewer(
    reviewer_id: int,
    user: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    reviewer = (await db.execute(select(Reviewer).where(Reviewer.id == reviewer_id))).scalar_one_or_none()
    if reviewer is None:
        raise HTTPException(status_code=404, detail="User not found")
    if reviewer.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")

    # Snapshot fields before the row disappears — the ORM instance is expired
    # after commit and its attributes can no longer be read for the response
    # or the activity detail string.
    snapshot = ReviewerOut.model_validate(reviewer).model_dump()

    await db.delete(reviewer)
    await db.commit()

    await write_audit(db, user, "user_change", "reviewer", resource_id=reviewer_id, detail=f"user_removed:{snapshot['email']}")
    return snapshot
