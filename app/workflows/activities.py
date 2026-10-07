"""Temporal activities — the side-effecting steps a workflow orchestrates.

Activities run in the worker process (workers/worker.py). Keep them
idempotent where possible; Temporal may retry them.
"""
from __future__ import annotations

from temporalio import activity

from db.base import get_db_session
from services.ingest import run_ingest_all
from shared.logger import get_logger

log = get_logger("workflows.activities")


@activity.defn
async def run_ingestion_activity() -> dict:
    """Run the live ingestion + scoring + routing pipeline for every watched
    company (see services/ingest.py). Wrapped as a Temporal
    activity so a scheduled or on-demand ingestion run gets retries and
    durability for free — the actual pipeline logic is identical to what a
    plain inline call would run; this activity only adds the DB session and
    the Temporal retry/timeout envelope around it.

    Idempotent: mock connectors return deterministic fixed data and
    fetch_and_store_raw_signals dedupes on (entity_id, signal_type, headline,
    observed_at), so a retried attempt after a partial failure is safe.
    """
    async with get_db_session() as db:
        result = await run_ingest_all(db)
    log.info("ingestion_activity_complete", **result)
    return result
