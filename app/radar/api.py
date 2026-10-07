"""Radar API, mounted at /api/v1/radar behind the repo's login (radar/access.py records every
request in the activity history). Every user sees every RPG company. Conventions: JSON, long work as 202 + job
polling. Every record comes from the repo's governed pipeline (radar/bridge.py) or from what
reviewers did (store.py); there is no demo data."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agents import acquisition_thesis, competitor_profile, opportunity_analyst, swot_analyst, watchlist_discovery
from agents.llm_azure import AZURE, AzureError
from api.auth import get_current_reviewer
from api.dependencies import get_db
from db.base import get_db_session
from db.models import OpportunityFinding, Reviewer
from ingestion.connectors.live import live_connectors
from services import jobs as repo_jobs
from services import pipeline, scheduler, swot_settings
from services import state as state_store

from . import ask as ask_mod
from . import bridge, rules, views
from .store import COMPANIES_ORDER, STORE, today, week_label

router = APIRouter()


Scope = Query("All", description="An RPG company name, or All for the group view")


def check_scope(scope: str) -> str:
    if scope != "All" and scope not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{scope}'. Use one of: All, {', '.join(COMPANIES_ORDER)}.")
    return scope


def check_company(company: str) -> str:
    if company not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{company}'.")
    return company


def get_case(cid: str) -> dict:
    c = STORE.cases.get(cid)
    if not c:
        raise HTTPException(404, f"No case with id '{cid}'.")
    return c


# ---------- who is asking ----------
@router.get("/me", tags=["reference"])
def me(reviewer: Reviewer = Depends(get_current_reviewer)):
    """Who is signed in, and the RPG companies (every user sees all of them)."""
    return {"name": reviewer.name, "companies": COMPANIES_ORDER}


@router.get("/companies", tags=["reference"])
def companies():
    return [{"name": co, "watching": [r["name"] for r in STORE.rivals.get(co, [])]} for co in COMPANIES_ORDER]


@router.get("/reference", tags=["reference"])
def reference():
    return {"tows": views.TOWS, "sector_labels": rules.SECTOR_LABEL, "metric_labels": rules.METRIC_LABEL}


# ---------- 1. This week ----------
@router.get("/home", tags=["swot"])
def home(company: str = Scope):
    return views.home(check_scope(company))


@router.post("/swot/{company}/rebuild", status_code=202, tags=["swot"])
async def rebuild_swot(company: str, response: Response, research: bool = False,
                       reviewer: Reviewer = Depends(get_current_reviewer)):
    """Start the SWOT Analyst agent for one company. It first researches the company when its research
    is missing or older than a week (or research=true). Poll the returned job; on success /home shows
    the new SWOT."""
    check_company(company)
    await bridge.sync()
    job = swot_analyst.start(company, reviewer.name, research=research or swot_analyst.research_due(company))
    response.headers["Location"] = f"/api/v1/radar/swot-jobs/{job['id']}"
    return job


@router.get("/swot-jobs/{job_id}", tags=["swot"])
def swot_job(job_id: str):
    job = swot_analyst.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"No SWOT job with id '{job_id}'.")
    return job


# ---------- SWOT parameters (services/swot_settings.py) ----------
def _params_out(co: str, p: dict) -> dict:
    return {"company": co, **p}


@router.get("/swot-settings", tags=["swot"])
async def swot_parameters(db: AsyncSession = Depends(get_db)):
    """Every company's SWOT parameters, with the choices on offer."""
    saved = await swot_settings.load_all(db)
    return {"sources": [{"key": k, "label": v} for k, v in swot_settings.SOURCES.items()],
            "factors": [{"key": k, "label": v[0]} for k, v in swot_settings.FACTORS.items()],
            "companies": [_params_out(bridge.CODE_TO_CO[code], p) for code, p in saved.items()]}


class SwotParamsIn(BaseModel):
    sources: list[str]
    factors: list[str]
    sector_queries: list[str] = Field(default_factory=list, max_length=swot_settings.MAX_QUERIES)


@router.put("/swot-settings/{company}", tags=["swot"])
async def save_swot_parameters(company: str, body: SwotParamsIn, reviewer: Reviewer = Depends(get_current_reviewer),
                               db: AsyncSession = Depends(get_db)):
    """Save one company's SWOT parameters. They apply from the next research and SWOT build."""
    check_company(company)
    unknown = [x for x in body.sources if x not in swot_settings.SOURCES] + [x for x in body.factors if x not in swot_settings.FACTORS]
    if unknown:
        raise HTTPException(422, f"Unknown choices: {', '.join(unknown)}.")
    if not set(body.sources) & {"results", "shareholding", "web", "news"}:
        raise HTTPException(422, "Tick at least one source about the company itself (results, shareholding, web pages or news): "
                                 "strengths and weaknesses rest on them.")
    if not body.factors:
        raise HTTPException(422, "Tick at least one analysis factor.")
    saved = await swot_settings.save(db, bridge.CO_TO_CODE[company], body.model_dump())
    await bridge.sync()
    STORE.audit(reviewer.name, "swot_parameters", f"{company}: {len(saved['sources'])} sources, {len(saved['factors'])} factors")
    return _params_out(company, saved)


# ---------- daily opportunities and threats (agents/opportunity_analyst.py) ----------
FINDINGS_DAYS = 7


def _finding(f: OpportunityFinding) -> dict:
    return {"id": f.id, "company": bridge.CODE_TO_CO.get(f.subsidiary_code), "date": f"{f.found_on:%d %b}", "found_on": f.found_on.isoformat(),
            "kind": f.kind, "title": f.title, "summary": f.summary, "swot_ref": f.swot_ref, "swot_text": f.swot_text,
            "effect": f.effect, "action": f.action, "impact": f.impact, "urgency": f.urgency, "sources": f.evidence or [],
            "status": f.status, "model": f.model}


@router.get("/opportunities", tags=["opportunities"])
async def opportunities(company: str = Scope, db: AsyncSession = Depends(get_db)):
    """The last week's findings (dismissed ones left out) for one company, newest first, with its last run;
    for All, the count of new findings per company."""
    check_scope(company)
    since = datetime.utcnow() - timedelta(days=FINDINGS_DAYS)
    state = await state_store.load(db, opportunity_analyst.STATE_KEY)
    if company == "All":
        rows = (await db.execute(select(OpportunityFinding.subsidiary_code, func.count()).where(
            OpportunityFinding.status == "new", OpportunityFinding.found_on >= since).group_by(OpportunityFinding.subsidiary_code))).all()
        counts = {bridge.CODE_TO_CO[c]: n for c, n in rows if c in bridge.CODE_TO_CO}
        return {"company": "All", "counts": {co: counts.get(co, 0) for co in COMPANIES_ORDER}}
    code = bridge.CO_TO_CODE[company]
    rows = (await db.execute(select(OpportunityFinding).where(
        OpportunityFinding.subsidiary_code == code, OpportunityFinding.found_on >= since, OpportunityFinding.status != "dismissed")
        .order_by(OpportunityFinding.found_on.desc(), (OpportunityFinding.impact + OpportunityFinding.urgency).desc()))).scalars().all()
    last = state.get(code) or {}
    return {"company": company, "findings": [_finding(f) for f in rows],
            "last_run": _when(last.get("at")), "news_read": last.get("news"), "errors": last.get("errors", [])}


class FindingIn(BaseModel):
    status: Literal["new", "kept", "dismissed"]


@router.patch("/opportunities/{finding_id}", tags=["opportunities"])
async def decide_finding(finding_id: int, body: FindingIn, reviewer: Reviewer = Depends(get_current_reviewer),
                         db: AsyncSession = Depends(get_db)):
    """Keep (it becomes evidence for the next weekly SWOT) or dismiss a finding."""
    f = await db.get(OpportunityFinding, finding_id)
    if f is None:
        raise HTTPException(404, "No such finding.")
    f.status, f.decided_by_id, f.decided_at = body.status, reviewer.id, datetime.utcnow()
    await db.commit()
    await bridge.sync()
    STORE.audit(reviewer.name, f"finding_{body.status}", f.title)
    return _finding(f)


def _opportunity_job(job: dict) -> dict:
    r = job.get("result") or {}
    return {"id": job["id"], "status": job["status"], "error": job.get("error"),
            "result": None if job["status"] != "completed" else {"findings": r.get("findings", 0), "news": r.get("news", 0), "errors": r.get("errors", [])}}


@router.post("/opportunities/{company}/run", status_code=202, tags=["opportunities"])
async def run_opportunities(company: str, response: Response, reviewer: Reviewer = Depends(get_current_reviewer)):
    """Run the Opportunity Analyst for one company now. Poll the job."""
    check_company(company)

    async def work():
        async with get_db_session() as db:
            res = await opportunity_analyst.analyse(db, bridge.CO_TO_CODE[company])
        STORE.audit(reviewer.name, "opportunities_run", f"{company}: {res['findings']} findings")
        return res
    job = await repo_jobs.start(f"opportunities-{bridge.CO_TO_CODE[company]}", work, started_by=reviewer.name)
    response.headers["Location"] = f"/api/v1/radar/opportunity-jobs/{job['id']}"
    return _opportunity_job(job)


@router.get("/opportunity-jobs/{job_id}", tags=["opportunities"])
async def opportunity_job(job_id: str):
    job = await repo_jobs.get(job_id)
    if not job or not job["kind"].startswith("opportunities-"):
        raise HTTPException(404, f"No opportunity job with id '{job_id}'.")
    return _opportunity_job(job)


# ---------- live data (the repo's governed pipeline) ----------
def _when(iso: str | None) -> str | None:
    from datetime import datetime
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).strftime("%d %b %H:%M")
    except ValueError:
        return iso


@router.get("/signals/status", tags=["live data"])
async def signals_status(db: AsyncSession = Depends(get_db)):
    """Which sources have keys, which real companies each RPG company watches, and the last run."""
    await bridge.sync(force=False)
    live = await state_store.load(db, "live")
    meta = STORE.live_meta
    out = []
    for co in COMPANIES_ORDER:
        watch = [w for w in (meta.get("watch") or {}).get(co, []) if w["status"] != "dismissed"]
        out.append({
            "company": co, "live_signals": len(STORE.live.get(co, [])),
            "companies": [{"name": w["name"], "status": w["status"], "why": w["why"] or "", "sources": w["sources"] or [],
                           "origin": w["origin"], "stock_symbol": w["nse_symbol"], "signals": w["signals"], "found_at": (w["found_at"] or "")[:10] or None}
                          for w in watch]})
    last = live.get("last_run") or {}
    return {"sources": [{"name": c.name, "configured": c.configured} for c in live_connectors(live)],
            "companies": out, "last_refresh": _when(last.get("at")), "errors": last.get("errors", [])}


def _signal_job(job: dict) -> dict:
    r = job.get("result") or {}
    return {"id": job["id"], "status": job["status"], "error": job.get("error"),
            "result": None if job["status"] != "completed" else
            {"companies": r.get("changed_subsidiaries", []), "signals": r.get("new_raw_signals", 0), "errors": r.get("errors", [])}}


def _rival_job(job: dict) -> dict:
    r = job.get("result") or {}
    return {"id": job["id"], "status": job["status"], "error": job.get("error"),
            "result": None if job["status"] != "completed" else
            {"found": r.get("added", []), "targets": r.get("targets", []), "too_big": r.get("too_big", []),
             "companies": r.get("subsidiaries", []), "signals": len(r.get("added", [])), "errors": r.get("errors", [])}}


@router.post("/signals/refresh", status_code=202, tags=["live data"])
async def signals_refresh(response: Response, reviewer: Reviewer = Depends(get_current_reviewer)):
    """Run live ingestion for every watched company now. Poll the job."""
    async def work():
        res = await pipeline.run_ingest(reviewer)
        await repo_jobs.start("theses", scheduler.write_agents_due, started_by=reviewer.name)  # theses and overviews the new signals change
        return res
    job = await repo_jobs.start("ingest", work, started_by=reviewer.name)
    response.headers["Location"] = f"/api/v1/radar/signal-jobs/{job['id']}"
    return _signal_job(job)


@router.post("/rivals/discover", status_code=202, tags=["live data"])
async def rivals_discover(response: Response, reviewer: Reviewer = Depends(get_current_reviewer)):
    """Run discovery now: competitors, then acquisition targets (sized; ones too big to buy are set
    aside). The companies found are watched at once. Poll the job."""
    async def work():
        res = await scheduler.discover_all(reviewer)
        await repo_jobs.start("theses", scheduler.write_agents_due, started_by=reviewer.name)  # the new targets' theses
        return res
    job = await repo_jobs.start("discovery", work, started_by=reviewer.name)
    response.headers["Location"] = f"/api/v1/radar/rival-jobs/{job['id']}"
    return _rival_job(job)


@router.get("/rival-jobs/{job_id}", tags=["live data"])
async def rival_job(job_id: str):
    job = await repo_jobs.get(job_id)
    if not job or job["kind"] != "discovery":
        raise HTTPException(404, f"No rival job with id '{job_id}'.")
    return _rival_job(job)


@router.get("/scheduler", tags=["live data"])
async def scheduler_status():
    """When the watchlist and live signals were last updated, and when they update next."""
    s = await scheduler.status()
    return {"enabled": s["enabled"], "signals_at": s["ingest_daily_at"], "rivals_every_days": s["discovery_every_days"],
            "opportunities_at": s["opportunity_daily_at"], "swot_every_days": s["swot_every_days"],
            "running": s["running"], "last_error": s["last_error"],
            "last": {"rivals": _when(s["last"]["discovery"]), "signals": _when(s["last"]["ingest"]),
                     "opportunities": _when(s["last"]["opportunities"]), "swot": _when(s["last"]["swot"])},
            "next": {"rivals": _when(s["next"]["discovery"]), "signals": _when(s["next"]["ingest"]),
                     "opportunities": _when(s["next"]["opportunities"]), "swot": _when(s["next"]["swot"])}}


@router.get("/signal-jobs/{job_id}", tags=["live data"])
async def signal_job(job_id: str):
    job = await repo_jobs.get(job_id)
    if not job or job["kind"] != "ingest":
        raise HTTPException(404, f"No refresh job with id '{job_id}'.")
    return _signal_job(job)


# ---------- M&A signals ----------
@router.get("/signals", tags=["signals"])
async def signals(company: str = Scope, status: Literal["open", "shortlisted", "dismissed"] = "open", db: AsyncSession = Depends(get_db)):
    """The M&A signal cards for a company (or All) with one status, highest score first, each with its
    thesis headline once one is written; and the count per status."""
    check_scope(company)
    mine = [c for c in STORE.cases.values() if views.in_scope(c, company)
            and (views.acquirable(c, company)["signal"] if company != "All" else views.signal_for(c))]
    out = []
    for c in sorted((c for c in mine if c["status"] == status), key=lambda c: -(c["score"] or 0)):
        co = company if company != "All" else views.signal_for(c)
        t = await acquisition_thesis.load(db, c["id"], co)
        out.append({**views.summary(c), "thesis": {"headline": t["draft"]["headline"], "acquisition_type": t["draft"]["acquisition_type"], "at": t["at"]} if t else None})
    return {"company": company, "status": status, "signals": out,
            "counts": {st: sum(1 for c in mine if c["status"] == st) for st in ("open", "shortlisted", "dismissed")}}


@router.get("/cases/{case_id}", tags=["signals"])
def case_detail(case_id: str):
    return views.case_detail(get_case(case_id))


class StatusIn(BaseModel):
    status: Literal["open", "shortlisted", "dismissed"]


@router.post("/cases/{case_id}/status", tags=["signals"])
def set_status(case_id: str, body: StatusIn, reviewer: Reviewer = Depends(get_current_reviewer)):
    """Shortlist an M&A signal, dismiss it to the archive, or reopen it."""
    get_case(case_id)
    return views.summary(STORE.set_status(case_id, body.status, reviewer.name))


# ---------- acquisition thesis (agents/acquisition_thesis.py) ----------
def _thesis_company(c: dict, company: str | None) -> str:
    co = company or views.signal_for(c) or c["co"]
    if co not in c["cos"]:
        raise HTTPException(404, f"{c['who']} is not watched for {co}.")
    return co


@router.get("/cases/{case_id}/thesis", tags=["signals"])
async def thesis(case_id: str, company: str | None = None, db: AsyncSession = Depends(get_db)):
    """The signal with its acquisition thesis for one RPG company (None until it has been written)."""
    c = get_case(case_id)
    co = _thesis_company(c, company)
    return {"company": co, "signal": views.case_detail(c), "thesis": await acquisition_thesis.load(db, case_id, co),
            "failed": acquisition_thesis.FAILED.get(acquisition_thesis.key(case_id, bridge.CO_TO_CODE[co]))}


def _thesis_job(job: dict) -> dict:
    return {"id": job["id"], "status": job["status"], "error": job.get("error"), "result": None}


@router.post("/cases/{case_id}/thesis", status_code=202, tags=["signals"])
async def write_thesis(case_id: str, response: Response, company: str | None = None, reviewer: Reviewer = Depends(get_current_reviewer)):
    """Have the Acquisition Thesis agent research the company and write (or rewrite) its thesis. Poll the job."""
    c = get_case(case_id)
    co = _thesis_company(c, company)

    async def work():
        async with get_db_session() as db:
            t = await acquisition_thesis.build(db, case_id, co)
        STORE.audit(reviewer.name, "thesis", f"{c['who']} for {co}")
        return {"at": t["at"]}
    job = await repo_jobs.start(f"thesis-{case_id}-{bridge.CO_TO_CODE[co]}", work, started_by=reviewer.name)
    response.headers["Location"] = f"/api/v1/radar/thesis-jobs/{job['id']}"
    return _thesis_job(job)


@router.get("/thesis-jobs/{job_id}", tags=["signals"])
async def thesis_job(job_id: str):
    job = await repo_jobs.get(job_id)
    if not job or not job["kind"].startswith("thesis-"):
        raise HTTPException(404, f"No thesis job with id '{job_id}'.")
    return _thesis_job(job)


# ---------- Explore ----------
@router.get("/competitors", tags=["explore"])
def competitors(company: str = Query(...)):
    return {"company": check_company(company), "rivals": views.roster(company)}


# ---------- competitor overview (agents/competitor_profile.py) ----------
MOVE_GROUPS = [("Deals and ownership", {"Deal", "Fund raise", "Shareholding", "Pledge"}),
               ("Patents", {"Patents"}), ("Hiring and leadership", {"Hiring", "Leadership"}),
               ("Results and filings", {"Earnings", "Filing delay", "Auditor change", "Rating", "Share price", "Legal"})]


def _company_row(entity_id: int, co: str) -> dict:
    row = next((x for x in views.roster(co) if x["entity_id"] == entity_id), None)
    if row is None:
        raise HTTPException(404, f"Company {entity_id} is not on {co}'s watchlist.")
    return row


@router.get("/competitors/{entity_id}/overview", tags=["explore"])
async def competitor_overview(entity_id: int, company: str = Query(...), db: AsyncSession = Depends(get_db)):
    """One watched company: its recent moves grouped by kind, its financial snapshot (stored research),
    and the Competitor Profile agent's analysis (None until written)."""
    co = check_company(company)
    row = _company_row(entity_id, co)
    r = competitor_profile.rival(entity_id, co)
    signals = [views._signal(s) for s in (r["signals"] if r else [])]
    used, moves = set(), []
    for title, labels in MOVE_GROUPS:
        hit = [i for i, s in enumerate(signals) if s["label"] in labels]
        used |= set(hit)
        moves.append({"group": title, "signals": [signals[i] for i in hit]})
    moves.append({"group": "News", "signals": [s for i, s in enumerate(signals) if i not in used]})
    research = await state_store.load(db, acquisition_thesis.research_key(entity_id))
    money = [{"text": f["text"], "source": f["source"], "date": (f.get("observed_at") or "")[:10], "url": f.get("url")}
             for f in research.get("facts") or [] if f["kind"] in ("results", "shareholding")]
    return {"company": co, "rival": row, "moves": moves, "financials": money, "researched_at": research.get("at"),
            "profile": await competitor_profile.load(db, entity_id, co),
            "failed": competitor_profile.FAILED.get(competitor_profile.key(entity_id, bridge.CO_TO_CODE[co]))}


@router.post("/competitors/{entity_id}/overview", status_code=202, tags=["explore"])
async def write_competitor_overview(entity_id: int, response: Response, company: str = Query(...),
                                    reviewer: Reviewer = Depends(get_current_reviewer)):
    """Have the Competitor Profile agent research the company and write (or rewrite) its overview. Poll the job."""
    co = check_company(company)
    _company_row(entity_id, co)

    async def work():
        async with get_db_session() as db:
            await competitor_profile.build(db, entity_id, co)
        STORE.audit(reviewer.name, "competitor_profile", f"{entity_id} for {co}")
        return {}
    job = await repo_jobs.start(f"profile-{entity_id}-{bridge.CO_TO_CODE[co]}", work, started_by=reviewer.name)
    response.headers["Location"] = f"/api/v1/radar/profile-jobs/{job['id']}"
    return _thesis_job(job)


@router.get("/profile-jobs/{job_id}", tags=["explore"])
async def profile_job(job_id: str):
    job = await repo_jobs.get(job_id)
    if not job or not job["kind"].startswith("profile-"):
        raise HTTPException(404, f"No overview job with id '{job_id}'.")
    return _thesis_job(job)


@router.get("/market", tags=["explore"])
async def market(company: str = Query(...), db: AsyncSession = Depends(get_db)):
    """The company's quarterly results, shareholding and share price against its listed watched companies'
    (services/market_data.py)."""
    from services import market_data

    co = check_company(company)
    live = await state_store.load(db, "live")
    return {**market_data.view(co, live, STORE.sizes), "budget": {k: v for k, v in (live.get("budget") or {}).items()
                                                                  if k in ("Fincrux", "Alpha Vantage")}}


@router.post("/market/refresh", status_code=202, tags=["explore"])
async def market_refresh(response: Response, company: str = Query(...), reviewer: Reviewer = Depends(get_current_reviewer)):
    """Fetch the company's and its listed peers' missing or stale prices and results, within the daily
    budgets (Alpha Vantage 25 calls, Fincrux 5). Poll the job."""
    from services import market_data

    co = check_company(company)

    async def work():
        async with get_db_session() as db:
            return await market_data.refresh(db, co)
    job = await repo_jobs.start(f"market-{bridge.CO_TO_CODE[co]}", work, started_by=reviewer.name)
    response.headers["Location"] = f"/api/v1/radar/market-jobs/{job['id']}"
    return {"id": job["id"], "status": job["status"], "error": job.get("error"), "result": job.get("result")}


@router.get("/market-jobs/{job_id}", tags=["explore"])
async def market_job(job_id: str):
    job = await repo_jobs.get(job_id)
    if not job or not job["kind"].startswith("market-"):
        raise HTTPException(404, f"No market job with id '{job_id}'.")
    return {"id": job["id"], "status": job["status"], "error": job.get("error"), "result": job.get("result")}


@router.get("/deals", tags=["explore"])
def deals(company: str = Scope):
    return {"deals": views.deals(check_scope(company))}


class AskIn(BaseModel):
    company: str
    question: str = Field(min_length=1, max_length=500)


@router.get("/ask", tags=["explore"])
def ask_start(company: str = Query(...)):
    return {"suggestions": ask_mod.suggestions(check_company(company))}


@router.post("/ask", tags=["explore"])
def ask(body: AskIn):
    check_company(body.company)
    return {"question": body.question, **ask_mod.answer(body.company, body.question)}


# ---------- Radar settings ----------
@router.get("/theses", tags=["settings"])
def theses():
    """Each saved thesis with its criteria. Matching needs sourced acquisition targets, which the
    radar does not have yet, so no thesis has matches."""
    return [{**th, "criteria": rules.thesis_criteria(th["c"]), "matches": []} for th in STORE.theses]


class ThesisTextIn(BaseModel):
    text: str = Field(min_length=3, max_length=600)


THESIS_SYSTEM = """You turn an M&A acquisition thesis written in plain language into search criteria for the RPG Horizon Radar.
Pick only from the allowed values. sector: the industries the thesis targets. geo: the regions it names (India if none).
rev_min_crore / rev_max_crore: the revenue band in Indian rupee crore; use 0 and 99999 when the thesis gives no band.
own: the ownership types it asks for, or an empty list. Do not guess beyond what the text says."""


def parse_thesis(txt: str) -> tuple[dict, str]:
    """Plain-language thesis -> criteria, by the Azure deployment when reachable, else by rules. The team confirms before saving."""
    if AZURE.available:
        schema = {"type": "object", "additionalProperties": False, "required": ["sector", "geo", "rev_min_crore", "rev_max_crore", "own"],
                  "properties": {"sector": {"type": "array", "items": {"type": "string", "enum": rules.SECTORS}},
                                 "geo": {"type": "array", "items": {"type": "string", "enum": rules.GEOS}},
                                 "rev_min_crore": {"type": "integer"}, "rev_max_crore": {"type": "integer"},
                                 "own": {"type": "array", "items": {"type": "string", "enum": rules.OWNERSHIP}}}}
        try:
            r = AZURE.complete_json(THESIS_SYSTEM, txt, schema, "thesis_criteria", max_tokens=300)
            lo, hi = sorted([max(0, r["rev_min_crore"]), max(0, r["rev_max_crore"])])
            if r["sector"]:
                return {"sector": list(dict.fromkeys(r["sector"])), "geo": list(dict.fromkeys(r["geo"])) or ["India"],
                        "rev": [lo, hi], "own": list(dict.fromkeys(r["own"]))}, AZURE.deployment
        except AzureError:
            pass
    return rules.parse_thesis(txt), "rules"


@router.post("/theses/parse", tags=["settings"])
def thesis_parse(body: ThesisTextIn):
    c, by = parse_thesis(body.text)
    return {"criteria": c, "labels": {"sector": [rules.SECTOR_LABEL[s] for s in c["sector"]]}, "text": rules.thesis_criteria(c), "parsed_by": by}


class ThesisIn(BaseModel):
    desk: str
    text: str = Field(min_length=3, max_length=600)
    c: dict


@router.post("/theses", status_code=201, tags=["settings"])
def thesis_create(body: ThesisIn, reviewer: Reviewer = Depends(get_current_reviewer)):
    if body.desk not in COMPANIES_ORDER:
        raise HTTPException(422, "desk must be an RPG company.")
    if not body.c.get("sector") or any(s not in rules.SECTOR_LABEL for s in body.c["sector"]):
        raise HTTPException(422, f"Pick at least one sector from: {', '.join(rules.SECTORS)}.")
    th = {"id": f"th{max([int(t['id'][2:]) for t in STORE.theses] + [0]) + 1}", "desk": body.desk, "text": body.text, "c": body.c}
    STORE.theses.append(th)
    STORE.audit(reviewer.name, "create_thesis", body.desk)
    return {**th, "criteria": rules.thesis_criteria(th["c"]), "matches": []}


def trig_out(tr: dict) -> dict:
    hits = rules.trigger_hits(tr, views.watched_companies()) if tr["on"] else []
    return {**tr, "text": rules.trigger_text(tr), "hits": [{"case_id": h["case_id"], "name": h["name"], "score": h["score"]} for h in hits]}


@router.get("/triggers", tags=["settings"])
def triggers():
    return [trig_out(t) for t in STORE.triggers]


class TriggerIn(BaseModel):
    desk: str = "All"
    metric: Literal["score"] = "score"
    op: Literal["above", "below"] = "above"
    val: float = Field(default=50, ge=0, le=100)
    company: str = "All"


@router.post("/triggers", status_code=201, tags=["settings"])
def trigger_create(body: TriggerIn, reviewer: Reviewer = Depends(get_current_reviewer)):
    if body.desk != "All" and body.desk not in COMPANIES_ORDER:
        raise HTTPException(422, "desk must be All or an RPG company.")
    tr = {"id": f"tr{max([int(t['id'][2:]) for t in STORE.triggers] + [0]) + 1}", "desk": body.desk, "metric": body.metric,
          "op": body.op, "val": body.val, "on": True}
    STORE.triggers.append(tr)
    STORE.audit(reviewer.name, "create_trigger", rules.trigger_text(tr))
    return trig_out(tr)


class TriggerPatch(BaseModel):
    on: bool


def _get_trigger(trigger_id: str) -> dict:
    tr = next((t for t in STORE.triggers if t["id"] == trigger_id), None)
    if not tr:
        raise HTTPException(404, "No such watch rule.")
    return tr


@router.patch("/triggers/{trigger_id}", tags=["settings"])
def trigger_toggle(trigger_id: str, body: TriggerPatch, reviewer: Reviewer = Depends(get_current_reviewer)):
    tr = _get_trigger(trigger_id)
    tr["on"] = body.on
    STORE.audit(reviewer.name, "toggle_trigger", rules.trigger_text(tr))
    return trig_out(tr)


@router.delete("/triggers/{trigger_id}", status_code=204, tags=["settings"])
def trigger_delete(trigger_id: str, reviewer: Reviewer = Depends(get_current_reviewer)):
    _get_trigger(trigger_id)
    STORE.triggers = [t for t in STORE.triggers if t["id"] != trigger_id]
    STORE.audit(reviewer.name, "delete_trigger", trigger_id)
    return Response(status_code=204)


@router.get("/universe", tags=["settings"])
def universe():
    return [{"company": u[0], "desk": u[1], "added": u[2]} for u in STORE.universe]


class UniverseIn(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    desk: str


@router.post("/universe", status_code=201, tags=["settings"])
def universe_add(body: UniverseIn, reviewer: Reviewer = Depends(get_current_reviewer)):
    if body.desk not in COMPANIES_ORDER:
        raise HTTPException(422, "desk must be an RPG company.")
    added = f"Added by {reviewer.name} on {today()}"
    STORE.universe.insert(0, [body.company, body.desk, added])
    STORE.audit(reviewer.name, "universe_add", body.company)
    return {"company": body.company, "desk": body.desk, "added": added}


@router.get("/activity", tags=["settings"])
def activity():
    """The radar's own activity feed (every request is in Admin -> Activity)."""
    return [{"time": a[0], "who": a[1], "action": a[2], "detail": a[3]} for a in STORE.activity[:40]]


@router.get("/health", tags=["reference"])
def health(x_request_id: str | None = Header(default=None)):
    return {"status": "ok", "request_id": x_request_id}
