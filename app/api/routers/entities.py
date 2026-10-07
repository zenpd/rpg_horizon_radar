from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.schemas.entity import EntityOut
from db.models import Entity, Reviewer

router = APIRouter()


@router.get("", response_model=list[EntityOut])
async def list_entities(
    subsidiary: str | None = None,
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    entities = (await db.execute(select(Entity).order_by(Entity.id))).scalars().all()
    if not subsidiary:
        return entities
    return [e for e in entities
            if subsidiary in {link.subsidiary_code for cluster in e.clusters for link in cluster.subsidiary_links}]
