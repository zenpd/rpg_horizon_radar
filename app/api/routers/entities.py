from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.schemas.entity import EntityOut
from db.models import Entity, Reviewer, Subsidiary
from services import visibility

router = APIRouter()


@router.get("", response_model=list[EntityOut])
async def list_entities(
    subsidiary: str | None = None,
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    sub_map = {s.code: s for s in (await db.execute(select(Subsidiary))).scalars().all()}

    out = []
    entities = (await db.execute(select(Entity).order_by(Entity.id))).scalars().all()
    for entity in entities:
        routed_codes = {link.subsidiary_code for cluster in entity.clusters for link in cluster.subsidiary_links}
        if subsidiary and subsidiary not in routed_codes:
            continue
        if any(visibility.subsidiary_code_visible_to(reviewer, code, sub_map) for code in routed_codes):
            out.append(entity)

    return out
