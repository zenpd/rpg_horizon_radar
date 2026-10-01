"""Read and write ConnectorState rows (small JSON documents keyed by name):
``live`` for the connectors (pacing, budgets, snapshots, symbol lookups),
``scheduler`` for the scheduler's last runs."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ConnectorState


async def load(db: AsyncSession, key: str) -> dict:
    row = (await db.execute(select(ConnectorState).where(ConnectorState.key == key))).scalar_one_or_none()
    return dict(row.value) if row else {}


async def save(db: AsyncSession, key: str, value: dict) -> None:
    row = (await db.execute(select(ConnectorState).where(ConnectorState.key == key))).scalar_one_or_none()
    if row is None:
        db.add(ConnectorState(key=key, value=value, updated_at=datetime.utcnow()))
    else:
        row.value = dict(value)  # a new object, so SQLAlchemy sees the JSON change
        row.updated_at = datetime.utcnow()
    await db.flush()
