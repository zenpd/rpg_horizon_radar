"""Connects the radar screens (the in-memory STORE) to the repo's governed data.

- Live signals: for each RPG company whose compliance gate is open, the approved
  (``watching``) real companies routed to it by sector are its watched rivals.
  The one with the most recent signals is the primary rival; its raw_signals
  become STORE.live[company], which replaces the demo rival story in the SWOT
  evidence (evidence.py). Nothing is fetched here — ingestion (services/ingest.py)
  already ran only for approved companies in open sectors.
- Watchlist: every real company proposed or watched for a company, with
  discovery's reasons and sources, for the radar's Watched companies screen.
- Agent SWOTs: kept in the swot_briefs table (one row per rebuild) and loaded
  back into the store at startup.

sync() runs at startup, after every ingestion run, after a watchlist change, and
at most every SYNC_EVERY seconds on radar requests."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import func, select

from db.base import get_db_session
from db.models import Entity, OpportunityScore, RawSignal, SignalCluster, Subsidiary, SwotBrief
from services import routing
from shared.logger import get_logger

from .store import COMPANIES_ORDER, STORE

log = get_logger("radar.bridge")

# Subsidiary code (repo) <-> company name (radar screens)
CODE_TO_CO = {"CEAT": "CEAT", "KEC": "KEC", "ZENSAR": "Zensar", "RPGLS": "RPG Life Sciences",
              "RAYCHEM": "Raychem RPG", "HARRISONS": "Harrisons"}
CO_TO_CODE = {v: k for k, v in CODE_TO_CO.items()}
assert set(CO_TO_CODE) == set(COMPANIES_ORDER)

WINDOW_DAYS = 120
MAX_LIVE = 40
SYNC_EVERY = 300  # seconds
NEWS_PROVIDERS = {"GNews", "NewsData.io", "Tavily", "YouTube"}
LABEL = {"leadership_churn": "Leadership", "delayed_filing": "Filing delay", "credit_downgrade": "Rating",
         "patent_shift": "Patents", "hiring_scaledown": "Hiring", "hiring_scaleup": "Hiring", "press_distress": "News",
         "press_opportunity": "News", "promoter_pledge": "Pledge", "auditor_change": "Auditor change",
         "legal_action": "Legal", "earnings_decline": "Earnings", "stake_selldown": "Shareholding",
         "share_price_slump": "Share price", "deal_activity": "Deal", "fund_raise": "Fund raise"}

LOOP: asyncio.AbstractEventLoop | None = None
_last_sync = 0.0
_lock = asyncio.Lock()


def _signal(s: RawSignal, name: str) -> dict:
    text = s.headline
    for prefix in (f"{name}: ", f"{name} "):
        if text.startswith(prefix):
            text = text[len(prefix):]
            text = text[:1].upper() + text[1:]
            break
    if s.provider in NEWS_PROVIDERS:
        source = s.source_excerpt or s.provider
    else:
        source = s.provider
        if s.source_excerpt:
            extra = s.source_excerpt if len(s.source_excerpt) <= 220 else s.source_excerpt[:217].rsplit(" ", 1)[0] + "..."
            text = f"{text}. {extra}" if not text.endswith(".") else f"{text} {extra}"
    return {"date": f"{s.observed_at.day:02d} {s.observed_at:%b}", "company": name, "label": LABEL.get(s.signal_type, "Signal"),
            "text": text, "source": source, "url": s.source_url or None, "kind": s.source_type, "provider": s.provider,
            "signal_type": s.signal_type, "observed_at": s.observed_at.isoformat(timespec="seconds")}


async def sync(force: bool = True) -> None:
    global _last_sync
    if not force and time.monotonic() - _last_sync < SYNC_EVERY:
        return
    async with _lock:
        async with get_db_session() as db:
            subs = (await db.execute(select(Subsidiary))).scalars().all()
            real = (await db.execute(select(Entity).where(Entity.is_fictional.is_(False)))).scalars().all()
            since = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
            watching_ids = [e.id for e in real if e.status == "watching"]
            rows = (await db.execute(select(RawSignal).where(RawSignal.entity_id.in_(watching_ids), RawSignal.observed_at >= since)
                                     .order_by(RawSignal.observed_at.desc()))).scalars().all() if watching_ids else []
            scores = dict((await db.execute(select(SignalCluster.entity_id, OpportunityScore.score)
                                            .join(OpportunityScore, OpportunityScore.cluster_id == SignalCluster.id))).all())
            counts = dict((await db.execute(select(RawSignal.entity_id, func.count()).group_by(RawSignal.entity_id))).all())
        by_entity: dict[int, list[RawSignal]] = {}
        for s in rows:
            by_entity.setdefault(s.entity_id, []).append(s)
        live, watch, primary = {}, {}, {}
        for sub in subs:
            co = CODE_TO_CO.get(sub.code)
            if co is None:
                continue
            mine = [e for e in real if routing.matching_subsidiaries(e, [sub])]
            watch[co] = [{"id": e.id, "name": e.name, "status": e.status, "origin": e.origin, "nse_symbol": e.nse_symbol,
                          "why": (e.discovery or {}).get("why"), "sources": (e.discovery or {}).get("sources", []),
                          "found_at": (e.discovery or {}).get("found_at"), "signals": counts.get(e.id, 0),
                          "score": scores.get(e.id)} for e in mine]
            watched = [e for e in mine if e.status == "watching" and by_entity.get(e.id)] if sub.compliance_gate else []
            if not watched:
                live[co] = []
                continue
            top = max(watched, key=lambda e: (len(by_entity[e.id]), scores.get(e.id) or 0))
            primary[co] = top.name
            live[co] = [_signal(s, top.name) for s in by_entity[top.id][:MAX_LIVE]]
        STORE.live = {co: live.get(co, []) for co in COMPANIES_ORDER}
        STORE.live_meta.update(watch=watch, primary=primary, gates={CODE_TO_CO[s.code]: s.compliance_gate for s in subs if s.code in CODE_TO_CO},
                               synced_at=datetime.now().isoformat(timespec="seconds"))
        _last_sync = time.monotonic()


async def load_agent_swots() -> None:
    """The newest agent SWOT per company, back into the store."""
    async with get_db_session() as db:
        rows = (
            await db.execute(select(SwotBrief).where(SwotBrief.kind == "baseline").order_by(SwotBrief.generated_at))
        ).scalars().all()
    for r in rows:  # oldest first, so the newest wins
        co = CODE_TO_CO.get(r.subsidiary_code)
        if co and isinstance(r.content, dict) and "swot" in r.content:
            STORE.agent_saved[co] = r.content
    # Not persisted: this runs on every boot just to fold in agent SWOTs, before
    # startup() applies the one real persisted snapshot (see below).
    STORE.reset(keep_agent_swots=True, persist=False)


async def load_post_acquisitions() -> None:
    """Every post-acquisition SWOT projection ever saved (radar/post_acquisition.py, written at
    radar/api.py:decide()'s approve step), back into the store — so an approved deal's projection
    survives a restart just like a baseline SWOT does."""
    async with get_db_session() as db:
        rows = (
            await db.execute(select(SwotBrief).where(SwotBrief.kind == "post_acquisition").order_by(SwotBrief.generated_at))
        ).scalars().all()
    for r in rows:  # oldest first, so the newest wins per (company, case_id)
        co = CODE_TO_CO.get(r.subsidiary_code)
        if co and r.case_id and isinstance(r.content, dict):
            STORE.post_acq_swot[(co, r.case_id)] = r.content


async def _save_swot(co: str, payload: dict) -> None:
    src = payload.get("source") or {}
    async with get_db_session() as db:
        db.add(SwotBrief(subsidiary_code=CO_TO_CODE[co], generated_at=datetime.utcnow(), model=src.get("model") or "",
                         rounds=src.get("rounds") or 1, content=payload, evidence=[]))
        await db.commit()


def persist_swot(co: str, payload: dict) -> None:
    """Called from the agent's worker thread: hand the write to the API's event loop."""
    if LOOP is None:
        log.warning("radar_swot_not_persisted", company=co)
        return
    fut = asyncio.run_coroutine_threadsafe(_save_swot(co, payload), LOOP)
    fut.add_done_callback(lambda f: f.exception() and log.error("radar_swot_persist_failed", company=co, error=str(f.exception())))


async def startup() -> None:
    global LOOP
    LOOP = asyncio.get_running_loop()
    STORE.on_agent_swot = persist_swot
    await load_agent_swots()
    await load_post_acquisitions()
    # The one real restore: whatever a reviewer actually did (escalations, decisions, plans,
    # theses, watch rules, universe additions, activity) survives a restart from here on
    # (radar/persistence.py). Last, so load_agent_swots()'s own reset() above can't undo it.
    STORE._apply_persisted()
    await sync()
