"""Applied to every radar request as a router dependency in api/main.py: the user must be
signed in, the radar reloads its data from the database when it is stale, and the request is
recorded in the activity history (view_radar for reads, radar_change for writes). Every user
sees every RPG company; there are no roles or scopes."""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from db.models import Reviewer
from services.audit import write_audit

from . import bridge


async def radar_access(request: Request, reviewer: Reviewer = Depends(get_current_reviewer), db: AsyncSession = Depends(get_db)) -> Reviewer:
    await bridge.sync(force=False)
    path = request.url.path.removeprefix("/api/v1/radar")
    await write_audit(db, reviewer, "view_radar" if request.method == "GET" else "radar_change", "radar",
                      resource_id=path[:64], detail=f"{request.method} {path}" + (f"?{request.url.query}" if request.url.query else ""))
    return reviewer
