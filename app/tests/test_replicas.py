"""Work meant to run once across API replicas: the scheduler's lease and background job records
(services/lease.py, scheduler.py, jobs.py). A second replica is simulated by a second holder id
and by forgetting this process's in-memory jobs."""
from __future__ import annotations

import asyncio
from datetime import timedelta

from services import jobs, lease, scheduler

TTL = timedelta(minutes=3)


def arun(coro):
    return asyncio.run(coro)


def test_a_lease_has_one_holder_until_it_expires_or_is_released(seeded):
    async def go():
        assert await lease.acquire("t1", "replica-a", TTL)
        assert not await lease.acquire("t1", "replica-b", TTL), "held by a"
        assert await lease.acquire("t1", "replica-a", TTL), "the holder renews"
        assert await lease.holder("t1") == "replica-a"
        await lease.release("t1", "replica-b")  # not b's to release
        assert await lease.holder("t1") == "replica-a"
        await lease.release("t1", "replica-a")
        assert await lease.holder("t1") is None and await lease.acquire("t1", "replica-b", TTL)
        assert await lease.acquire("t2", "replica-a", timedelta(seconds=-1)), "an already-expired lease"
        assert await lease.holder("t2") is None and await lease.acquire("t2", "replica-b", TTL), "a dead holder's lease passes on"
    arun(go())


def test_only_the_replica_holding_the_lease_runs_a_scheduler_tick(seeded, monkeypatch):
    ran = []

    async def fake_run_due():
        ran.append(lease.REPLICA_ID)
        return []

    monkeypatch.setattr(scheduler, "run_due", fake_run_due)

    async def go():
        await lease.release(scheduler.LEASE, "other-replica")
        assert await lease.acquire(scheduler.LEASE, "other-replica", TTL)
        assert await scheduler.tick() is None and ran == [], "another replica leads"
        await lease.release(scheduler.LEASE, "other-replica")
        assert await scheduler.tick() == [] and ran == [lease.REPLICA_ID]
        assert (await scheduler.status())["leader"] == lease.REPLICA_ID
        await lease.release(scheduler.LEASE, lease.REPLICA_ID)
    arun(go())


def test_a_job_is_visible_from_any_replica_and_runs_once_per_kind(seeded):
    async def go():
        gate = asyncio.Event()

        async def work():
            await gate.wait()
            return {"n": 1}

        job = await jobs.start("t-kind", work, started_by="tester")
        again = await jobs.start("t-kind", work, started_by="someone else")
        assert again["id"] == job["id"], "one running job per kind"
        jobs.JOBS.pop(job["id"])  # as another replica sees it: only the stored record
        assert (await jobs.get(job["id"]))["status"] == "running"
        assert (await jobs.start("t-kind", work))["id"] == job["id"], "also across replicas"
        gate.set()
        while job["status"] == "running":
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # the record is saved after the status flips
        stored = await jobs.get(job["id"])
        assert stored["status"] == "completed" and stored["result"] == {"n": 1} and stored["finished_at"]
        assert await lease.holder("job-t-kind") is None, "released when done"
        assert await jobs.get("t-kind_missing") is None
    arun(go())


def test_a_job_whose_replica_stopped_reads_as_failed(seeded):
    async def go():
        async def never():
            await asyncio.Event().wait()

        job = await jobs.start("t-dead", never)
        jobs.JOBS.pop(job["id"])
        await lease.release("job-t-dead", job["id"])  # the lease lapsing, as when its replica dies
        got = await jobs.get(job["id"])
        assert got["status"] == "failed" and "stopped" in got["error"]
        for t in list(jobs._tasks):
            t.cancel()
    arun(go())
