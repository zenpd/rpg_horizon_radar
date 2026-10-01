"""Access rule for every radar request, applied as a router dependency in api/main.py.

The radar's RPG companies are the repo's subsidiaries. A reviewer sees a company
only when it is in their subsidiary scope AND its compliance gate is open — the
same rule as signals (services/visibility.py); a compliance_admin sees all, and
only an admin may use the group-wide "All" view. A company outside the rule
answers 404, so a response never confirms it exists. Every request writes an
audit row (view_radar for reads, radar_change for writes)."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from db.models import Reviewer, Subsidiary
from services import visibility
from services.audit import write_audit

from . import bridge
from .store import COMPANIES_ORDER, STORE

# Endpoints whose company parameter defaults to "All" (radar/api.py: Scope).
GROUP_DEFAULT = ("/home", "/deals", "/follow-ups")


async def allowed_companies(db: AsyncSession, reviewer: Reviewer) -> list[str]:
    subs = (await db.execute(select(Subsidiary))).scalars().all()
    ok = {bridge.CODE_TO_CO[s.code] for s in subs if s.code in bridge.CODE_TO_CO and visibility.subsidiary_visible_to(reviewer, s)}
    return [co for co in COMPANIES_ORDER if co in ok]


async def radar_access(request: Request, reviewer: Reviewer = Depends(get_current_reviewer), db: AsyncSession = Depends(get_db)) -> Reviewer:
    allowed = await allowed_companies(db, reviewer)
    is_admin = reviewer.role == "compliance_admin"
    request.state.radar_allowed = allowed
    request.state.radar_admin = is_admin
    if not allowed:
        raise HTTPException(403, "No RPG company in your scope has an open compliance gate.")

    named: list[str] = []
    for value in (request.query_params.get("company"), request.path_params.get("company")):
        if value:
            named.append(value)
    if request.method == "GET" and "company" not in request.query_params and request.url.path.rstrip("/").endswith(GROUP_DEFAULT):
        named.append("All")  # these screens default to the group-wide view
    if request.method in ("POST", "PATCH", "PUT") and "json" in (request.headers.get("content-type") or ""):
        try:
            body = await request.json()  # cached by Starlette, so the route still reads it
        except ValueError:
            body = None
        if isinstance(body, dict):
            named += [body[k] for k in ("company", "desk") if isinstance(body.get(k), str)]
    for name in named:
        if name == "All":
            if not is_admin and request.method == "GET":
                raise HTTPException(403, "Only a compliance_admin can use the group-wide view.")
        elif name in COMPANIES_ORDER and name not in allowed:
            raise HTTPException(404, f"Unknown company '{name}'.")
    cid = request.path_params.get("case_id")
    if cid and cid in STORE.cases and not set(STORE.cases[cid]["cos"]) & set(allowed):
        raise HTTPException(404, f"No case with id '{cid}'.")

    await bridge.sync(force=False)
    path = request.url.path.removeprefix("/api/v1/radar")
    await write_audit(db, reviewer, "view_radar" if request.method == "GET" else "radar_change", "radar",
                      resource_id=path[:64], detail=f"{request.method} {path}" + (f"?{request.url.query}" if request.url.query else ""))
    return reviewer


def visible(request: Request, companies: list[str] | str | None) -> bool:
    """For list endpoints: does an item that belongs to these companies pass the rule?"""
    if getattr(request.state, "radar_admin", False):
        return True
    allowed = set(getattr(request.state, "radar_allowed", []))
    if companies is None or companies == "All":
        return False
    names = [companies] if isinstance(companies, str) else companies
    return bool(set(names) & allowed)
