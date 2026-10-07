from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.schemas.subsidiary import SubsidiaryOut
from db.models import Reviewer, Subsidiary

router = APIRouter()


@router.get("", response_model=list[SubsidiaryOut])
async def list_subsidiaries(
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subsidiary).order_by(Subsidiary.code))
    return result.scalars().all()
