"""Keeps the radar current without anyone pressing a button. An asyncio task
started with the API (api/main.py) checks once a minute and runs what is due:

  discovery  Watchlist discovery for gate-open subsidiaries every
             DISCOVERY_EVERY_DAYS days (default 7), and on first start. It only
             proposes companies; a compliance_admin still approves each one.
  ingest     A live ingestion run daily at INGEST_DAILY_AT (default 17:00 local),
             followed by SWOT rebuilds for subsidiaries whose signals changed.
             Each connector keeps its own pace and quota on top of this.
  digest     A weekly M&A-signal digest (services/digest.py) every
             DIGEST_EVERY_DAYS days (default 7), snapshotting live clusters
             scoring at or above DIGEST_THRESHOLD per gate-open subsidiary.
             Runs after ingest so the same tick's fresh clusters are included.

SCHEDULER_ENABLED=false turns it off (tests do). Last runs are kept in the
``scheduler`` ConnectorState row, so a restart does not repeat work. In a
multi-replica deployment run it in one replica only, or replace it with a
Temporal Schedule on IngestionWorkflow."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from db.base import get_db_session
from services import digest, discovery, pipeline
from services import state as state_store
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("services.scheduler")

TICK = 60  # seconds between checks
STATUS: dict = {"running": None, "last_error": None}
_task: asyncio.Task | None = None


def _slot(now: datetime, at: str) -> datetime:
    h, m = (int(x) for x in at.split(":"))
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def due(now: datetime, state: dict) -> list[str]:
    s = get_settings()
    out = []
    last_d = state.get("discovery")
    if not last_d or now - datetime.fromisoformat(last_d) >= timedelta(days=s.discovery_every_days):
        out.append("discovery")
    slot = _slot(now, s.ingest_daily_at)
    last_i = state.get("ingest")
    if now >= slot and (not last_i or datetime.fromisoformat(last_i) < slot):
        out.append("ingest")
    last_g = state.get("digest")
    if not last_g or now - datetime.fromisoformat(last_g) >= timedelta(days=s.digest_every_days):
        out.append("digest")
    return out


def next_runs(now: datetime, state: dict) -> dict:
    s = get_settings()
    slot = _slot(now, s.ingest_daily_at)
    last_i = state.get("ingest")
    ingest_next = slot if now < slot or not last_i or datetime.fromisoformat(last_i) < slot else slot + timedelta(days=1)
    last_d = state.get("discovery")
    disc_next = datetime.fromisoformat(last_d) + timedelta(days=s.discovery_every_days) if last_d else now
    last_g = state.get("digest")
    digest_next = datetime.fromisoformat(last_g) + timedelta(days=s.digest_every_days) if last_g else now
    return {"ingest": ingest_next.isoformat(timespec="minutes"), "discovery": disc_next.isoformat(timespec="minutes"),
            "digest": digest_next.isoformat(timespec="minutes")}


async def run_due(now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    async with get_db_session() as db:
        state = await state_store.load(db, "scheduler")
    ran = []
    for job in due(now, state):
        STATUS["running"] = job
        try:
            if job == "discovery":
                async with get_db_session() as db:
                    res = await discovery.discover(db)
            elif job == "digest":
                async with get_db_session() as db:
                    issue = await digest.generate_digest(db, created_by=None)
                    res = {"digest_id": issue.id, "items": len(issue.items), "errors": []}
            else:
                res = await pipeline.run_ingest()
            state[job] = now.isoformat(timespec="seconds")
            state[f"{job}_result"] = {k: v for k, v in res.items() if k != "errors"} | {"errors": (res.get("errors") or [])[:20]}
            ran.append(job)
        except Exception as e:  # noqa: BLE001 — the loop must survive any failure
            log.error("scheduler_job_failed", job=job, error=str(e))
            STATUS["last_error"] = f"{job}: {e}"
            state[job] = now.isoformat(timespec="seconds")  # do not retry every minute; next slot retries
        finally:
            STATUS["running"] = None
        async with get_db_session() as db:
            await state_store.save(db, "scheduler", state)
    return ran


async def status() -> dict:
    s = get_settings()
    async with get_db_session() as db:
        state = await state_store.load(db, "scheduler")
    return {"enabled": s.scheduler_enabled, "ingest_daily_at": s.ingest_daily_at, "discovery_every_days": s.discovery_every_days,
            "digest_every_days": s.digest_every_days,
            "auto_swot": s.auto_swot, "last": {k: state.get(k) for k in ("ingest", "discovery", "digest")},
            "last_results": {k: state.get(f"{k}_result") for k in ("ingest", "discovery", "digest")},
            "next": next_runs(datetime.now(), state), **STATUS}


async def _loop() -> None:
    while True:
        try:
            await run_due()
        except Exception as e:  # noqa: BLE001
            STATUS["last_error"] = str(e)
            log.error("scheduler_tick_failed", error=str(e))
        await asyncio.sleep(TICK)


def start() -> None:
    global _task
    if get_settings().scheduler_enabled and _task is None:
        _task = asyncio.get_running_loop().create_task(_loop())
        log.info("scheduler_started")


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
