"""Opportunity Analyst agent. Every day, for each RPG company: reads the last two days of news about
the company, the companies it watches and its industry (services/company_research.daily_news, the
sector searches from its SWOT parameters), plus its watched companies' new signals; asks an LLM for
the opportunities and threats that news creates, each judged against the company's current SWOT
(the item it affects, or "new"); checks the draft and sends problems back for revision, as the SWOT
Analyst does; and stores what passes in opportunity_findings.

Users keep or dismiss findings on This week. Kept findings of the last week are evidence for the
next weekly SWOT (radar/evidence.daily). The agent never scores a signal or changes the SWOT itself.
Runs daily at OPPORTUNITY_DAILY_AT (services/scheduler.py), or on request."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_routes import Drafter, LLMError
from db.models import OpportunityFinding
from radar.store import STORE
from services import company_research, swot_settings
from services import state as state_store

MAX_ROUNDS = 3
MAX_FINDINGS = 6
REPEAT_DAYS = 7  # findings and news of this many days back are not reported again
STATE_KEY = "opportunities"  # ConnectorState: each company's last run {at, news, findings, errors}

SYSTEM = """You are the Opportunity Analyst for RPG Horizon Radar, the competitive intelligence and M&A radar of the RPG Group.

Every day you read the latest news for one RPG company — news about the company itself, about the companies it watches, and about its industry — and find the opportunities and threats that news creates for the company, judged against its current SWOT.
- A finding is an opportunity (something the company could use) or a threat (something that could hurt it). Report only news that matters to this company. Most news does not: return fewer findings, or none, rather than stretch.
- Every finding cites the news items it rests on, by id (N1, N2 ...).
- swot_ref is the item of the current SWOT the finding affects most (S1, W2, O1, T3 ...), or null when the finding is new — something the SWOT does not cover yet. effect is one sentence on how it affects that item (it eases a weakness, strengthens a strength, makes a threat more likely ...) or, for a new finding, why it matters.
- Score impact and urgency 0-100 from the news alone.
- action is one short, concrete next step for the company's strategy team.
- Do not report again a finding listed under previous findings, unless the news adds something new; then say what is new.
Never write an id inside title, summary, effect or action. Use only the news given; do not invent facts, numbers or names."""

IDS = re.compile(r"\b(?:N\d{1,3}|[SWOT][1-9])\b")


class AgentError(Exception):
    pass


# ---------- inputs ----------
def watched_names(co: str) -> list[str]:
    return [w["name"] for w in (STORE.live_meta.get("watch") or {}).get(co, []) if w["status"] == "watching"]


def swot_items(co: str) -> list[dict]:
    s = STORE.swot.get(co)
    if not s:
        return []
    text = lambda x: x[0] if isinstance(x, list) else x
    return [{"ref": f"{q}{i + 1}", "text": text(x)} for q in "SWOT" for i, x in enumerate(s[q])]


def signals_since(co: str, since: datetime) -> list[dict]:
    """Watched companies' new public signals (already fetched by ingestion), as news items."""
    return [{"kind": "watched_news", "text": f"{x['company']}: {x['text']}", "source": x["source"], "url": x.get("url"),
             "observed_at": x["observed_at"]} for x in STORE.live.get(co, []) if x["observed_at"] >= since.isoformat()]


ABOUT = {"company_news": "the company", "watched_news": "a watched company", "sector_news": "its industry"}


def numbered(news: list[dict]) -> list[dict]:
    return [{"id": f"N{i}", "about": ABOUT[n["kind"]], "date": (n.get("observed_at") or "")[:10], "source": n["source"],
             "text": n["text"], "url": n.get("url")} for i, n in enumerate(news, 1)]


# ---------- the draft ----------
def schema(news_ids: list[str], refs: list[str]) -> dict:
    ref = {"anyOf": [{"type": "string", "enum": refs}, {"type": "null"}]} if refs else {"type": "null"}
    finding = {"type": "object", "additionalProperties": False,
               "required": ["kind", "title", "summary", "swot_ref", "effect", "impact", "urgency", "action", "evidence"],
               "properties": {"kind": {"type": "string", "enum": ["opportunity", "threat"]}, "title": {"type": "string"},
                              "summary": {"type": "string"}, "swot_ref": ref, "effect": {"type": "string"},
                              "impact": {"type": "integer"}, "urgency": {"type": "integer"}, "action": {"type": "string"},
                              "evidence": {"type": "array", "items": {"type": "string", "enum": news_ids}}}}
    return {"type": "object", "additionalProperties": False, "required": ["findings"],
            "properties": {"findings": {"type": "array", "items": finding}}}


def check(draft: dict, news_ids: set[str], refs: set[str], previous: list[str]) -> list[str]:
    errs: list[str] = []
    found = draft["findings"]
    if len(found) > MAX_FINDINGS:
        errs.append(f"Report at most {MAX_FINDINGS} findings, the ones that matter most; you reported {len(found)}.")
    seen = [company_research._words(t) for t in previous]
    for i, f in enumerate(found, 1):
        name = f"Finding {i} ('{f['title']}')"
        if f["kind"] not in ("opportunity", "threat"):
            errs.append(f"{name}: kind must be opportunity or threat.")
        if not f["evidence"]:
            errs.append(f"{name} cites no news; list the news ids it rests on.")
        bad = [e for e in f["evidence"] if e not in news_ids]
        if bad:
            errs.append(f"{name} cites {', '.join(bad)}, which are not in the news list.")
        if f["swot_ref"] is not None and f["swot_ref"] not in refs:
            errs.append(f"{name}: swot_ref {f['swot_ref']} is not an item of the current SWOT; use one of them or null.")
        if not (0 <= f["impact"] <= 100 and 0 <= f["urgency"] <= 100):
            errs.append(f"{name}: impact and urgency must be between 0 and 100.")
        if not f["effect"].strip() or not f["action"].strip():
            errs.append(f"{name} needs an effect and an action.")
        if IDS.findall(" ".join((f["title"], f["summary"], f["effect"], f["action"]))):
            errs.append(f"{name} mentions ids in its text. Write plain sentences; ids belong only in evidence and swot_ref.")
        words = company_research._words(f["title"])
        if any(company_research._same(words, w) for w in seen):
            errs.append(f"{name} was already reported in the last {REPEAT_DAYS} days. Leave it out unless the news adds something new, and then say what in the title.")
    return errs


def run(co: str, news: list[dict], previous: list[str], drafter=None) -> dict:
    """Blocking: draft, check, revise. Returns {draft, rounds, model} or raises AgentError."""
    try:
        drafter = drafter or Drafter()
    except LLMError as e:
        raise AgentError(str(e))
    items = swot_items(co)
    ids, refs = [n["id"] for n in news], [x["ref"] for x in items]
    payload = {"company": co, "current_swot": items or "No SWOT yet: every finding is new (swot_ref null).",
               "previous_findings": previous, "news": [{k: n[k] for k in ("id", "about", "date", "source", "text")} for n in news]}
    messages = [{"role": "user", "content": "Find today's opportunities and threats for this RPG company.\n\n" + json.dumps(payload, indent=1, ensure_ascii=False)}]
    errs: list[str] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        try:
            text = drafter.draft(SYSTEM, messages, schema(ids, refs), "findings")
        except LLMError as e:
            raise AgentError(str(e))
        try:
            draft = json.loads(text)
            errs = check(draft, set(ids), set(refs), previous)
        except json.JSONDecodeError as e:
            errs = [f"The reply was not valid JSON ({e.msg} at character {e.pos}). Return only the JSON object."]
        except KeyError as e:
            errs = [f"The reply is missing the field {e}. Return the JSON object with every field."]
        except (TypeError, AttributeError):
            errs = ["A field in the reply has the wrong type. Follow the schema exactly."]
        if not errs:
            return {"draft": draft, "rounds": rnd, "model": drafter.model}
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "The findings break these rules. Fix them and return all findings again.\n- " + "\n- ".join(errs)}]
    raise AgentError(f"The findings still broke {len(errs)} rule(s) after {MAX_ROUNDS} rounds: " + " ".join(errs[:3]))


# ---------- a day's run ----------
async def analyse(db: AsyncSession, code: str, drafter=None, transport=None) -> dict:
    """One company's daily run: gather news, draft findings, store them. Returns a summary."""
    from radar.bridge import CODE_TO_CO  # imported here: radar.bridge imports the agents' store

    co = CODE_TO_CO[code]
    now = datetime.utcnow()
    since = now - timedelta(hours=company_research.DAILY_HOURS)
    settings = await swot_settings.load(db, code)
    news, errors = await asyncio.to_thread(company_research.daily_news, code, settings, watched_names(co), transport)
    news += signals_since(co, since)

    recent = (await db.execute(select(OpportunityFinding).where(
        OpportunityFinding.subsidiary_code == code, OpportunityFinding.found_on >= now - timedelta(days=REPEAT_DAYS)))).scalars().all()
    used = {e.get("url") for f in recent for e in f.evidence or [] if e.get("url")}
    news = [n for n in news if not n.get("url") or n["url"] not in used]  # already read on an earlier day
    previous = [f"{f.kind}: {f.title}" for f in recent]
    summary = {"company": co, "at": datetime.now().isoformat(timespec="seconds"), "news": len(news), "findings": 0, "errors": errors}
    if news:
        items = numbered(news)
        try:
            out = await asyncio.to_thread(run, co, items, previous, drafter)
        except AgentError as e:
            summary["errors"] = errors + [f"Opportunity Analyst: {e}"]
        else:
            by_id, refs = {n["id"]: n for n in items}, {x["ref"]: x["text"] for x in swot_items(co)}
            for f in out["draft"]["findings"]:
                db.add(OpportunityFinding(
                    subsidiary_code=code, found_on=now, kind=f["kind"], title=f["title"][:255], summary=f["summary"],
                    swot_ref=f["swot_ref"], swot_text=refs.get(f["swot_ref"] or "", ""), effect=f["effect"], action=f["action"],
                    impact=f["impact"], urgency=f["urgency"], model=out["model"], status="new",
                    evidence=[{k: by_id[e][k] for k in ("text", "source", "date", "url")} for e in dict.fromkeys(f["evidence"])]))
            summary["findings"] = len(out["draft"]["findings"])
    state = await state_store.load(db, STATE_KEY)
    state[code] = summary
    await state_store.save(db, STATE_KEY, state)
    await db.commit()
    return summary


async def analyse_all(db: AsyncSession, drafter=None, transport=None) -> dict:
    """The daily run for every company, one after another (so the LLM routes are not hit at once)."""
    out = {}
    for code in swot_settings.SECTOR_QUERIES:
        try:
            out[code] = await analyse(db, code, drafter, transport)
        except Exception as e:  # noqa: BLE001 — one company failing never stops the others
            await db.rollback()
            out[code] = {"errors": [f"{code}: {e}"], "findings": 0}
    return {"companies": out, "findings": sum(r.get("findings", 0) for r in out.values()),
            "errors": [e for r in out.values() for e in r.get("errors", [])]}
