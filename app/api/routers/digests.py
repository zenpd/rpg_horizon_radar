from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer, require_role
from api.dependencies import get_db
from api.routers.signals import _build_summary, _subsidiary_map
from api.schemas.digest import DigestDetailOut, DigestItemOut, DigestSummaryOut
from db.models import DigestIssue, Reviewer, Subsidiary
from services import visibility
from services.audit import write_audit
from services.digest import generate_digest

router = APIRouter()


@router.get("", response_model=list[DigestSummaryOut])
async def list_digests(
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    sub_map = await _subsidiary_map(db)
    digests = (await db.execute(select(DigestIssue).order_by(DigestIssue.created_at.desc()))).scalars().all()

    out = []
    for digest in digests:
        breakdown: dict[str, int] = {}
        for item in digest.items:
            if visibility.subsidiary_code_visible_to(reviewer, item.subsidiary_code, sub_map):
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


def _build_detail(digest: DigestIssue, reviewer: Reviewer, sub_map: dict[str, Subsidiary]) -> DigestDetailOut:
    items = []
    for item in digest.items:
        if not visibility.subsidiary_code_visible_to(reviewer, item.subsidiary_code, sub_map):
            continue
        items.append(DigestItemOut(subsidiary_code=item.subsidiary_code, cluster=_build_summary(item.cluster, reviewer, sub_map)))
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

    sub_map = await _subsidiary_map(db)
    await write_audit(db, reviewer, "view_digest", "digest_issue", resource_id=digest_id)
    return _build_detail(digest, reviewer, sub_map)


@router.post("/generate", response_model=DigestDetailOut)
async def generate_digest_endpoint(
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    digest = await generate_digest(db, admin)
    await write_audit(db, admin, "admin_change", "digest_issue", resource_id=digest.id, detail="digest_generate")

    sub_map = await _subsidiary_map(db)
    return _build_detail(digest, admin, sub_map)
