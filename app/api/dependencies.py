"""FastAPI dependencies — shared singletons (Redis, DB session, etc.)."""
from __future__ import annotations

from typing import AsyncGenerator

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import get_db_session
from shared.config import get_settings

settings = get_settings()
_redis: Redis | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields an AsyncSession, wrapping db.base.get_db_session
    (commit on success, rollback on exception) for use with ``Depends(get_db)``."""
    async with get_db_session() as session:
        yield session


async def get_redis() -> Redis:
    """FastAPI dependency — returns a singleton Redis connection."""
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis
