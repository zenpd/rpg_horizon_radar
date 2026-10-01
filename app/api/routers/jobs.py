from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_role
from api.schemas.ingest import JobOut
from db.models import Reviewer
from services import jobs

router = APIRouter()


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, admin: Reviewer = Depends(require_role("compliance_admin"))):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found (jobs are kept in memory until the API restarts)")
    return job
