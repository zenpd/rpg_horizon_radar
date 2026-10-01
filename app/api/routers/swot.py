"""SWOT briefs per subsidiary. Reading follows the same visibility rule as
signals (services/visibility.py) and is audit-logged; generating and editing
team notes is compliance_admin only."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer, require_role
from api.dependencies import get_db
from api.schemas.ingest import JobOut
from api.schemas.swot import SwotBriefOut, TeamNotes
from db.base import get_db_session
from db.models import Reviewer, Subsidiary, SwotBrief
from services import jobs, swot, visibility
from services.audit import write_audit

router = APIRouter()


async def _subsidiary(db: AsyncSession, code: str, reviewer: Reviewer) -> Subsidiary:
    sub = (await db.execute(select(Subsidiary).where(Subsidiary.code == code))).scalar_one_or_none()
    if sub is None or not visibility.subsidiary_visible_to(reviewer, sub):
        raise HTTPException(status_code=404, detail="Subsidiary not found")
    return sub


@router.get("/{code}", response_model=SwotBriefOut)
async def get_swot(code: str, reviewer: Reviewer = Depends(get_current_reviewer), db: AsyncSession = Depends(get_db)):
    await _subsidiary(db, code, reviewer)
    brief = (await db.execute(select(SwotBrief).where(SwotBrief.subsidiary_code == code)
                              .order_by(SwotBrief.generated_at.desc()).limit(1))).scalar_one_or_none()
    if brief is None:
        raise HTTPException(status_code=404, detail="No SWOT brief has been generated for this subsidiary yet")
    await write_audit(db, reviewer, "view_swot", "swot_brief", resource_id=brief.id, detail=f"subsidiary={code}")
    return SwotBriefOut(id=brief.id, subsidiary_code=code, generated_at=brief.generated_at,
                        generated_by=brief.generated_by.name if brief.generated_by else "scheduler", model=brief.model,
                        rounds=brief.rounds, content=brief.content, evidence=brief.evidence)


@router.post("/{code}/rebuild", response_model=JobOut, status_code=202)
async def rebuild_swot(code: str, admin: Reviewer = Depends(require_role("compliance_admin")), db: AsyncSession = Depends(get_db)):
    sub = await _subsidiary(db, code, admin)
    if not sub.compliance_gate:
        raise HTTPException(status_code=409, detail=f"{sub.name}'s compliance gate is closed")

    async def work():
        async with get_db_session() as s:
            return await swot.build(s, code, admin)
    return jobs.start(f"swot:{code}", work, started_by=admin.name)


@router.get("/{code}/team-notes", response_model=TeamNotes)
async def get_team_notes(code: str, reviewer: Reviewer = Depends(get_current_reviewer), db: AsyncSession = Depends(get_db)):
    sub = await _subsidiary(db, code, reviewer)
    return TeamNotes(**(sub.team_notes or {}))


@router.put("/{code}/team-notes", response_model=TeamNotes)
async def put_team_notes(code: str, payload: TeamNotes, admin: Reviewer = Depends(require_role("compliance_admin")),
                         db: AsyncSession = Depends(get_db)):
    sub = await _subsidiary(db, code, admin)
    notes = {k: [t.strip() for t in v if t.strip()] for k, v in payload.model_dump().items()}
    sub.team_notes = notes
    await db.commit()
    await write_audit(db, admin, "admin_change", "subsidiary", resource_id=code,
                      detail=f"team_notes strengths={len(notes['strengths'])} weaknesses={len(notes['weaknesses'])}")
    return TeamNotes(**notes)
