"""In-process background jobs for long runs (live ingestion, discovery, SWOT
briefs): the endpoint returns 202 with a job id at once and the UI polls
GET /api/v1/jobs/{id}. One running job per kind; a second request for the
same kind returns the running one. Jobs live in memory, so a restart forgets
them — the work they did is already in the database."""
from __future__ import annotations

import asyncio
import itertools
import traceback
from datetime import datetime
from typing import Awaitable, Callable

from shared.logger import get_logger

log = get_logger("services.jobs")

_ids = itertools.count(1)
JOBS: dict[str, dict] = {}
_tasks: set[asyncio.Task] = set()


def start(kind: str, work: Callable[[], Awaitable[dict]], started_by: str = "system") -> dict:
    running = next((j for j in JOBS.values() if j["kind"] == kind and j["status"] == "running"), None)
    if running:
        return running
    job = {"id": f"{kind}_{next(_ids)}", "kind": kind, "status": "running", "result": None, "error": None,
           "started_by": started_by, "started_at": datetime.utcnow().isoformat(timespec="seconds"), "finished_at": None}
    JOBS[job["id"]] = job

    async def run():
        try:
            job["result"] = await work()
            job["status"] = "completed"
        except Exception as e:  # keep the job pollable whatever happens
            log.error("job_failed", job=job["id"], error=str(e), trace=traceback.format_exc())
            job.update(status="failed", error=str(e) or type(e).__name__)
        finally:
            job["finished_at"] = datetime.utcnow().isoformat(timespec="seconds")

    task = asyncio.get_running_loop().create_task(run())
    _tasks.add(task)  # keep a reference so the task is not garbage-collected
    task.add_done_callback(_tasks.discard)
    return job


def get(job_id: str) -> dict | None:
    return JOBS.get(job_id)
