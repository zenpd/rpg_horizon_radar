"""Radar API, mounted at /api/v1/radar behind the repo's reviewer login (radar/access.py checks
scope and writes the audit row for every request). Conventions: JSON, long work as 202 + job
polling. Live data comes from the repo's governed pipeline (radar/bridge.py); the deal targets,
rival placeholders and decisions are the prototype's in-memory demo state (store.py)."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from db.base import get_db_session
from db.models import Reviewer
from ingestion.connectors.live import live_connectors
from services import discovery as discovery_svc
from services import jobs as repo_jobs
from services import pipeline, scheduler
from services import state as state_store

from . import ask as ask_mod
from . import bridge, rules, swot_agent, views
from .access import visible
from .llm_azure import AZURE, AzureError
from .market import market_view
from .reference import REF
from .store import COMPANIES_ORDER, STORE, TODAY

router = APIRouter()


def admin_only(reviewer: Reviewer = Depends(get_current_reviewer)) -> Reviewer:
    if reviewer.role != "compliance_admin":
        raise HTTPException(403, "Requires role 'compliance_admin'")
    return reviewer
Scope = Query("All", description="An RPG company name, or All for the group view")


def user_of(scope: str | None) -> str:
    if not scope or scope == "All":
        return "group.strategy"
    return "strategy." + scope.lower().split(" ")[0]


def check_scope(scope: str) -> str:
    if scope != "All" and scope not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{scope}'. Use one of: All, {', '.join(COMPANIES_ORDER)}.")
    return scope


def get_case(cid: str) -> dict:
    c = STORE.cases.get(cid)
    if not c:
        raise HTTPException(404, f"No case with id '{cid}'.")
    return c


# ---------- who is asking ----------
@router.get("/me", tags=["reference"])
def me(request: Request, reviewer: Reviewer = Depends(get_current_reviewer)):
    """The RPG companies this reviewer may open (scope + open compliance gate); All only for admins."""
    return {"name": reviewer.name, "role": reviewer.role, "companies": request.state.radar_allowed,
            "group_view": request.state.radar_admin}


# ---------- reference ----------
@router.get("/companies", tags=["reference"])
def companies():
    return [{"name": co, "rival": STORE.companies[co]["rival"], "segment": STORE.companies[co]["seg"]} for co in COMPANIES_ORDER]


@router.get("/reference", tags=["reference"])
def reference():
    return {"weights": REF["W"], "type_labels": REF["TYPE_LABEL"], "tows": REF["TOWS"], "sector_labels": REF["SECTOR_LABEL"],
            "rating_order": REF["RATING_ORDER"], "metric_labels": REF["METRIC_LABEL"], "deep_dive_steps": {"deal": REF["DD_DEAL"], "threat": REF["DD_THREAT"]}}


# ---------- 1. SWOT home ----------
@router.get("/home", tags=["swot"])
def home(company: str = Scope):
    STORE.settle_jobs()
    return views.home(check_scope(company))


@router.post("/swot/{company}/rebuild", status_code=202, tags=["swot"])
async def rebuild_swot(company: str, response: Response, admin: Reviewer = Depends(admin_only)):
    """Start the SWOT Analyst agent for one company. Poll the returned job; on success /home shows the new SWOT."""
    if company not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{company}'. Use one of: {', '.join(COMPANIES_ORDER)}.")
    await bridge.sync()  # the latest approved companies' signals
    job = swot_agent.start(company, admin.name)
    response.headers["Location"] = f"/api/v1/radar/swot-jobs/{job['id']}"
    return job


@router.get("/swot-jobs/{job_id}", tags=["swot"])
def swot_job(job_id: str):
    job = swot_agent.JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"No SWOT job with id '{job_id}'.")
    return job


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
    """Which sources have keys, which approved real companies each RPG company watches, and the last run."""
    await bridge.sync(force=False)
    live = await state_store.load(db, "live")
    meta = STORE.live_meta
    companies = []
    for co in COMPANIES_ORDER:
        watch = [w for w in (meta.get("watch") or {}).get(co, []) if w["status"] != "dismissed"]
        primary = (meta.get("primary") or {}).get(co) or next((w["name"] for w in watch if w["status"] == "watching"), None)
        first = next((w for w in watch if w["name"] == primary), None)
        companies.append({
            "company": co, "rival_placeholder": STORE.companies[co]["rival"], "real_name": primary,
            "rival_source": None if not first else ("manual" if first["origin"] == "manual" else "auto"),
            "stock_symbol": first["nse_symbol"] if first else None,
            "rivals_found": [{"name": w["name"], "why": w["why"] or "", "sources": w["sources"] or [], "status": w["status"]} for w in watch],
            "rivals_found_at": ((first or {}).get("found_at") or "")[:10] or None,
            "live_signals": len(STORE.live.get(co, [])), "gate_open": (meta.get("gates") or {}).get(co, False)})
    last = live.get("last_run") or {}
    return {"sources": [{"name": c.name, "configured": c.configured} for c in live_connectors(live)],
            "companies": companies, "last_refresh": _when(last.get("at")), "errors": last.get("errors", [])}


def _signal_job(job: dict) -> dict:
    r = job.get("result") or {}
    return {"id": job["id"], "status": job["status"], "error": job.get("error"),
            "result": None if job["status"] != "completed" else
            {"companies": r.get("changed_subsidiaries", []), "signals": r.get("new_raw_signals", 0), "errors": r.get("errors", [])}}


def _rival_job(job: dict) -> dict:
    r = job.get("result") or {}
    return {"id": job["id"], "status": job["status"], "error": job.get("error"),
            "result": None if job["status"] != "completed" else
            {"found": r.get("proposed", []), "companies": r.get("subsidiaries", []), "signals": len(r.get("proposed", [])), "errors": r.get("errors", [])}}


@router.post("/signals/refresh", status_code=202, tags=["live data"])
async def signals_refresh(response: Response, admin: Reviewer = Depends(admin_only)):
    """Run live ingestion for approved companies in gate-open sectors now. Poll the job."""
    job = repo_jobs.start("ingest", lambda: pipeline.run_ingest(admin), started_by=admin.name)
    response.headers["Location"] = f"/api/v1/radar/signal-jobs/{job['id']}"
    return _signal_job(job)


@router.post("/rivals/discover", status_code=202, tags=["live data"])
async def rivals_discover(response: Response, admin: Reviewer = Depends(admin_only)):
    """Run watchlist discovery now. It only proposes companies; a compliance_admin approves them
    in Admin -> Watchlist. Poll the job."""
    async def work():
        async with get_db_session() as db:
            res = await discovery_svc.discover(db, admin)
        await bridge.sync()
        return res
    job = repo_jobs.start("discovery", work, started_by=admin.name)
    response.headers["Location"] = f"/api/v1/radar/rival-jobs/{job['id']}"
    return _rival_job(job)


@router.get("/rival-jobs/{job_id}", tags=["live data"])
def rival_job(job_id: str):
    job = repo_jobs.get(job_id)
    if not job or job["kind"] != "discovery":
        raise HTTPException(404, f"No rival job with id '{job_id}'.")
    return _rival_job(job)


@router.get("/scheduler", tags=["live data"])
async def scheduler_status():
    """When the watchlist and live signals were last updated, and when they update next."""
    s = await scheduler.status()
    return {"enabled": s["enabled"], "signals_at": s["ingest_daily_at"], "rivals_every_days": s["discovery_every_days"],
            "auto_rebuild": s["auto_swot"], "running": s["running"], "last_error": s["last_error"],
            "last": {"rivals": _when(s["last"]["discovery"]), "signals": _when(s["last"]["ingest"])},
            "next": {"rivals": _when(s["next"]["discovery"]), "signals": _when(s["next"]["ingest"])}}


@router.get("/signal-jobs/{job_id}", tags=["live data"])
def signal_job(job_id: str):
    job = repo_jobs.get(job_id)
    if not job or job["kind"] != "ingest":
        raise HTTPException(404, f"No refresh job with id '{job_id}'.")
    return _signal_job(job)


# ---------- 3. Deep dive jobs ----------
class DeepDiveIn(BaseModel):
    case_ids: list[str] = Field(min_length=1, max_length=5)
    company: str = "All"


@router.post("/deep-dives", status_code=202, tags=["deep dive"])
def start_deep_dive(body: DeepDiveIn, response: Response):
    for cid in body.case_ids:
        if get_case(cid)["stage"] != "digest":
            raise HTTPException(409, f"'{cid}' has already been escalated.")
    job = STORE.start_job(body.case_ids, user_of(body.company))
    response.headers["Location"] = f"/api/v1/radar/deep-dives/{job['id']}"
    return job


@router.get("/deep-dives/{job_id}", tags=["deep dive"])
def deep_dive(job_id: str):
    if job_id not in STORE.jobs:
        raise HTTPException(404, f"No deep-dive job '{job_id}'.")
    return STORE.job_status(job_id)


# ---------- 4. Book ----------
@router.get("/book", tags=["book"])
def book(request: Request):
    STORE.settle_jobs()
    pages = []
    for cid in STORE.book_order:
        c = STORE.cases[cid]
        if not visible(request, c["cos"]):
            continue
        pages.append({**views.summary(c), "recommendation": views.overview(c)["recommendation"]["title"]})
    return {"week": "Week 40", "written": TODAY, "pages": pages}


@router.get("/cases/{case_id}/overview", tags=["book"])
def case_overview(case_id: str):
    c = get_case(case_id)
    if not c["ov_date"]:
        raise HTTPException(409, "This case has no detailed overview yet. Escalate it for a deep dive first.")
    return views.overview(c)


class DecisionIn(BaseModel):
    action: Literal["approve", "park", "reject"]
    owner: str | None = None
    company: str = "All"


@router.post("/cases/{case_id}/decision", tags=["book"])
def decide(case_id: str, body: DecisionIn):
    c = get_case(case_id)
    if c["stage"] != "decide":
        raise HTTPException(409, "Only a case waiting for a decision can be decided.")
    u = user_of(body.company)
    if body.action == "approve":
        if not body.owner:
            raise HTTPException(422, "Approving needs an owner.")
        c.update(owner=body.owner, approved=TODAY, stage="act")
        c["plan"] = [{**p, "done": False} for p in rules.plan_for(c)]
        STORE.audit(u, "approve", f'{STORE.who(c)} · owner {body.owner}')
    elif body.action == "park":
        c.update(stage="closed", outcome="Parked for 90 days")
        STORE.audit(u, "park", STORE.who(c))
    else:
        c.update(stage="closed", outcome="Rejected")
        STORE.audit(u, "reject", STORE.who(c))
    return views.summary(c)


# ---------- 5. Follow-up ----------
@router.get("/follow-ups", tags=["follow-up"])
def follow_ups(company: str = Scope):
    check_scope(company)
    return [views.follow_up(c) for c in STORE.cases.values() if c["owner"] and views.in_scope(c, company)]


class PlanStepIn(BaseModel):
    done: bool
    company: str = "All"


@router.patch("/cases/{case_id}/plan/{index}", tags=["follow-up"])
def plan_step(case_id: str, index: int, body: PlanStepIn):
    c = get_case(case_id)
    if not 0 <= index < len(c["plan"]):
        raise HTTPException(404, "No such plan step.")
    c["plan"][index]["done"] = body.done
    STORE.audit(user_of(body.company), "plan_step", c["plan"][index]["what"])
    return views.follow_up(c)


class ScopeIn(BaseModel):
    company: str = "All"


@router.post("/cases/{case_id}/simulate-week", tags=["follow-up"])
def simulate_week(case_id: str, body: ScopeIn):
    c = get_case(case_id)
    if c["stage"] != "act":
        raise HTTPException(409, "Only open follow-ups get weekly updates.")
    for u in c["updates"]:
        u["fresh"] = False
    date = ["6 Oct", "13 Oct", "20 Oct", "27 Oct"][min(c["up_next"], 3)]
    c["updates"].insert(0, {"date": date, "text": STORE.next_update(c), "fresh": True})
    STORE.audit(user_of(body.company), "weekly_run", STORE.who(c))
    return views.follow_up(c)


class OutcomeIn(BaseModel):
    outcome: Literal["acted", "dropped"]
    company: str = "All"


@router.post("/cases/{case_id}/outcome", tags=["follow-up"])
def outcome(case_id: str, body: OutcomeIn):
    c = get_case(case_id)
    if c["stage"] != "act":
        raise HTTPException(409, "Only open follow-ups can be closed.")
    c.update(stage="closed", outcome="Acted on it" if body.outcome == "acted" else "Dropped after follow-up")
    STORE.audit(user_of(body.company), "outcome", f'{STORE.who(c)} · {body.outcome}')
    return views.follow_up(c)


# ---------- Explore ----------
@router.get("/competitors", tags=["explore"])
def competitors(company: str = Query(...)):
    if company not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{company}'.")
    return {"company": company, "rivals": views.roster(company)}


class FollowIn(BaseModel):
    company: str
    rival: str
    follow: bool = True


@router.post("/competitors/follow", tags=["explore"])
def follow(body: FollowIn):
    k = body.company + body.rival
    if body.follow:
        STORE.followed.add(k)
        STORE.audit(user_of(body.company), "follow_rival", body.rival)
    else:
        STORE.followed.discard(k)
    return {"company": body.company, "rivals": views.roster(body.company)}


@router.get("/market", tags=["explore"])
def market(company: str = Query(...), rival: str | None = None, period: str = "1Y"):
    if company not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{company}'.")
    if period not in REF["PERIODS"]:
        raise HTTPException(422, "period must be one of 1M, 6M, 1Y, 3Y.")
    return market_view(company, STORE.companies[company], rival, period)


@router.get("/deals", tags=["explore"])
def deals(company: str = Scope):
    check_scope(company)
    lst = [d for d in STORE.deals if company == "All" or d[6] == company]
    counts: dict[str, int] = {}
    for d in STORE.deals:
        counts[d[1]] = counts.get(d[1], 0) + 1
    top = sorted(counts.items(), key=lambda x: -x[1])[:6]
    tid = {t["name"]: "d_" + t["id"] for t in STORE.targets}
    return {"deals": [{"date": d[0], "buyer": d[1], "target": d[2], "type": d[3], "size": d[4], "sector": d[5], "for": d[6], "source": d[7], "case_id": tid.get(d[2])} for d in lst],
            "top_buyers": [{"buyer": b, "count": n} for b, n in top]}


class AskIn(BaseModel):
    company: str
    question: str = Field(min_length=1, max_length=500)


@router.get("/ask", tags=["explore"])
def ask_start(company: str = Query(...)):
    if company not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{company}'.")
    return {"first": ask_mod.first_turn(company), "suggestions": ask_mod.suggestions(company)}


@router.post("/ask", tags=["explore"])
def ask(body: AskIn):
    if body.company not in COMPANIES_ORDER:
        raise HTTPException(404, f"Unknown company '{body.company}'.")
    return {"question": body.question, **ask_mod.answer(body.company, body.question)}


# ---------- Radar settings ----------
@router.get("/theses", tags=["settings"])
def theses(request: Request):
    out = []
    for th in [t for t in STORE.theses if visible(request, t["desk"])]:
        rows = [{"case_id": "d_" + t["id"], "name": t["name"], "category": t["category"], "geo": t["geo"], "score": t["score"], **rules.thesis_match(th, t)} for t in STORE.targets]
        rows = [r for r in rows if r["checks"][0][1]]
        rows.sort(key=lambda r: (-r["pct"], -r["score"]))
        out.append({**th, "criteria": [c[0] for c in rules.thesis_match(th, STORE.targets[0])["checks"]], "matches": rows})
    return out


class ThesisTextIn(BaseModel):
    text: str = Field(min_length=3, max_length=600)


GEOS = ["India", "ASEAN", "Middle East", "US", "UK"]
OWNERSHIP = ["family", "promoter", "pe", "founder"]
THESIS_SYSTEM = """You turn an M&A acquisition thesis written in plain language into search criteria for the RPG Horizon Radar.
Pick only from the allowed values. sector: the industries the thesis targets. geo: the regions it names (India if none).
rev_min_crore / rev_max_crore: the revenue band in Indian rupee crore; use 0 and 99999 when the thesis gives no band.
own: the ownership types it asks for, or an empty list. Do not guess beyond what the text says."""


def parse_thesis(txt: str) -> tuple[dict, str]:
    """Plain-language thesis -> criteria, by gpt-4.1-mini when Azure is reachable, else by rules. The team confirms before saving."""
    if AZURE.available:
        schema = {"type": "object", "additionalProperties": False, "required": ["sector", "geo", "rev_min_crore", "rev_max_crore", "own"],
                  "properties": {"sector": {"type": "array", "items": {"type": "string", "enum": list(REF["SECTOR_LABEL"])}},
                                 "geo": {"type": "array", "items": {"type": "string", "enum": GEOS}},
                                 "rev_min_crore": {"type": "integer"}, "rev_max_crore": {"type": "integer"},
                                 "own": {"type": "array", "items": {"type": "string", "enum": OWNERSHIP}}}}
        try:
            r = AZURE.complete_json(THESIS_SYSTEM, txt, schema, "thesis_criteria", max_tokens=300)
            lo, hi = sorted([max(0, r["rev_min_crore"]), max(0, r["rev_max_crore"])])
            if r["sector"]:
                return {"sector": list(dict.fromkeys(r["sector"])), "geo": list(dict.fromkeys(r["geo"])) or ["India"],
                        "rev": [lo, hi], "own": list(dict.fromkeys(r["own"]))}, AZURE.deployment
        except AzureError:
            pass
    return parse_thesis_rules(txt), "rules"


def parse_thesis_rules(txt: str) -> dict:
    """Keyword rules: the fallback when Azure OpenAI is not available."""
    l, c = txt.lower(), {"sector": [], "geo": [], "rev": [0, 99999], "own": []}
    for pat, sec in [(r"tyre|tire|rubber compound", "tyres"), (r"epc|substation|transmission", "epc"), (r"\bai\b|analytics|software|it services", "it"),
                     (r"pharma|api|formulation", "pharma"), (r"cable|heat-shrink|joint|electrical", "electrical"), (r"tea|estate|plantation", "plantations"), (r"sensor|iot", "sensors")]:
        if re.search(pat, l):
            c["sector"].append(sec)
    c["sector"] = c["sector"] or ["tyres"]
    c["geo"] = [g for g in GEOS if g.lower() in l] or ["India"]
    m = re.search(r"(\d+)\s*[–-]\s*(\d+)", txt.replace(",", ""))
    if m:
        c["rev"] = [int(m.group(1)), int(m.group(2))]
    for pat, o in [(r"family", "family"), (r"promoter", "promoter"), (r"\bpe\b|private equity", "pe"), (r"founder", "founder")]:
        if re.search(pat, l):
            c["own"].append(o)
    return c


@router.post("/theses/parse", tags=["settings"])
def thesis_parse(body: ThesisTextIn):
    c, by = parse_thesis(body.text)
    return {"criteria": c, "labels": {"sector": [REF["SECTOR_LABEL"][s] for s in c["sector"]]}, "parsed_by": by}


class ThesisIn(BaseModel):
    desk: str
    text: str
    c: dict


@router.post("/theses", status_code=201, tags=["settings"])
def thesis_create(body: ThesisIn):
    if body.desk not in COMPANIES_ORDER:
        raise HTTPException(422, "desk must be an RPG company.")
    th = {"id": f"th{len(STORE.theses) + 1}", "desk": body.desk, "text": body.text, "c": body.c}
    STORE.theses.append(th)
    STORE.audit(user_of(body.desk), "create_thesis", body.desk)
    return th


def trig_out(tr: dict) -> dict:
    hits = rules.trigger_hits(tr, STORE.targets, STORE.deals) if tr["on"] else []
    return {**tr, "text": rules.trigger_text(tr), "hits": [{"case_id": "d_" + t["id"], "name": t["name"]} for t in hits]}


@router.get("/triggers", tags=["settings"])
def triggers(request: Request):
    return [trig_out(t) for t in STORE.triggers if t["desk"] == "All" or visible(request, t["desk"])]


class TriggerIn(BaseModel):
    desk: str = "All"
    metric: Literal["score", "pledge", "rating", "insolvency", "rivalstake"]
    op: Literal["above", "below", "is"] = "above"
    val: str = "50"
    company: str = "All"


@router.post("/triggers", status_code=201, tags=["settings"])
def trigger_create(body: TriggerIn):
    tr = {"id": f"tr{max([int(t['id'][2:]) for t in STORE.triggers if t['id'][2:].isdigit()] + [0]) + 1}", "desk": body.desk, "metric": body.metric, "op": body.op, "val": body.val, "on": True}
    if tr["metric"] == "insolvency":
        tr.update(op="is", val="filed")
    elif tr["metric"] == "rivalstake":
        tr.update(op="is", val="new")
    elif tr["metric"] == "rating":
        tr.update(op="below", val=tr["val"].upper())
    STORE.triggers.append(tr)
    STORE.audit(user_of(body.company), "create_trigger", rules.trigger_text(tr))
    return trig_out(tr)


class TriggerPatch(BaseModel):
    on: bool


def _own_trigger(request: Request, trigger_id: str) -> dict:
    tr = next((t for t in STORE.triggers if t["id"] == trigger_id), None)
    if not tr or not (visible(request, tr["desk"]) or (tr["desk"] == "All" and request.state.radar_admin)):
        raise HTTPException(404, "No such watch rule.")
    return tr


@router.patch("/triggers/{trigger_id}", tags=["settings"])
def trigger_toggle(trigger_id: str, body: TriggerPatch, request: Request):
    tr = _own_trigger(request, trigger_id)
    tr["on"] = body.on
    STORE.audit("strategy", "toggle_trigger", rules.trigger_text(tr))
    return trig_out(tr)


@router.delete("/triggers/{trigger_id}", status_code=204, tags=["settings"])
def trigger_delete(trigger_id: str, request: Request):
    _own_trigger(request, trigger_id)
    STORE.triggers = [t for t in STORE.triggers if t["id"] != trigger_id]
    STORE.audit("strategy", "delete_trigger", trigger_id)
    return Response(status_code=204)


@router.get("/universe", tags=["settings"])
def universe(request: Request):
    return [{"company": u[0], "desk": u[1], "sector": u[2], "added": u[3]} for u in STORE.universe if visible(request, u[1])]


class UniverseIn(BaseModel):
    company: str = Field(min_length=2, max_length=120)
    desk: str


@router.post("/universe", status_code=201, tags=["settings"])
def universe_add(body: UniverseIn):
    STORE.universe.insert(0, [body.company, body.desk, "–", f"Added by {body.desk} strategy"])
    STORE.audit(user_of(body.desk), "universe_add", body.company)
    return {"company": body.company, "desk": body.desk, "sector": "–", "added": f"Added by {body.desk} strategy"}


@router.get("/activity", tags=["settings"])
def activity(admin: Reviewer = Depends(admin_only)):
    """The radar's own activity feed (the immutable audit trail is Admin -> Audit Log)."""
    return [{"time": a[0], "who": a[1], "action": a[2], "detail": a[3]} for a in STORE.activity[:40]]


@router.post("/demo/reset", tags=["demo"])
def reset(admin: Reviewer = Depends(admin_only)):
    """Back to the start of the demo week. SWOTs the agent built from live data stay."""
    STORE.reset(keep_agent_swots=True)
    return {"ok": True}


@router.get("/health", tags=["demo"])
def health(x_request_id: str | None = Header(default=None)):
    return {"status": "ok", "request_id": x_request_id}
