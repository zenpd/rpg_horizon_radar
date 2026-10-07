"""Connects the radar screens (the in-memory STORE) to the repo's data.

- Watched companies: for each RPG company, the ``watching`` companies routed to
  it by sector, each with its recent raw_signals and its rule-based opportunity
  score, become STORE.rivals[company]; their signals together, newest first, are
  STORE.live[company]. Each one with signals is a case on the radar (store.py).
  Nothing is fetched here — ingestion (services/ingest.py) already ran.
- Watchlist: every real company watched for a company, with discovery's
  reasons and sources, for the radar's Watched companies screen.
- Research on the RPG companies themselves (services/company_research.py),
  the SWOT Analyst's evidence for strengths and weaknesses: STORE.research.
- SWOT parameters per company (services/swot_settings.py) and the daily findings users
  kept in the last week (opportunity_findings): STORE.swot_settings, STORE.kept_findings.
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
from db.models import Entity, OpportunityFinding, OpportunityScore, RawSignal, SignalCluster, Subsidiary, SwotBrief
from services import company_research, company_size, routing, swot_settings
from shared.logger import get_logger

from .store import COMPANIES_ORDER, STORE

log = get_logger("radar.bridge")

# Subsidiary code (repo) <-> company name (radar screens)
CODE_TO_CO = {"CEAT": "CEAT", "KEC": "KEC", "ZENSAR": "Zensar", "RPGLS": "RPG Life Sciences",
              "RAYCHEM": "Raychem RPG", "HARRISONS": "Harrisons"}
CO_TO_CODE = {v: k for k, v in CODE_TO_CO.items()}
assert set(CO_TO_CODE) == set(COMPANIES_ORDER)

WINDOW_DAYS = 120
KEPT_DAYS = 7  # kept daily findings feed the weekly SWOT for this long
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
    return {"date": f"{s.observed_at.day:02d} {s.observed_at:%b}", "company": name, "entity_id": s.entity_id,
            "label": LABEL.get(s.signal_type, "Signal"), "text": text, "source": source, "url": s.source_url or None,
            "kind": s.source_type, "provider": s.provider, "signal_type": s.signal_type,
            "observed_at": s.observed_at.isoformat(timespec="seconds")}


async def sync(force: bool = True) -> None:
    global _last_sync
    if not force and time.monotonic() - _last_sync < SYNC_EVERY:
        return
    async with _lock:
        async with get_db_session() as db:
            subs = (await db.execute(select(Subsidiary))).scalars().all()
            real = (await db.execute(select(Entity))).scalars().all()
            since = datetime.utcnow() - timedelta(days=WINDOW_DAYS)
            watching_ids = [e.id for e in real if e.status == "watching"]
            rows = (await db.execute(select(RawSignal).where(RawSignal.entity_id.in_(watching_ids), RawSignal.observed_at >= since)
                                     .order_by(RawSignal.observed_at.desc()))).scalars().all() if watching_ids else []
            scores = {eid: sc for eid, sc in (await db.execute(select(SignalCluster.entity_id, OpportunityScore)
                                                                .join(OpportunityScore, OpportunityScore.cluster_id == SignalCluster.id))).all()}
            counts = dict((await db.execute(select(RawSignal.entity_id, func.count()).group_by(RawSignal.entity_id))).all())
            research = await company_research.load_all(db)
            params = await swot_settings.load_all(db)
            sizes = await company_size.load_all(db)
            kept = (await db.execute(select(OpportunityFinding).where(
                OpportunityFinding.status == "kept", OpportunityFinding.found_on >= datetime.utcnow() - timedelta(days=KEPT_DAYS))
                .order_by(OpportunityFinding.found_on.desc()))).scalars().all()
        by_entity: dict[int, list[RawSignal]] = {}
        for s in rows:
            by_entity.setdefault(s.entity_id, []).append(s)
        rivals, watch, primary = {}, {}, {}
        for sub in subs:
            co = CODE_TO_CO.get(sub.code)
            if co is None:
                continue
            mine = [e for e in real if routing.matching_subsidiaries(e, [sub])]
            watch[co] = [{"id": e.id, "name": e.name, "status": e.status, "role": e.role, "origin": e.origin, "nse_symbol": e.nse_symbol,
                          "why": (e.discovery or {}).get("why"), "sources": (e.discovery or {}).get("sources", []),
                          "found_at": (e.discovery or {}).get("found_at"), "signals": counts.get(e.id, 0),
                          "score": scores[e.id].score if e.id in scores else None} for e in mine]
            watched = [e for e in mine if e.status == "watching" and by_entity.get(e.id)]
            rivals[co] = sorted(({"id": e.id, "name": e.name, "role": e.role,
                                  "score": scores[e.id].score if e.id in scores else None,
                                  "rationale": scores[e.id].rationale if e.id in scores else None,
                                  "types": list(scores[e.id].signal_types_json or []) if e.id in scores else [],
                                  "watched_since": e.watched_since.isoformat(timespec="seconds") if e.watched_since else None,
                                  "signals": [_signal(s, e.name) for s in by_entity[e.id][:MAX_LIVE]]} for e in watched),
                                key=lambda r: (-len(r["signals"]), -(r["score"] or 0)))
            if rivals[co]:
                primary[co] = rivals[co][0]["name"]
        STORE.set_rivals({co: rivals.get(co, []) for co in COMPANIES_ORDER})
        STORE.research = {CODE_TO_CO[code]: r for code, r in research.items() if code in CODE_TO_CO}
        STORE.swot_settings = {CODE_TO_CO[code]: p for code, p in params.items() if code in CODE_TO_CO}
        STORE.sizes = sizes
        STORE.kept_findings = {co: [] for co in COMPANIES_ORDER}
        for f in kept:
            if f.subsidiary_code in CODE_TO_CO:
                first = (f.evidence or [{}])[0]
                STORE.kept_findings[CODE_TO_CO[f.subsidiary_code]].append(
                    {"kind": f.kind, "title": f.title, "summary": f.summary, "date": f"{f.found_on:%d %b %Y}",
                     "source": first.get("source") or "news", "url": first.get("url")})
        STORE.live_meta.update(watch=watch, primary=primary, synced_at=datetime.now().isoformat(timespec="seconds"))
        _last_sync = time.monotonic()


async def load_agent_swots() -> None:
    """The newest agent SWOT per company, back into the store."""
    async with get_db_session() as db:
        rows = (await db.execute(select(SwotBrief).order_by(SwotBrief.generated_at))).scalars().all()
    for r in rows:  # oldest first, so the newest wins
        co = CODE_TO_CO.get(r.subsidiary_code)
        if co and isinstance(r.content, dict) and "swot" in r.content:
            STORE.use_agent_swot(co, r.content)


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


async def research_now(co: str) -> dict:
    """Research one RPG company now (services/company_research.py) and reload the radar."""
    async with get_db_session() as db:
        saved = await company_research.refresh(db, CO_TO_CODE[co])
    await sync()
    return saved


def run_on_loop(coro, timeout: float = 600):
    """From a worker thread (the SWOT Analyst's job): run a coroutine on the API's event loop."""
    if LOOP is None:
        raise RuntimeError("The radar has not started.")
    return asyncio.run_coroutine_threadsafe(coro, LOOP).result(timeout)


async def startup() -> None:
    global LOOP
    LOOP = asyncio.get_running_loop()
    STORE.on_agent_swot = persist_swot
    await load_agent_swots()
    # What reviewers did (escalations, decisions, plans, theses, watch rules, universe
    # additions, activity) survives a restart (radar/persistence.py). Before sync(), so the
    # cases it builds pick up their saved stage, owner and plan.
    STORE.apply_persisted()
    await sync()
