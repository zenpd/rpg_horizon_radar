"""Acquisition Thesis agent. For one M&A signal (a watched company) and the RPG company it is viewed
for, writes a detailed acquisition thesis:

- the target's own SWOT, from public research on it (services/company_research.collect_company:
  results, shareholding, web pages per factor, news) and its public signals;
- a company background: business, history, products, scale, ownership and management;
- its connections: shareholders, promoter group, parent, subsidiaries, joint ventures, partners,
  key customers and suppliers named in the evidence, flagged when one is an RPG company or a
  company the radar watches;
- a SWOT comparison with the RPG company's current SWOT (agents/swot_analyst.py): where the target
  complements, overlaps with or conflicts with it;
- the post-acquisition SWOT: the RPG company's SWOT as it would look after the deal, each item marked
  new (from the target), strengthened, weakened or carried over (an item of its current SWOT);
- a fitment analysis: strategic, product, market, capability, scale and risk fit;
- the ripple effect: whether the deal is an opportunity, neutral or a risk for each of the other
  five RPG companies;
- whether a partial or a full acquisition looks likelier, and the open questions.

Every point cites numbered evidence; rule checks send a broken draft back for revision, as the
other agents do. It is a draft for review — no valuation, no deal price, not a recommendation to
bid. Stored per signal and RPG company in the ``thesis:<case>:<code>`` ConnectorState row; research
on the target is reused for RESEARCH_DAYS. write_due() writes every signal's thesis without anyone
opening it (services/scheduler.py: straight after each news run, SWOT rebuild and discovery, and every
30 minutes), and rewrites one that is out of date (stale()): the target has new or different public
signals, the RPG company's SWOT has been rebuilt since, or it is older than REWRITE_DAYS."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_routes import Drafter, LLMError, thesis_routes
from db.models import Entity
from agents.watchlist_discovery import PROFILES
from db.seed import SUBSIDIARIES
from ingestion.connectors.live.common import query_name
from radar.store import COMPANIES_ORDER, STORE
from services import company_research
from services import state as state_store

MAX_ROUNDS = 3
RESEARCH_DAYS = 7
# The target is researched on the factors that matter for a deal (one web search each).
TARGET_FACTORS = ["financial", "market", "products", "deals", "regulation", "ownership"]
REWRITE_DAYS = 7
# Kept small so a request fits a free LLM plan's tokens-per-minute (Groq's is about 8k): a refused
# request falls back to a much slower model.
MAX_EVIDENCE = 20
EVIDENCE_CHARS = 250
NOT_ASSESSED = "Not assessed in this draft."
RELATIONS = ["shareholder", "promoter", "parent", "subsidiary", "joint venture", "partner", "customer", "supplier", "director", "other"]
MAX_CONNECTIONS = 12
DIMENSIONS = ["Strategic", "Product", "Market", "Capability", "Scale", "Risk"]
RATINGS = ["strong", "moderate", "weak", "unknown"]
EFFECTS = ["complements", "overlaps", "conflicts"]
RIPPLE = ["opportunity", "neutral", "risk"]
CHANGES = ["new", "strengthened", "weakened", "carried over"]
IDS = re.compile(r"\b(?:E\d{1,3}|[SWOT][1-9])\b")

SYSTEM = """You are the Acquisition Thesis analyst for RPG Horizon Radar, the M&A radar of the RPG Group.

For one target company and the RPG company considering it, you write a detailed acquisition thesis from numbered public evidence about the target (E1, E2 ...) and the RPG company's current SWOT (S1, W1, O1, T1 ...).
- target_swot: the target's own strengths, weaknesses, opportunities and threats, each citing the evidence it rests on.
- comparison: the points where the target complements, overlaps with or conflicts with the RPG company. Name the item of the RPG company's SWOT it relates to (swot_ref), or null.
- post_swot: the RPG company's SWOT as it would look after the acquisition, for the combined business. Mark each item: new (it comes from the target; cite the evidence), strengthened or weakened (an item of the RPG company's current SWOT that the deal changes; name it in swot_ref and cite the evidence for the change), or carried over (a current item the deal leaves as it is; name it in swot_ref). 1-4 items per quadrant, the ones that matter most for the decision; a weakness the target fixes becomes a strengthened item, and a new risk it brings is a new weakness or threat.
- fitment: one entry per dimension (Strategic, Product, Market, Capability, Scale, Risk), rated strong, moderate, weak or unknown, with the reasoning and evidence. Use unknown, with no evidence, when the evidence says nothing about it; never guess. For Scale, compare the target's size with the RPG company's own results (rpg_company_facts): a target larger than the RPG company is a weak scale fit, and say so.
- ripple: for each other RPG company listed, whether owning the target would be an opportunity, neutral or a risk for it, and why, from its business and SWOT. Look for supplier and customer links (one company's product is another's input: a company that grows natural rubber supplies tyre makers, so a tyre deal is an opportunity for it), shared customers and shared markets, not only the same industry. Call it neutral when there is no such link; do not stretch for one.
- acquisition_type: full, partial or unclear, with the reason (e.g. a promoter stake sale points to partial; a listed company with a strong promoter, or one larger than the RPG company, makes full control unlikely).
- background: a short summary of the company (what it does, where, how big, who owns and runs it) and 2-6 cited points on its business, history, products, scale, ownership and management.
- connections: the companies and people the evidence names as linked to the target — shareholders and the promoter group (with the stake when stated), parent, subsidiaries, joint ventures, partners, key customers and suppliers, directors. Each cites the evidence that names the link; list none rather than guess. Up to 12.
- headline: one sentence on what the deal would do for the RPG company. open_questions: what a diligence team must answer first.
Write short, plain sentences. Use only the evidence and SWOT given; no invented facts, numbers or names, and no valuation, price or synergy figure. Never write an id inside a text field."""


class AgentError(Exception):
    pass


def key(case_id: str, code: str) -> str:
    return f"thesis:{case_id}:{code}"


FAILED: dict[str, dict] = {}  # thesis key -> {"error", "at"}: the last failed attempt, shown until one succeeds


def research_key(entity_id: int) -> str:
    return f"research:entity:{entity_id}"


# ---------- inputs ----------
def swot_items(co: str) -> list[dict]:
    s = STORE.swot.get(co)
    if not s:
        return []
    text = lambda x: x[0] if isinstance(x, list) else x
    return [{"ref": f"{q}{i + 1}", "text": text(x)} for q in "SWOT" for i, x in enumerate(s[q])]


def others(co: str) -> list[dict]:
    from radar.bridge import CO_TO_CODE  # imported here: radar.bridge imports the agents' store

    focus = {s["code"]: s for s in SUBSIDIARIES}
    out = []
    for name in COMPANIES_ORDER:
        if name == co:
            continue
        sub = focus[CO_TO_CODE[name]]
        out.append({"company": name, "business": PROFILES[sub["code"]][1], "sectors": sub["sectors"], "focus": sub["signal_focus"],
                    "swot_strengths": [x["text"] for x in swot_items(name) if x["ref"][0] == "S"][:3],
                    "swot_weaknesses": [x["text"] for x in swot_items(name) if x["ref"][0] == "W"][:3]})
    return out


def evidence(case: dict, facts: list[dict]) -> list[dict]:
    """The numbered evidence: its public signals, results and shareholding first, then web pages and news,
    at most MAX_EVIDENCE items of EVIDENCE_CHARS each."""
    clip = lambda t: t if len(t) <= EVIDENCE_CHARS else t[: EVIDENCE_CHARS - 1].rsplit(" ", 1)[0] + "…"
    signals = [{"date": s["date"], "source": s["source"], "text": clip(f"{s['label']}: {s['text']}"), "url": s.get("url")} for s in case["signals"]]
    first = [f for f in facts if f["kind"] in ("results", "shareholding")]
    rest = [f for f in facts if f["kind"] not in ("results", "shareholding")]
    raw = signals + [{"date": (f.get("observed_at") or "")[:10], "source": f["source"], "text": clip(f["text"]), "url": f.get("url")}
                     for f in first + rest]
    return [{"id": f"E{i}", **x} for i, x in enumerate(raw[:MAX_EVIDENCE], 1)]


def tidy(draft: dict, ids: set[str], refs: set[str], other_cos: list[str]) -> dict:
    """Fix the small, mechanical slips in place, so only real problems cost another model round: unknown
    evidence ids and SWOT references dropped, ids stripped from text, a missing fitment dimension or ripple
    entry added as not assessed, a rating with no evidence set to unknown, an uncited connection or
    background point dropped."""
    strip = lambda t: re.sub(r"\s*\(?\b(?:E\d{1,3}|[SWOT][1-9])\b\)?", "", t).strip()
    keep = lambda e: [x for x in dict.fromkeys(e) if x in ids]
    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        for x in draft["target_swot"][k]:
            x["text"], x["evidence"] = strip(x["text"]), keep(x["evidence"])
    for x in draft["comparison"]:
        x["point"], x["evidence"] = strip(x["point"]), keep(x["evidence"])
        if x["swot_ref"] not in refs:
            x["swot_ref"] = None
    bg = draft["background"]
    bg["summary"] = strip(bg["summary"])
    for x in bg["points"]:
        x["text"], x["evidence"] = strip(x["text"]), keep(x["evidence"])
    cited = [x for x in bg["points"] if x["evidence"]]
    if len(cited) >= 2:
        bg["points"] = cited
    draft["connections"] = [{**x, "detail": strip(x["detail"]), "evidence": keep(x["evidence"])} for x in draft["connections"]
                            if keep(x["evidence"])][:MAX_CONNECTIONS]
    fit = {}
    for x in draft["fitment"]:
        if x["dimension"] in DIMENSIONS and x["dimension"] not in fit:
            x["reasoning"], x["evidence"] = strip(x["reasoning"]), keep(x["evidence"])
            if not x["evidence"]:
                x["rating"] = "unknown"
            fit[x["dimension"]] = x
    draft["fitment"] = [fit.get(d) or {"dimension": d, "rating": "unknown", "reasoning": NOT_ASSESSED, "evidence": []} for d in DIMENSIONS]
    rip = {x["company"]: {**x, "reasoning": strip(x["reasoning"])} for x in draft["ripple"] if x["company"] in other_cos}
    draft["ripple"] = [rip.get(co) or {"company": co, "effect": "neutral", "reasoning": NOT_ASSESSED} for co in other_cos]
    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        for x in draft["post_swot"][k]:
            x["text"], x["evidence"] = strip(x["text"]), keep(x["evidence"])
            if x["swot_ref"] not in refs:
                x["swot_ref"] = None
            if x["change"] != "new" and x["swot_ref"] is None:
                x["change"] = "new"  # a change to no current item is a new item
    draft["headline"], draft["acquisition_reason"] = strip(draft["headline"]), strip(draft["acquisition_reason"])
    draft["open_questions"] = [strip(q) for q in draft["open_questions"]][:5]
    return draft


# ---------- the draft ----------
def schema(ids: list[str], refs: list[str], other_cos: list[str]) -> dict:
    cites = {"type": "array", "items": {"type": "string", "enum": ids}}
    item = {"type": "object", "additionalProperties": False, "required": ["text", "evidence"],
            "properties": {"text": {"type": "string"}, "evidence": cites}}
    quad = {"type": "array", "items": item}
    ref = {"anyOf": [{"type": "string", "enum": refs}, {"type": "null"}]} if refs else {"type": "null"}
    return {"type": "object", "additionalProperties": False,
            "required": ["headline", "background", "connections", "acquisition_type", "acquisition_reason", "target_swot", "comparison", "post_swot", "fitment", "ripple", "open_questions"],
            "properties": {
                "headline": {"type": "string"},
                "background": {"type": "object", "additionalProperties": False, "required": ["summary", "points"],
                               "properties": {"summary": {"type": "string"}, "points": {"type": "array", "items": item}}},
                "connections": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                "required": ["name", "relation", "detail", "evidence"],
                                "properties": {"name": {"type": "string"}, "relation": {"type": "string", "enum": RELATIONS},
                                               "detail": {"type": "string"}, "evidence": cites}}},
                "acquisition_type": {"type": "string", "enum": ["full", "partial", "unclear"]},
                "acquisition_reason": {"type": "string"},
                "target_swot": {"type": "object", "additionalProperties": False, "required": ["strengths", "weaknesses", "opportunities", "threats"],
                                "properties": {k: quad for k in ("strengths", "weaknesses", "opportunities", "threats")}},
                "post_swot": {"type": "object", "additionalProperties": False, "required": ["strengths", "weaknesses", "opportunities", "threats"],
                              "properties": {k: {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                 "required": ["text", "change", "swot_ref", "evidence"],
                                                 "properties": {"text": {"type": "string"}, "change": {"type": "string", "enum": CHANGES},
                                                                "swot_ref": ref, "evidence": cites}}}
                                             for k in ("strengths", "weaknesses", "opportunities", "threats")}},
                "comparison": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                               "required": ["point", "effect", "swot_ref", "evidence"],
                               "properties": {"point": {"type": "string"}, "effect": {"type": "string", "enum": EFFECTS}, "swot_ref": ref, "evidence": cites}}},
                "fitment": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                            "required": ["dimension", "rating", "reasoning", "evidence"],
                            "properties": {"dimension": {"type": "string", "enum": DIMENSIONS}, "rating": {"type": "string", "enum": RATINGS},
                                           "reasoning": {"type": "string"}, "evidence": cites}}},
                "ripple": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["company", "effect", "reasoning"],
                           "properties": {"company": {"type": "string", "enum": other_cos}, "effect": {"type": "string", "enum": RIPPLE},
                                          "reasoning": {"type": "string"}}}},
                "open_questions": {"type": "array", "items": {"type": "string"}}}}


def check(draft: dict, ids: set[str], refs: set[str], other_cos: list[str]) -> list[str]:
    errs: list[str] = []
    points = draft["background"]["points"]
    if not draft["background"]["summary"].strip() or not 2 <= len(points) <= 6:
        errs.append(f"Give a background summary and 2-6 background points; you gave {len(points)} points.")
    for i, x in enumerate(points, 1):
        if not x["evidence"] or set(x["evidence"]) - ids:
            errs.append(f"Background point {i} must cite evidence ids from the list.")
    if len(draft["connections"]) > MAX_CONNECTIONS:
        errs.append(f"List at most {MAX_CONNECTIONS} connections, the most important.")
    for x in draft["connections"]:
        if not x["evidence"] or set(x["evidence"]) - ids:
            errs.append(f"Connection '{x['name']}' must cite the evidence that names the link.")
    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        items = draft["target_swot"][k]
        if not 1 <= len(items) <= 4:
            errs.append(f"List 1-4 target {k}; you listed {len(items)}.")
        for i, x in enumerate(items, 1):
            if not x["evidence"] or set(x["evidence"]) - ids:
                errs.append(f"Target {k} {i} must cite evidence ids from the list.")
    if not 2 <= len(draft["comparison"]) <= 6:
        errs.append(f"Give 2-6 comparison points; you gave {len(draft['comparison'])}.")
    for i, x in enumerate(draft["comparison"], 1):
        if x["swot_ref"] is not None and x["swot_ref"] not in refs:
            errs.append(f"Comparison point {i}: {x['swot_ref']} is not an item of the RPG company's SWOT; use one of them or null.")
        if set(x["evidence"]) - ids:
            errs.append(f"Comparison point {i} cites ids that are not in the evidence list.")
    for k in ("strengths", "weaknesses", "opportunities", "threats"):
        items = draft["post_swot"][k]
        if not 1 <= len(items) <= 4:
            errs.append(f"List 1-4 post-acquisition {k}; you listed {len(items)}.")
        for i, x in enumerate(items, 1):
            if set(x["evidence"]) - ids:
                errs.append(f"Post-acquisition {k} {i} cites ids that are not in the evidence list.")
            elif x["change"] in ("new", "strengthened", "weakened") and not x["evidence"]:
                errs.append(f"Post-acquisition {k} {i} is marked {x['change']} but cites no evidence; cite it, or mark it carried over with its swot_ref.")
    dims = [x["dimension"] for x in draft["fitment"]]
    if sorted(dims) != sorted(DIMENSIONS):
        errs.append(f"Give exactly one fitment entry for each of: {', '.join(DIMENSIONS)}.")
    for x in draft["fitment"]:
        if x["rating"] != "unknown" and not x["evidence"]:
            errs.append(f"Fitment '{x['dimension']}' is rated {x['rating']} but cites no evidence; cite it or rate it unknown.")
        if set(x["evidence"]) - ids:
            errs.append(f"Fitment '{x['dimension']}' cites ids that are not in the evidence list.")
    if sorted(x["company"] for x in draft["ripple"]) != sorted(other_cos):
        errs.append(f"Give exactly one ripple entry for each of: {', '.join(other_cos)}.")
    if not 1 <= len(draft["open_questions"]) <= 5:
        errs.append("List 1-5 open questions.")
    texts = [draft["headline"], draft["acquisition_reason"], *draft["open_questions"], draft["background"]["summary"],
             *(x["text"] for x in draft["background"]["points"]), *(x["detail"] for x in draft["connections"]),
             *(x["text"] for k in draft["target_swot"] for x in draft["target_swot"][k]),
             *(x["point"] for x in draft["comparison"]), *(x["text"] for k in draft["post_swot"] for x in draft["post_swot"][k]), *(x["reasoning"] for x in draft["fitment"]), *(x["reasoning"] for x in draft["ripple"])]
    leaked = sorted({m for t in texts for m in IDS.findall(t)})
    if leaked:
        errs.append(f"Text fields mention ids ({', '.join(leaked)}). Write plain sentences; ids belong only in evidence and swot_ref.")
    return errs


def run(case: dict, co: str, ev: list[dict], drafter=None) -> dict:
    """Blocking: draft, check, revise. Returns {draft, rounds, model} or raises AgentError."""
    try:
        drafter = drafter or Drafter(routes=thesis_routes())
    except LLMError as e:
        raise AgentError(str(e))
    items, other = swot_items(co), others(co)
    ids, refs, other_cos = [x["id"] for x in ev], [x["ref"] for x in items], [o["company"] for o in other]
    own = [f["text"] for f in (STORE.research.get(co) or {}).get("facts") or [] if f["kind"] in ("results", "shareholding")]
    payload = {"target": case["who"], "rpg_company": co,
               "rpg_company_swot": items or "No SWOT yet for the RPG company: use swot_ref null.",
               "rpg_company_facts": own or "No results on record for the RPG company.",
               "other_rpg_companies": other,
               "evidence_about_target": [{k: x[k] for k in ("id", "date", "source", "text")} for x in ev]}
    messages = [{"role": "user", "content": "Write the acquisition thesis.\n\n" + json.dumps(payload, indent=1, ensure_ascii=False)}]
    errs: list[str] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        try:
            text = drafter.draft(SYSTEM, messages, schema(ids, refs, other_cos), "thesis")
        except LLMError as e:
            raise AgentError(str(e))
        try:
            draft = tidy(json.loads(text), set(ids), set(refs), other_cos)
            errs = check(draft, set(ids), set(refs), other_cos)
        except json.JSONDecodeError as e:
            errs = [f"The reply was not valid JSON ({e.msg} at character {e.pos}). Return only the JSON object."]
        except KeyError as e:
            errs = [f"The reply is missing the field {e}. Return the JSON object with every field."]
        except (TypeError, AttributeError):
            errs = ["A field in the reply has the wrong type. Follow the schema exactly."]
        if not errs:
            return {"draft": draft, "rounds": rnd, "model": drafter.model}
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "The thesis breaks these rules. Fix them and return the full thesis again.\n- " + "\n- ".join(errs)}]
    raise AgentError(f"The thesis still broke {len(errs)} rule(s) after {MAX_ROUNDS} rounds: " + " ".join(errs[:3]))


# ---------- a build ----------
async def research(db: AsyncSession, entity: Entity, transport=None) -> dict:
    """Public research on the target, reused for RESEARCH_DAYS."""
    from services.ingest import RUN_LOCK  # the Fincrux budget lives in the shared ``live`` state

    saved = await state_store.load(db, research_key(entity.id))
    if saved.get("at") and datetime.now() - datetime.fromisoformat(saved["at"]) < timedelta(days=RESEARCH_DAYS):
        return saved
    settings = {"sources": ["results", "shareholding", "web", "news"], "factors": TARGET_FACTORS, "sector_queries": []}
    async with RUN_LOCK:
        live = await state_store.load(db, "live")
        facts, errors = await asyncio.to_thread(company_research.collect_company, entity.name, query_name(entity), entity.nse_symbol,
                                                live, settings, transport)
        await state_store.save(db, "live", live)
    saved = {"at": datetime.now().isoformat(timespec="seconds"), "facts": facts, "errors": errors}
    await state_store.save(db, research_key(entity.id), saved)
    await db.commit()
    return saved


async def build(db: AsyncSession, case_id: str, co: str, drafter=None, transport=None) -> dict:
    """Research the target, write its thesis for ``co`` and store it. Returns the stored thesis."""
    from radar.bridge import CO_TO_CODE  # imported here: radar.bridge imports the agents' store

    case = STORE.cases[case_id]
    entity = await db.get(Entity, case["entity_id"])
    if entity is None:
        raise AgentError(f"{case['who']} is no longer on the watchlist.")
    found = await research(db, entity, transport)
    ev = evidence(case, found.get("facts") or [])
    out = await asyncio.to_thread(run, case, co, ev, drafter)
    for x in out["draft"]["connections"]:
        x["link"] = link(x["name"])
    thesis = {"case_id": case_id, "company": co, "target": case["who"], "at": datetime.now().strftime("%d %b %Y %H:%M"),
              "written_at": datetime.now().isoformat(timespec="seconds"),
              "model": out["model"], "rounds": out["rounds"], "research_errors": found.get("errors") or [],
              "swot_at": (STORE.swot_source.get(co) or {}).get("at"), "signals_key": signals_key(case),
              "draft": out["draft"], "evidence": ev}
    await state_store.save(db, key(case_id, CO_TO_CODE[co]), thesis)
    await db.commit()
    FAILED.pop(key(case_id, CO_TO_CODE[co]), None)
    return thesis


def signals_key(case: dict) -> str:
    """A fingerprint of the target's public signals: it changes when one is added or dropped."""
    import hashlib

    return hashlib.sha1("|".join(sorted(f"{s['date']}:{s['source']}:{s['text']}" for s in case["signals"])).encode()).hexdigest()[:16]


def stale(t: dict, case: dict, co: str) -> str | None:
    """Why a stored thesis needs rewriting, or None when it is up to date."""
    if not t.get("written_at"):
        return "not written"
    if datetime.now() - datetime.fromisoformat(t["written_at"]) >= timedelta(days=REWRITE_DAYS):
        return f"older than {REWRITE_DAYS} days"
    if t.get("signals_key") != signals_key(case):
        return "new public signals"
    if t.get("swot_at") != (STORE.swot_source.get(co) or {}).get("at"):
        return f"{co}'s SWOT was rebuilt"
    return None


def link(name: str) -> str | None:
    """'RPG company' or 'watched company' when a connection is one of them, else None."""
    from ingestion.connectors.live.common import short_name

    n = short_name(name).lower()
    group = {short_name(x).lower() for x in COMPANIES_ORDER} | {"rpg", "rpg enterprises", "rpg group", "ceat", "kec", "zensar technologies", "harrisons malayalam"}
    if n in group or n.startswith("rpg "):
        return "RPG company"
    watched = {short_name(w["name"]).lower() for ws in (STORE.live_meta.get("watch") or {}).values() for w in ws}
    return "watched company" if n in watched else None


def due_cases() -> list[tuple[str, str]]:
    """(case, RPG company) pairs whose thesis should be written now: every M&A signal not in the archive —
    a company an RPG company could plausibly buy (radar.views.signal_for) — for that RPG company."""
    from radar.views import signal_for

    cases = sorted((c for c in STORE.cases.values() if c["status"] != "dismissed"), key=lambda c: -(c["score"] or 0))
    return [(c["id"], co) for c in cases if (co := signal_for(c))]  # highest score first


async def write_due(user: str = "radar", drafter=None, transport=None) -> dict:
    """Write each signal's missing thesis and rewrite each out-of-date one (stale()), one after another."""
    from db.base import get_db_session
    from radar.bridge import CO_TO_CODE

    written, errors = [], []
    for cid, co in due_cases():
        async with get_db_session() as db:
            t = await state_store.load(db, key(cid, CO_TO_CODE[co]))
            if cid not in STORE.cases or not stale(t, STORE.cases[cid], co):
                continue
            try:
                await build(db, cid, co, drafter, transport)
                written.append(STORE.cases[cid]["who"])
                STORE.audit(user, "thesis", f"{STORE.cases[cid]['who']} for {co}")
            except Exception as e:  # noqa: BLE001 — one signal failing never stops the others
                errors.append(f"{STORE.cases.get(cid, {}).get('who', cid)}: {e}")
                FAILED[key(cid, CO_TO_CODE[co])] = {"error": str(e), "at": datetime.now().strftime("%d %b %H:%M")}
    return {"written": written, "errors": errors}


async def load(db: AsyncSession, case_id: str, co: str) -> dict | None:
    from radar.bridge import CO_TO_CODE

    return await state_store.load(db, key(case_id, CO_TO_CODE[co])) or None
