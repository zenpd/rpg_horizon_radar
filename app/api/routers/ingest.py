"""Triggers the signal-ingestion pipeline — see DESIGN.md §10 and
BOOTSTRAP_GUIDE.md's Temporal section.

Live connectors make a run take minutes, so this starts it as a background
job and returns 202 at once; the UI polls GET /api/v1/jobs/{id}. The run
itself goes through services.pipeline: IngestionWorkflow on Temporal when
reachable (durable, retried), the same services.ingest code inline otherwise.
Both paths write the ``ingest_run`` audit row."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth import get_current_reviewer
from api.schemas.ingest import JobOut
from db.models import Reviewer
from services import jobs, pipeline

router = APIRouter()


@router.post("/run", response_model=JobOut, status_code=202)
async def run_ingest(user: Reviewer = Depends(get_current_reviewer)):
    return await jobs.start("ingest", lambda: pipeline.run_ingest(user), started_by=user.name)
