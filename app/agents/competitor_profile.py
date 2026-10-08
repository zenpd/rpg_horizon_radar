"""Competitor Profile agent. For one watched company and the RPG company watching it, writes an
overview from numbered public evidence — its public signals, then the research the Acquisition
Thesis agent keeps on it (results, shareholding, web pages on six factors, news):

- a short summary of the company and what it has been doing;
- its SWOT, each item cited;
- how it competes with the RPG company: where it is ahead, behind or head-to-head, linked to an item
  of the RPG company's current SWOT where one fits;
- the competitive intensity with the RPG company (high, medium, low) and why;
- what to watch next.

The recent moves (patents, hiring, deals, results, news) and the financial snapshot are shown from
the stored signals and research as they are (radar/api.py); the agent writes only the analysis.
Rule checks send a broken draft back for revision, as the other agents do. Stored per company and
RPG company in the ``profile:<entity>:<code>`` ConnectorState row. write_due() writes the profile of
every watched company with public signals in the background and rewrites one that is out of date
(new signals, a rebuilt SWOT, or older than REWRITE_DAYS); the others are written when opened."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agents import acquisition_thesis as thesis
from agents.llm_routes import Drafter, LLMError, thesis_routes
from db.models import Entity
from radar.store import COMPANIES_ORDER, STORE
from services import state as state_store

MAX_ROUNDS = 3
REWRITE_DAYS = 7
SIDES = ["ahead", "behind", "head-to-head"]
THREAT = ["high", "medium", "low"]
IDS = re.compile(r"\b(?:E\d{1,3}|[SWOT][1-9])\b")
QUADS = ("strengths", "weaknesses", "opportunities", "threats")

SYSTEM = """You are the Competitor Profile analyst for RPG Horizon Radar, the M&A radar of the RPG Group.

For one company the RPG company watches, you write an overview from numbered public evidence about it (E1, E2 ...) and the RPG company's current SWOT (S1, W1, O1, T1 ...).
- summary: 2-3 sentences on what the company does and what it has been doing lately, from the evidence.
- swot: its own strengths, weaknesses, opportunities and threats, 1-4 each, each citing the evidence it rests on.
- versus: 2-6 points on how it competes with the RPG company: where it is ahead of it, behind it, or head-to-head. Name the item of the RPG company's SWOT the point relates to (swot_ref), or null. Cite the evidence about the company.
- threat: the competitive intensity with the RPG company — how hard it competes with it (high, medium or low) — and why, in one or two sentences. Judge from the overlap in products and markets and its recent moves; a company in a different business is low.
- watch: 1-4 short things the RPG company should watch for next (an expected result, a capacity start-up, a pending deal, a court case).
Write short, plain sentences. Use only the evidence and SWOT given; no invented facts, numbers or names. Never write an id inside a text field."""


class AgentError(Exception):
    pass


FAILED: dict[str, dict] = {}  # profile key -> {"error", "at"}: the last failed attempt


def key(entity_id: int, code: str) -> str:
    return f"profile:{entity_id}:{code}"


def rival(entity_id: int, co: str) -> dict | None:
    """The watched company as the radar holds it for ``co``, with its signals (none when it has had none)."""
    r = next((r for r in STORE.rivals.get(co, []) if r["id"] == entity_id), None)
    if r:
        return r
    w = next((w for w in (STORE.live_meta.get("watch") or {}).get(co, []) if w["id"] == entity_id and w["status"] == "watching"), None)
    return {"id": w["id"], "name": w["name"], "signals": []} if w else None


def signals_key(signals: list[dict]) -> str:
    return hashlib.sha1("|".join(sorted(f"{s['date']}:{s['source']}:{s['text']}" for s in signals)).encode()).hexdigest()[:16]


# ---------- the draft ----------
def schema(ids: list[str], refs: list[str]) -> dict:
    cites = {"type": "array", "items": {"type": "string", "enum": ids}}
    item = {"type": "object", "additionalProperties": False, "required": ["text", "evidence"],
            "properties": {"text": {"type": "string"}, "evidence": cites}}
    ref = {"anyOf": [{"type": "string", "enum": refs}, {"type": "null"}]} if refs else {"type": "null"}
    return {"type": "object", "additionalProperties": False, "required": ["summary", "swot", "versus", "threat", "watch"],
            "properties": {
                "summary": {"type": "string"},
                "swot": {"type": "object", "additionalProperties": False, "required": list(QUADS),
                         "properties": {k: {"type": "array", "items": item} for k in QUADS}},
                "versus": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                           "required": ["point", "side", "swot_ref", "evidence"],
                           "properties": {"point": {"type": "string"}, "side": {"type": "string", "enum": SIDES},
                                          "swot_ref": ref, "evidence": cites}}},
                "threat": {"type": "object", "additionalProperties": False, "required": ["level", "reason"],
                           "properties": {"level": {"type": "string", "enum": THREAT}, "reason": {"type": "string"}}},
                "watch": {"type": "array", "items": {"type": "string"}}}}


def tidy(draft: dict, ids: set[str], refs: set[str]) -> dict:
    """Fix mechanical slips in code: unknown ids and SWOT references dropped, ids stripped from text."""
    strip = lambda t: re.sub(r"\s*\(?\b(?:E\d{1,3}|[SWOT][1-9])\b\)?", "", t).strip()
    keep = lambda e: [x for x in dict.fromkeys(e) if x in ids]
    draft["summary"] = strip(draft["summary"])
    for k in QUADS:
        for x in draft["swot"][k]:
            x["text"], x["evidence"] = strip(x["text"]), keep(x["evidence"])
    for x in draft["versus"]:
        x["point"], x["evidence"] = strip(x["point"]), keep(x["evidence"])
        if x["swot_ref"] not in refs:
            x["swot_ref"] = None
    draft["threat"]["reason"] = strip(draft["threat"]["reason"])
    draft["watch"] = [strip(w) for w in draft["watch"]][:4]
    return draft


def check(draft: dict, ids: set[str]) -> list[str]:
    errs: list[str] = []
    if not draft["summary"].strip():
        errs.append("Write the summary.")
    for k in QUADS:
        items = draft["swot"][k]
        if not 1 <= len(items) <= 4:
            errs.append(f"List 1-4 {k}; you listed {len(items)}.")
        for i, x in enumerate(items, 1):
            if not x["evidence"] or set(x["evidence"]) - ids:
                errs.append(f"{k.capitalize()} {i} must cite evidence ids from the list.")
    if not 2 <= len(draft["versus"]) <= 6:
        errs.append(f"Give 2-6 points on how it competes with the RPG company; you gave {len(draft['versus'])}.")
    for i, x in enumerate(draft["versus"], 1):
        if not x["evidence"]:
            errs.append(f"Competition point {i} must cite the evidence about the company.")
    if not draft["threat"]["reason"].strip():
        errs.append("Give the reason for the competitive intensity.")
    if not 1 <= len(draft["watch"]) <= 4:
        errs.append("List 1-4 things to watch.")
    texts = [draft["summary"], draft["threat"]["reason"], *draft["watch"], *(x["point"] for x in draft["versus"]),
             *(x["text"] for k in QUADS for x in draft["swot"][k])]
    leaked = sorted({m for t in texts for m in IDS.findall(t)})
    if leaked:
        errs.append(f"Text fields mention ids ({', '.join(leaked)}). Write plain sentences; ids belong only in evidence and swot_ref.")
    return errs


def run(name: str, co: str, ev: list[dict], drafter=None) -> dict:
    """Blocking: draft, check, revise. Returns {draft, rounds, model} or raises AgentError."""
    try:
        drafter = drafter or Drafter(routes=thesis_routes())
    except LLMError as e:
        raise AgentError(str(e))
    items = thesis.swot_items(co)
    ids, refs = [x["id"] for x in ev], [x["ref"] for x in items]
    payload = {"company": name, "rpg_company": co,
               "rpg_company_swot": items or "No SWOT yet for the RPG company: use swot_ref null.",
               "evidence_about_company": [{k: x[k] for k in ("id", "date", "source", "text")} for x in ev]}
    messages = [{"role": "user", "content": "Write the competitor overview.\n\n" + json.dumps(payload, indent=1, ensure_ascii=False)}]
    errs: list[str] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        try:
            text = drafter.draft(SYSTEM, messages, schema(ids, refs), "competitor_profile")
        except LLMError as e:
            raise AgentError(str(e))
        try:
            draft = tidy(json.loads(text), set(ids), set(refs))
            errs = check(draft, set(ids))
        except json.JSONDecodeError as e:
            errs = [f"The reply was not valid JSON ({e.msg} at character {e.pos}). Return only the JSON object."]
        except KeyError as e:
            errs = [f"The reply is missing the field {e}. Return the JSON object with every field."]
        except (TypeError, AttributeError):
            errs = ["A field in the reply has the wrong type. Follow the schema exactly."]
        if not errs:
            return {"draft": draft, "rounds": rnd, "model": drafter.model}
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "The overview breaks these rules. Fix them and return the full overview again.\n- " + "\n- ".join(errs)}]
    raise AgentError(f"The overview still broke {len(errs)} rule(s) after {MAX_ROUNDS} rounds: " + " ".join(errs[:3]))


# ---------- a build ----------
async def build(db: AsyncSession, entity_id: int, co: str, drafter=None, transport=None) -> dict:
    """Research the company (reusing the thesis agent's research), write its overview for ``co`` and store it."""
    from radar.bridge import CO_TO_CODE

    entity = await db.get(Entity, entity_id)
    r = rival(entity_id, co)
    if entity is None or r is None:
        raise AgentError(f"Company {entity_id} is not on {co}'s watchlist.")
    found = await thesis.research(db, entity, transport)
    ev = thesis.evidence({"signals": r["signals"]}, found.get("facts") or [])
    if not ev:
        raise AgentError(f"There is no public evidence on {entity.name} yet.")
    out = await asyncio.to_thread(run, entity.name, co, ev, drafter)
    k = key(entity_id, CO_TO_CODE[co])
    profile = {"entity_id": entity_id, "company": co, "name": entity.name, "at": datetime.now().strftime("%d %b %Y %H:%M"),
               "written_at": datetime.now().isoformat(timespec="seconds"), "model": out["model"], "rounds": out["rounds"],
               "research_errors": found.get("errors") or [], "signals_key": signals_key(r["signals"]),
               "swot_at": (STORE.swot_source.get(co) or {}).get("at"), "draft": out["draft"], "evidence": ev}
    await state_store.save(db, k, profile)
    await db.commit()
    FAILED.pop(k, None)
    return profile


def stale(p: dict, r: dict, co: str) -> str | None:
    if not p.get("written_at"):
        return "not written"
    if datetime.now() - datetime.fromisoformat(p["written_at"]) >= timedelta(days=REWRITE_DAYS):
        return f"older than {REWRITE_DAYS} days"
    if p.get("signals_key") != signals_key(r["signals"]):
        return "new public signals"
    if p.get("swot_at") != (STORE.swot_source.get(co) or {}).get("at"):
        return f"{co}'s SWOT was rebuilt"
    return None


def due() -> list[tuple[int, str]]:
    """(company, RPG company) pairs written in the background: every watched company with public
    signals, most signals first."""
    pairs = [(len(r["signals"]), r["id"], co) for co in COMPANIES_ORDER for r in STORE.rivals.get(co, []) if r["signals"]]
    return [(eid, co) for _, eid, co in sorted(pairs, key=lambda x: -x[0])]


async def write_due(user: str = "radar", drafter=None, transport=None) -> dict:
    """Write each due profile that is missing or out of date, one after another."""
    from db.base import get_db_session
    from radar.bridge import CO_TO_CODE

    written, errors = [], []
    for eid, co in due():
        r = rival(eid, co)
        async with get_db_session() as db:
            p = await state_store.load(db, key(eid, CO_TO_CODE[co]))
            if r is None or not stale(p, r, co):
                continue
            try:
                await build(db, eid, co, drafter, transport)
                written.append(f"{r['name']} for {co}")
                STORE.audit(user, "competitor_profile", f"{r['name']} for {co}")
            except Exception as e:  # noqa: BLE001 — one company failing never stops the others
                errors.append(f"{r['name']} for {co}: {e}")
                FAILED[key(eid, CO_TO_CODE[co])] = {"error": str(e), "at": datetime.now().strftime("%d %b %H:%M")}
    return {"written": written, "errors": errors}


async def load(db: AsyncSession, entity_id: int, co: str) -> dict | None:
    from radar.bridge import CO_TO_CODE

    return await state_store.load(db, key(entity_id, CO_TO_CODE[co])) or None
