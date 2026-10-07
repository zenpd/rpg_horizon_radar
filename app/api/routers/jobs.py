from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_reviewer
from api.schemas.ingest import JobOut
from db.models import Reviewer
from services import jobs

router = APIRouter()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: Reviewer = Depends(get_current_reviewer)):
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
