"""Durable save/load for the radar's mutable demo state (store.py), so decisions, plans,
follow-ups, theses, watch rules, universe additions and the activity feed survive a restart
(TODO.md "Persistence and platform"). Reuses the existing ``connector_state`` key/value table
(services/state.py's pattern) under one key — no new migration needed.

Store's methods are plain sync functions, called from FastAPI's sync path-operation handlers
(which Starlette runs in a worker thread with no event loop of its own) or at module import time
(before uvicorn's loop starts) — so calling ``asyncio.run()`` from here is safe in both cases.

What this does NOT do: share the app-wide async engine (db/base.py). That engine's connection
pool is bound to whichever event loop first uses it — uvicorn's main loop, for every other part of
this app. Driving it from a *second* loop (the one asyncio.run() spins up in a worker thread) is
exactly the "engine used across event loops" misuse asyncpg/SQLAlchemy don't support. Each call
here opens its own short-lived engine instead and disposes it immediately after — slightly more
setup cost, but it never touches the main pool, so there is no cross-loop sharing at all.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Any, Coroutine

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import ConnectorState, SwotBrief
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("radar.persistence")

KEY = "radar_mutable_state"


async def _load_async() -> dict:
    engine = create_async_engine(get_settings().database_url)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            row = (await db.execute(select(ConnectorState).where(ConnectorState.key == KEY))).scalar_one_or_none()
            return dict(row.value) if row else {}
    finally:
        await engine.dispose()


async def _save_async(value: dict) -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            row = (await db.execute(select(ConnectorState).where(ConnectorState.key == KEY))).scalar_one_or_none()
            now = datetime.utcnow()
            if row is None:
                db.add(ConnectorState(key=KEY, value=value, updated_at=now))
            else:
                row.value = dict(value)  # a new object, so SQLAlchemy sees the JSON change
                row.updated_at = now
            await db.commit()
    finally:
        await engine.dispose()


async def _save_post_acquisition_async(subsidiary_code: str, case_id: str, payload: dict) -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as db:
            db.add(SwotBrief(subsidiary_code=subsidiary_code, generated_at=datetime.utcnow(), model="", rounds=1,
                             content=payload, evidence=[], kind="post_acquisition", case_id=case_id))
            await db.commit()
    finally:
        await engine.dispose()


def save_post_acquisition(subsidiary_code: str, case_id: str, payload: dict) -> None:
    """Called from radar/api.py:decide() — a plain sync FastAPI handler, so (per the module
    docstring) a short-lived engine + asyncio.run() is the correct, already-proven pattern here,
    not bridge.py's thread-to-main-loop bridge (that one's built for the SWOT agent's own
    background worker thread, a different case). Best-effort, same as save() above: a failed
    write leaves the in-memory projection (still correct for this process) as the only copy."""
    try:
        _run(_save_post_acquisition_async(subsidiary_code, case_id, payload))
    except Exception as e:  # noqa: BLE001
        log.warning("radar_post_acquisition_save_failed", subsidiary_code=subsidiary_code, case_id=case_id, error=str(e))


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Drive ``coro`` to completion regardless of whether the calling thread already has an
    event loop running. Store's methods are plain sync functions called from two different
    places: FastAPI's sync path handlers (no loop in that worker thread — asyncio.run() is fine)
    and radar/bridge.py's async startup(), which calls Store.reset() while the main uvicorn loop
    IS running (asyncio.run() would raise there). In that second case, run a throwaway loop on a
    separate thread and block until it finishes — these are small, infrequent, fast calls (admin
    actions and startup), so a short synchronous wait is the simplest correct option; the
    alternative (making Store and its ~15 call sites in radar/api.py async) is a much larger,
    riskier change for the same result."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # no loop here — the common case (sync request handlers)

    result: dict[str, Any] = {}

    def _runner() -> None:
        result["value"] = asyncio.run(coro)

    t = threading.Thread(target=_runner)
    t.start()
    t.join()
    return result.get("value")


def load() -> dict:
    """The last-saved snapshot, or {} if there isn't one yet (first boot) or the load fails —
    the radar falls back to its demo defaults either way, so a bad read is never fatal."""
    try:
        return _run(_load_async()) or {}
    except Exception as e:  # noqa: BLE001 — a read failure must not block the app from starting
        log.warning("radar_state_load_failed", error=str(e))
        return {}


def save(value: dict) -> None:
    """Best-effort: a failed write leaves this process's in-memory state (still correct) as the
    only copy until the next successful save, rather than raising out of a request handler."""
    try:
        _run(_save_async(value))
    except Exception as e:  # noqa: BLE001
        log.warning("radar_state_save_failed", error=str(e))
