"""Background jobs for long runs (live ingestion, discovery, SWOT briefs): the
endpoint returns 202 with a job id at once and the UI polls GET /api/v1/jobs/{id}.

The work runs as a task in the replica that started it, but the job record is
also written to the ``connector_state`` table (``job:<id>``) when it starts and
when it ends, so a poll that lands on another replica still finds it. One
running job per kind across all replicas: the job holds the ``job-<kind>``
lease (services/lease.py) while it runs, and a second request for the same kind
returns the running one. If a replica dies mid-job the lease lapses after
JOB_TTL; the work done so far is already in the database."""
from __future__ import annotations

import asyncio
import json
import traceback
import uuid
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from db.base import get_db_session
from services import lease
from services import state as state_store
from shared.logger import get_logger

log = get_logger("services.jobs")

JOB_TTL = timedelta(hours=2)  # longer than any run: ingestion's Temporal activity times out at 30 minutes
JOBS: dict[str, dict] = {}  # jobs started by this replica
_tasks: set[asyncio.Task] = set()


async def _save(job: dict) -> None:
    async with get_db_session() as db:
        await state_store.save(db, f"job:{job['id']}", json.loads(json.dumps(job, default=str)))


async def start(kind: str, work: Callable[[], Awaitable[dict]], started_by: str = "system") -> dict:
    job_id = f"{kind}_{uuid.uuid4().hex[:12]}"
    if not await lease.acquire(f"job-{kind}", job_id, JOB_TTL):
        running = await get(await lease.holder(f"job-{kind}") or "")
        if running and running["status"] == "running":
            return running
        # The holder finished between the two reads; take the lease now it is free.
        if not await lease.acquire(f"job-{kind}", job_id, JOB_TTL):
            raise RuntimeError(f"A {kind} job is already running.")
    job = {"id": job_id, "kind": kind, "status": "running", "result": None, "error": None,
           "started_by": started_by, "started_at": datetime.utcnow().isoformat(timespec="seconds"), "finished_at": None}
    JOBS[job_id] = job
    await _save(job)

    async def run():
        try:
            job["result"] = await work()
            job["status"] = "completed"
        except Exception as e:  # keep the job pollable whatever happens
            log.error("job_failed", job=job_id, error=str(e), trace=traceback.format_exc())
            job.update(status="failed", error=str(e) or type(e).__name__)
        finally:
            job["finished_at"] = datetime.utcnow().isoformat(timespec="seconds")
            try:
                await _save(job)
                await lease.release(f"job-{kind}", job_id)
            except Exception as e:  # noqa: BLE001 — this replica still answers polls from JOBS
                log.error("job_record_not_saved", job=job_id, error=str(e))

    task = asyncio.get_running_loop().create_task(run())
    _tasks.add(task)  # keep a reference so the task is not garbage-collected
    task.add_done_callback(_tasks.discard)
    return job


async def get(job_id: str) -> dict | None:
    if job_id in JOBS:
        return JOBS[job_id]
    if not job_id:
        return None
    async with get_db_session() as db:
        job = await state_store.load(db, f"job:{job_id}") or None
    if job and job["status"] == "running" and await lease.holder(f"job-{job['kind']}") != job_id:
        # Its replica stopped before the job ended and the lease has lapsed.
        job.update(status="failed", error="The replica running this job stopped before it finished.")
    return job
