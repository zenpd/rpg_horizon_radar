from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.routers.signals import _build_summary
from api.schemas.digest import DigestDetailOut, DigestItemOut, DigestSummaryOut
from db.models import DigestIssue, Reviewer
from services.audit import write_audit
from services.digest import generate_digest

router = APIRouter()


@router.get("", response_model=list[DigestSummaryOut])
async def list_digests(
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    digests = (await db.execute(select(DigestIssue).order_by(DigestIssue.created_at.desc()))).scalars().all()

    out = []
    for digest in digests:
        breakdown: dict[str, int] = {}
        for item in digest.items:
            breakdown[item.subsidiary_code] = breakdown.get(item.subsidiary_code, 0) + 1
        out.append(
            DigestSummaryOut(
                id=digest.id,
                period_start=digest.period_start,
                period_end=digest.period_end,
                created_at=digest.created_at,
                subsidiary_breakdown=breakdown,
            )
        )
    return out


def _build_detail(digest: DigestIssue) -> DigestDetailOut:
    items = [DigestItemOut(subsidiary_code=item.subsidiary_code, cluster=_build_summary(item.cluster)) for item in digest.items]
    return DigestDetailOut(
        id=digest.id,
        period_start=digest.period_start,
        period_end=digest.period_end,
        created_at=digest.created_at,
        items=items,
    )


@router.get("/{digest_id}", response_model=DigestDetailOut)
async def get_digest(
    digest_id: int,
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    digest = (await db.execute(select(DigestIssue).where(DigestIssue.id == digest_id))).scalar_one_or_none()
    if digest is None:
        raise HTTPException(status_code=404, detail="Digest not found")

    await write_audit(db, reviewer, "view_digest", "digest_issue", resource_id=digest_id)
    return _build_detail(digest)


@router.post("/generate", response_model=DigestDetailOut)
async def generate_digest_endpoint(
    user: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    digest = await generate_digest(db, user)
    await write_audit(db, user, "digest_generate", "digest_issue", resource_id=digest.id)
    return _build_detail(digest)
