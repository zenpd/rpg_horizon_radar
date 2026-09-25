"""Triggers the signal-ingestion pipeline — see DESIGN.md §10 and
BOOTSTRAP_GUIDE.md's Temporal section.

Primary path: start IngestionWorkflow on Temporal, so the run is durable and
retried on transient failure (BOOTSTRAP_GUIDE.md's "Durability with Temporal"
pattern, applied here for real rather than left commented out). Fallback: if
the worker/Temporal isn't reachable — e.g. `uvicorn --reload` on its own
without `docker compose up` — run the pipeline inline so the demo click still
works. Both paths call the exact same services.ingest code.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from api.auth import require_role
from api.dependencies import get_db
from api.schemas.ingest import IngestRunResult
from db.models import Reviewer
from services.audit import write_audit
from services.ingest import run_ingest_for_open_subsidiaries
from shared.config import get_settings
from shared.logger import get_logger

router = APIRouter()
log = get_logger("api.ingest")
settings = get_settings()


async def _run_via_temporal() -> dict | None:
    try:
        from workflows.ingestion_workflow import IngestionWorkflow

        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        return await client.execute_workflow(
            IngestionWorkflow.run,
            id=f"ingestion-{settings.temporal_namespace}",
            task_queue=settings.temporal_task_queue_agents,
        )
    except Exception as exc:  # noqa: BLE001 — Temporal/worker unreachable is an expected local-dev case
        log.warning("temporal_ingest_unavailable_falling_back_inline", error=str(exc))
        return None


@router.post("/run", response_model=IngestRunResult)
async def run_ingest(
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await _run_via_temporal()
    via = "temporal"
    if result is None:
        result = await run_ingest_for_open_subsidiaries(db)
        via = "inline_fallback"

    await write_audit(
        db, admin, "ingest_run", "raw_signal",
        detail=f"via={via} new_raw_signals={result['new_raw_signals']} clusters_updated={result['clusters_updated']}",
    )
    return IngestRunResult(**result)
