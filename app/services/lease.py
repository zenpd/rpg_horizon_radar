"""Leases in the ``connector_state`` table, so that work meant to run once
across all API replicas does: the scheduler's ticks (services/scheduler.py)
and one background job per kind (services/jobs.py).

A lease is the row ``lease:<name>`` = {holder, until}. acquire() takes it when
it is free, expired or already ours, and extends it; on PostgreSQL the row is
locked (SELECT ... FOR UPDATE) for that short transaction, so two replicas
cannot both take it. A holder that dies simply stops renewing, and the lease
passes to the next replica that asks once ``until`` is past."""
from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.base import get_db_session
from db.models import ConnectorState

REPLICA_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def _key(name: str) -> str:
    return f"lease:{name}"


async def acquire(name: str, holder: str, ttl: timedelta) -> bool:
    """Take or renew the lease; False when someone else holds it."""
    now = datetime.utcnow()
    value = {"holder": holder, "until": (now + ttl).isoformat(timespec="seconds")}
    try:
        async with get_db_session() as db:
            row = (await db.execute(select(ConnectorState).where(ConnectorState.key == _key(name)).with_for_update())).scalar_one_or_none()
            if row is None:
                db.add(ConnectorState(key=_key(name), value=value, updated_at=now))
                return True
            v = row.value or {}
            if v.get("holder") not in (None, holder) and datetime.fromisoformat(v["until"]) > now:
                return False
            row.value, row.updated_at = value, now
            return True
    except IntegrityError:  # another replica created the row first
        return False


async def release(name: str, holder: str) -> None:
    """Give the lease up now, if we hold it, so the next replica need not wait for it to expire."""
    async with get_db_session() as db:
        row = (await db.execute(select(ConnectorState).where(ConnectorState.key == _key(name)).with_for_update())).scalar_one_or_none()
        if row is not None and (row.value or {}).get("holder") == holder:
            row.value, row.updated_at = {"holder": None, "until": datetime.utcnow().isoformat(timespec="seconds")}, datetime.utcnow()


async def holder(name: str) -> str | None:
    """Who holds the lease now, or None when it is free or expired."""
    async with get_db_session() as db:
        row = (await db.execute(select(ConnectorState).where(ConnectorState.key == _key(name)))).scalar_one_or_none()
    v = (row.value or {}) if row else {}
    if not v.get("holder") or datetime.fromisoformat(v["until"]) <= datetime.utcnow():
        return None
    return v["holder"]
