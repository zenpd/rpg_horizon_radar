"""Keeps the radar current without anyone pressing a button. An asyncio task
started with the API (api/main.py) checks once a minute and runs what is due:

  discovery  Watchlist discovery (competitors) and target discovery (smaller
             companies to acquire, agents/target_discovery.py) for every
             subsidiary every DISCOVERY_EVERY_DAYS days (default 7), and on first
             start. The companies found are watched at once.
  ingest     A live ingestion run daily at INGEST_DAILY_AT (default 17:00 local).
             Each connector keeps its own pace and quota on top of this.
  opportunities  The Opportunity Analyst (agents/opportunity_analyst.py) daily at
             OPPORTUNITY_DAILY_AT (default 08:00 local): each company's news of
             the last two days, judged against its SWOT.
  theses     Every THESIS_EVERY: company sizes still missing or a month old
             (services/company_size.py), then the Acquisition Thesis agent
             (agents/acquisition_thesis.py) writes the thesis of every new M&A
             signal and rewrites one older than a week.
  swot       The SWOT Analyst (agents/swot_analyst.py) every SWOT_EVERY_DAYS days
             (default 7), and on first start: each company's research is
             refreshed, then its SWOT rebuilt, one company after another.

SCHEDULER_ENABLED=false turns it off (tests do). Last runs are kept in the
``scheduler`` ConnectorState row, so a restart does not repeat work.

Every replica starts the loop, but only the one holding the ``scheduler`` lease
(services/lease.py) runs a tick; it renews the lease every TICK, including
while a long ingestion run is in progress. If that replica stops, another takes
over within LEASE_TTL."""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta

from agents import acquisition_thesis, opportunity_analyst, swot_analyst, target_discovery, watchlist_discovery
from db.base import get_db_session
from services import company_size, lease, pipeline
from services import state as state_store
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("services.scheduler")

TICK = 60  # seconds between checks
THESIS_EVERY = timedelta(minutes=30)  # new signals get their thesis within this
LEASE = "scheduler"
LEASE_TTL = timedelta(seconds=3 * TICK)
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
    for job, at in (("ingest", s.ingest_daily_at), ("opportunities", s.opportunity_daily_at)):
        slot, last = _slot(now, at), state.get(job)
        if now >= slot and (not last or datetime.fromisoformat(last) < slot):
            out.append(job)
    last_s = state.get("swot")
    if not last_s or now - datetime.fromisoformat(last_s) >= timedelta(days=s.swot_every_days):
        out.append("swot")
    last_t = state.get("theses")
    # last, and straight after new signals, a rebuilt SWOT or new targets: those make theses out of date
    if not last_t or now - datetime.fromisoformat(last_t) >= THESIS_EVERY or {"ingest", "swot", "discovery"} & set(out):
        out.append("theses")
    return out


def next_runs(now: datetime, state: dict) -> dict:
    s = get_settings()
    out = {}
    for job, at in (("ingest", s.ingest_daily_at), ("opportunities", s.opportunity_daily_at)):
        slot, last = _slot(now, at), state.get(job)
        out[job] = (slot if now < slot or not last or datetime.fromisoformat(last) < slot else slot + timedelta(days=1)).isoformat(timespec="minutes")
    for job, days in (("discovery", s.discovery_every_days), ("swot", s.swot_every_days)):
        last = state.get(job)
        out[job] = (datetime.fromisoformat(last) + timedelta(days=days) if last else now).isoformat(timespec="minutes")
    return out


_DISCOVERING = asyncio.Lock()


async def discover_all(reviewer=None) -> dict:
    """Competitors, then the RPG companies' own sizes, then acquisition targets (sized as they are found).
    One at a time: a run asked for while one is going is skipped."""
    if _DISCOVERING.locked():
        return {"skipped": "A discovery run is already in progress.", "errors": []}
    async with _DISCOVERING:
        return await _discover_all(reviewer)


async def _discover_all(reviewer=None) -> dict:
    async with get_db_session() as db:
        competitors = await watchlist_discovery.discover(db, reviewer)
    async with get_db_session() as db:
        await company_size.refresh_due(db, limit=len(target_discovery.PROFILES))
    await bridge_sync()
    async with get_db_session() as db:
        targets = await target_discovery.discover(db, reviewer)
    await bridge_sync()
    return {**competitors, "targets": targets["added"], "too_big": targets["too_big"],
            "errors": competitors.get("errors", []) + targets["errors"]}


async def weekly_swot(user: str = "scheduler") -> dict:
    """Refresh each company's research and rebuild its SWOT, one company after another."""
    from radar.store import COMPANIES_ORDER  # imported here: the radar package loads after services

    built, errors = [], []
    for co in COMPANIES_ORDER:
        try:
            await asyncio.to_thread(swot_analyst.build, co, user, None, True)
            built.append(co)
        except Exception as e:  # noqa: BLE001 — one company failing never stops the others
            errors.append(f"{co}: {e}")
    return {"built": built, "errors": errors}


async def run_due(now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    async with get_db_session() as db:
        state = await state_store.load(db, "scheduler")
    ran = []
    for job in due(now, state):
        STATUS["running"] = job
        try:
            if job == "discovery":
                res = await discover_all()
            elif job == "opportunities":
                async with get_db_session() as db:
                    res = await opportunity_analyst.analyse_all(db)
                await bridge_sync()
            elif job == "swot":
                res = await weekly_swot()
            elif job == "theses":
                async with get_db_session() as db:
                    sized = await company_size.refresh_due(db)
                await bridge_sync()
                res = {**await write_agents_due(), "sized": sized}
            else:
                res = await pipeline.run_ingest()
                from services import market_data  # the RPG companies' own prices and results, for The financial market

                async with get_db_session() as db:
                    res["market"] = await market_data.refresh(db)
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


async def write_agents_due(user: str = "radar") -> dict:
    """The acquisition theses, then the competitor overviews, that are missing or out of date."""
    from agents import competitor_profile

    t = await acquisition_thesis.write_due(user)
    p = await competitor_profile.write_due(user)
    return {"written": t["written"], "profiles": p["written"], "errors": t["errors"] + p["errors"]}


async def bridge_sync() -> None:
    from radar import bridge  # imported here: the radar package loads after services

    await bridge.sync()


JOBS = ("ingest", "discovery", "opportunities", "swot", "theses")


async def status() -> dict:
    s = get_settings()
    async with get_db_session() as db:
        state = await state_store.load(db, "scheduler")
    return {"enabled": s.scheduler_enabled, "ingest_daily_at": s.ingest_daily_at, "discovery_every_days": s.discovery_every_days,
            "opportunity_daily_at": s.opportunity_daily_at, "swot_every_days": s.swot_every_days,
            "last": {k: state.get(k) for k in JOBS},
            "last_results": {k: state.get(f"{k}_result") for k in JOBS},
            "next": next_runs(datetime.now(), state), "leader": await lease.holder(LEASE), **STATUS}


async def _keep_lease() -> None:
    """Renew the lease while a tick runs, so a long ingestion run does not let it lapse."""
    while True:
        await asyncio.sleep(TICK)
        if not await lease.acquire(LEASE, lease.REPLICA_ID, LEASE_TTL):
            log.warning("scheduler_lease_lost", replica=lease.REPLICA_ID)


async def tick() -> list[str] | None:
    """One check: run what is due if this replica holds the lease, else None."""
    if not await lease.acquire(LEASE, lease.REPLICA_ID, LEASE_TTL):
        return None
    keeper = asyncio.get_running_loop().create_task(_keep_lease())
    try:
        return await run_due()
    finally:
        keeper.cancel()


async def _loop() -> None:
    while True:
        try:
            await tick()
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
        with contextlib.suppress(Exception):  # shutting down: the lease expires anyway
            await lease.release(LEASE, lease.REPLICA_ID)
