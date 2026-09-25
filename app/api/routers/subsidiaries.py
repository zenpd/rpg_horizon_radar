from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer, require_role
from api.dependencies import get_db
from api.schemas.subsidiary import GateUpdateRequest, SubsidiaryOut
from db.models import Reviewer, Subsidiary
from services.audit import write_audit

router = APIRouter()


@router.get("", response_model=list[SubsidiaryOut])
async def list_subsidiaries(
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    # compliance_gate is rollout status, not sensitive — every reviewer sees it
    # truthfully so the UI can gray out gated-off subsidiaries. What's gated is
    # SIGNAL visibility, handled in api/routers/signals.py.
    result = await db.execute(select(Subsidiary).order_by(Subsidiary.code))
    return result.scalars().all()


@router.patch("/{code}/gate", response_model=SubsidiaryOut)
async def update_gate(
    code: str,
    payload: GateUpdateRequest,
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subsidiary).where(Subsidiary.code == code))
    subsidiary = result.scalar_one_or_none()
    if subsidiary is None:
        raise HTTPException(status_code=404, detail="Subsidiary not found")

    subsidiary.compliance_gate = payload.compliance_gate
    await db.commit()
    await db.refresh(subsidiary)

    await write_audit(
        db, admin, "gate_change", "subsidiary", resource_id=code,
        detail=f"compliance_gate={payload.compliance_gate}",
    )
    return subsidiary
