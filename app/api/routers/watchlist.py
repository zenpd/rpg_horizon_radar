"""The watchlist of real companies: what discovery found, manual additions,
removals, and the live-source status. Any signed-in user can change it; every
change is recorded in the activity history. A company is ingested while
``watching``; a ``dismissed`` one is not, and discovery never re-adds it —
see services/ingest.py."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents import watchlist_discovery
from agents.llm_routes import routes_from_settings
from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.schemas.ingest import JobOut
from api.schemas.watchlist import ConnectorStatus, SourcesStatus, WatchlistCreate, WatchlistEntity, WatchlistUpdate
from db.base import get_db_session
from db.models import Entity, RawSignal, Reviewer, SignalCluster, Subsidiary
from ingestion.connectors.live import live_connectors
from radar import bridge as radar_bridge
from services import jobs, scheduler
from services import state as state_store
from services.audit import write_audit

router = APIRouter()


async def _out(db: AsyncSession, entities: list[Entity]) -> list[WatchlistEntity]:
    counts = dict((await db.execute(select(RawSignal.entity_id, func.count()).group_by(RawSignal.entity_id))).all())
    clusters = {c.entity_id: c for c in (await db.execute(select(SignalCluster))).scalars().all()}
    out = []
    for e in entities:
        c = clusters.get(e.id)
        out.append(WatchlistEntity(
            id=e.id, name=e.name, sectors=e.sectors or [], category=e.category, origin=e.origin, status=e.status, query_name=e.query_name, nse_symbol=e.nse_symbol, discovery=e.discovery,
            watched_since=e.watched_since, raw_signal_count=counts.get(e.id, 0),
            score=c.opportunity_score.score if c is not None and c.opportunity_score else None))
    return out


@router.get("", response_model=list[WatchlistEntity])
async def list_watchlist(user: Reviewer = Depends(get_current_reviewer), db: AsyncSession = Depends(get_db)):
    entities = (await db.execute(select(Entity).order_by(Entity.status, Entity.name))).scalars().all()
    return await _out(db, entities)


@router.post("", response_model=WatchlistEntity, status_code=201)
async def add_company(payload: WatchlistCreate, user: Reviewer = Depends(get_current_reviewer),
                      db: AsyncSession = Depends(get_db)):
    """Add a real company by hand. It is watched from the next ingestion run."""
    known = {s for sub in (await db.execute(select(Subsidiary))).scalars().all() for s in sub.sectors or []}
    unknown = [s for s in payload.sectors if s not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown sectors: {', '.join(unknown)}")
    name = payload.name.strip()
    if (await db.execute(select(Entity).where(func.lower(Entity.name) == name.lower()))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"{name} is already on the watchlist")
    e = Entity(name=name, sectors=payload.sectors, category=payload.category, origin="manual",
               status="watching", query_name=payload.query_name.strip(), nse_symbol=(payload.nse_symbol or "").strip().upper() or None,
               watched_since=datetime.utcnow())
    db.add(e)
    await db.commit()
    await write_audit(db, user, "watchlist_change", "entity", resource_id=e.id, detail=f"watchlist_add name={name} sectors={','.join(payload.sectors)}")
    await radar_bridge.sync()
    return (await _out(db, [e]))[0]


@router.patch("/{entity_id}", response_model=WatchlistEntity)
async def update_company(entity_id: int, payload: WatchlistUpdate, user: Reviewer = Depends(get_current_reviewer),
                         db: AsyncSession = Depends(get_db)):
    e = (await db.execute(select(Entity).where(Entity.id == entity_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    changes = []
    if payload.status and payload.status != e.status:
        changes.append(f"status {e.status}->{payload.status}")
        e.status = payload.status
        if payload.status == "watching":
            e.watched_since = datetime.utcnow()
    if payload.nse_symbol is not None and payload.nse_symbol.strip().upper() != (e.nse_symbol or ""):
        e.nse_symbol = payload.nse_symbol.strip().upper() or None
        changes.append(f"nse_symbol={e.nse_symbol}")
    if payload.query_name is not None and payload.query_name.strip() != e.query_name:
        e.query_name = payload.query_name.strip()
        changes.append(f"query_name={e.query_name}")
    await db.commit()
    if changes:
        await write_audit(db, user, "watchlist_change", "entity", resource_id=e.id, detail=f"watchlist {e.name}: " + "; ".join(changes))
        await radar_bridge.sync()
    return (await _out(db, [e]))[0]


@router.post("/discover", response_model=JobOut, status_code=202)
async def discover(user: Reviewer = Depends(get_current_reviewer)):
    async def work():
        async with get_db_session() as db:
            res = await watchlist_discovery.discover(db, user)
        await radar_bridge.sync()
        return res
    return await jobs.start("discovery", work, started_by=user.name)


@router.get("/sources", response_model=SourcesStatus)
async def sources_status(user: Reviewer = Depends(get_current_reviewer), db: AsyncSession = Depends(get_db)):
    live = await state_store.load(db, "live")
    out = []
    for c in live_connectors(live):
        pulls = (live.get("pulled") or {}).get(c.name) or {}
        out.append(ConnectorStatus(name=c.name, source_type=c.source_type, configured=c.configured, min_days=c.min_days,
                                   entities_pulled=len(pulls), last_pull=max((p["at"] for p in pulls.values()), default=None),
                                   budget=(live.get("budget") or {}).get(c.name)))
    try:
        routes = [r.name for r in routes_from_settings()]
    except Exception as e:  # a bad LLM_ROUTES value should show, not break the page
        routes = [f"invalid LLM_ROUTES: {e}"]
    return SourcesStatus(connectors=out, llm_routes=routes, last_run=live.get("last_run"), scheduler=await scheduler.status())
