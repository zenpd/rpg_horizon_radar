"""Sector Scout agent: acquisition targets found in the industry's own news.

Target Discovery (agents/target_discovery.py) searches for companies that fit a profile; this agent
reads what is happening in each RPG company's industry instead. Every day it reads the last
NEWS_DAYS of sector news (SCOUT_QUERIES: funding rounds, stake sales, distress, deals, contract wins
in the industry — GNews, else Tavily news), and a model picks the smaller companies named in it that
the RPG company could plausibly buy, with the event and why it matters. Only companies named in the
headlines or snippets they cite are kept (the grounding check), and a company already being bought
by someone else is left out.

Each pick is sized (services/company_size.py): one larger than half the RPG company is set aside
(watched as dismissed, so it is not picked again); one that cannot be sized from a sourced figure is
added as "Size not verified" — no number is ever taken from a search snippet. The others are added to the watchlist as role
"target" — or matched to a company already watched — and the news items become their public signals
(provider "Sector news"), so they appear on M&A Signals at once and the Acquisition Thesis agent
writes their thesis. Runs daily with the Opportunity Analyst (services/scheduler.py), or on demand."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_routes import Drafter, LLMError, thesis_routes
from agents.watchlist_discovery import GROUP, PROFILES
from db.models import Entity, RawSignal, Subsidiary
from ingestion.connectors.live.common import SourceError, about, same_company, short_name
from services import company_research, company_size
from services import state as state_store
from services.audit import write_audit

NEWS_DAYS = 7
MAX_ITEMS = 40
MAX_PICKS = 8
PROVIDER = "Sector news"

# Topic searches over the industry's news, per RPG company: the events that make a company buyable.
SCOUT_QUERIES = {
    "ZENSAR": ["IT services company acquisition", "IT services firm funding round", "IT company stake sale",
               "IT services company layoffs", "mid-size IT company wins contract", "digital engineering company"],
    "CEAT": ["tyre company acquisition", "tyre maker stake sale", "tyre manufacturer funding", "rubber products company"],
    "KEC": ["EPC company stake sale", "transmission tower company", "EPC firm insolvency", "power transmission company acquisition"],
    "RPGLS": ["pharma company stake sale", "small pharma company acquisition", "API manufacturer funding"],
    "RAYCHEM": ["cable accessories company", "electrical components company stake sale", "switchgear company acquisition"],
    "HARRISONS": ["tea estate sale", "plantation company stake sale", "rubber plantation company"],
}

EVENTS = {"fund_raise": "fund_raise", "stake_sale": "stake_selldown", "distress": "press_distress", "growth": "press_opportunity",
          "leadership": "leadership_churn", "legal": "legal_action", "deal": "deal_activity"}

SYSTEM = """You scout acquisition targets for an RPG Group company's Corporate Strategy team, from this week's news about its industry.
From the numbered news items, pick up to {n} real companies named in them that the RPG company could plausibly buy, most promising first: smaller companies raising money, selling a stake, in distress, changing leaders, winning business or doing deals in the RPG company's segment or the target profile.
Never pick: a large or listed company near or above the RPG company's size, a market leader, the RPG company itself or another RPG Group company, a company already agreed to be bought by someone else, a government body, an investor or fund, or a news or data site.
Use only companies named in the items you cite; write each name as the company is usually called.
event: what the news says happened to the company (fund_raise, stake_sale, distress, growth, leadership, legal, deal). why: one short, neutral sentence on why it could interest the RPG company, from the items.
size_hint: only a size the items state (revenue, valuation, employees), else null.
scale: small, mid or large, from what you know of the company and the items; large = a large listed company, a bank, insurer, utility, oil or power major, conglomerate, or anything near the RPG company's size; unknown if you cannot tell.
segment: same (it does what the RPG company does), adjacent (supplies it, buys from it, or a neighbouring line of business it could add), or unrelated.
acquired: true when the items say another company is buying or has bought it.
Picks that are large, unrelated or acquired are discarded, so only pick companies you would class as small or mid, same or adjacent, and not acquired."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["companies"],
          "properties": {"companies": {"type": "array", "items": {
              "type": "object", "additionalProperties": False,
              "required": ["name", "event", "why", "size_hint", "scale", "segment", "acquired", "items"],
              "properties": {"name": {"type": "string"}, "event": {"type": "string", "enum": list(EVENTS)},
                             "scale": {"type": "string", "enum": ["small", "mid", "large", "unknown"]},
                             "segment": {"type": "string", "enum": ["same", "adjacent", "unrelated"]},
                             "acquired": {"type": "boolean"},
                             "why": {"type": "string"}, "size_hint": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                             "items": {"type": "array", "items": {"type": "integer"}}}}}}}


class ScoutError(Exception):
    pass


def news(code: str, transport=None) -> tuple[list[dict], list[str]]:
    """Blocking: the last NEWS_DAYS of the industry's news for one RPG company (GNews, else Tavily news)."""
    since = datetime.utcnow() - timedelta(days=NEWS_DAYS)

    def read(q: str) -> list[dict]:
        try:
            found = company_research.headlines(q, transport, since, exact=False, kind="sector_news")
            if found:
                return found
        except SourceError:
            pass  # GNews refused or has no key: Tavily news below
        return company_research.tavily_news(q, transport, NEWS_DAYS, None, "sector_news")

    facts, errors = company_research._run([("News", lambda q=q: read(q)) for q in SCOUT_QUERIES.get(code, [])], PROFILES[code][0])
    # one copy of each story (several outlets carry the same one), newest first
    return company_research._dedupe(facts, "")[:MAX_ITEMS], errors


def pick(code: str, items: list[dict], acquirer: dict | None, drafter=None) -> tuple[list[dict], str]:
    """Blocking: the companies in the news the RPG company could buy, grounded in the items they cite."""
    from agents.target_discovery import TARGET_PROFILES

    full, seg = PROFILES[code]
    if not items:
        return [], "", []
    try:
        drafter = drafter or Drafter(routes=thesis_routes())
    except LLMError as e:
        raise ScoutError(str(e))
    own = {m: ((acquirer or {}).get(m) or {}).get("cr") for m in ("market_cap", "revenue")}
    profile = TARGET_PROFILES.get(code)
    brief = (f"RPG company: {full}\nSegment: {seg}\nIts size: market cap ₹{own['market_cap'] or '?'} cr, revenue ₹{own['revenue'] or '?'} cr"
             + (f"\nTarget profile: {profile['what']}; {profile['size']}; in {profile['where']}." if profile else ""))
    listing = "\n".join(f"[{i}] {(f.get('observed_at') or '')[:10]} · {f['source']} · {f['text'][:400]}" for i, f in enumerate(items, 1))
    try:
        picks = json.loads(drafter.draft(SYSTEM.replace("{n}", str(MAX_PICKS)),
                                         [{"role": "user", "content": f"{brief}\n\nNews items:\n{listing}"}], SCHEMA, "scout"))["companies"]
    except LLMError as e:
        raise ScoutError(str(e))
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ScoutError(f"Could not read the picks from the model: {e}")
    out, names, dropped = [], [], []
    for p in picks:
        name = re.sub(r"\s+", " ", p["name"]).strip(" .")
        cited = [items[i - 1] for i in dict.fromkeys(p["items"]) if 1 <= i <= len(items)]
        # named in a headline, not only somewhere in a snippet
        named = [f for f in cited if any(about(n, f.get("title") or f["text"]) for n in (name, short_name(name)))]
        if not name or not named or any(same_company(name, n) for n in names) or any(g.lower() in name.lower() for g in GROUP):
            continue
        if p.get("scale") == "large" or p.get("segment") == "unrelated" or p.get("acquired"):
            why = "large" if p.get("scale") == "large" else "unrelated" if p.get("segment") == "unrelated" else "being acquired"
            dropped.append(f"{name} ({why})")
            continue
        names.append(name)
        out.append({"name": name, "event": p["event"], "why": p["why"].strip(), "size_hint": (p.get("size_hint") or "").strip() or None,
                    "segment": p.get("segment"), "items": named})
        if len(out) == MAX_PICKS:
            break
    return out, drafter.model, dropped


async def scan(db: AsyncSession, reviewer=None, codes: list[str] | None = None, drafter=None, transport=None) -> dict:
    """Read each RPG company's industry news, pick the companies in it it could buy, size them, and add
    them (or match them to watched ones) with the news as their signals."""
    from services.ingest import recompute_cluster_for_entity

    subs = [(s.code, list(s.sectors or [])) for s in (await db.execute(select(Subsidiary).order_by(Subsidiary.code))).scalars().all()
            if s.code in SCOUT_QUERIES and (not codes or s.code in codes)]
    known = [(e.id, e.name) for e in (await db.execute(select(Entity))).scalars().all()]
    acquirers = {code: await state_store.load(db, company_size.rpg_key(code)) for code, _ in subs}
    await db.rollback()  # end the read transaction: the searches and the model take minutes
    found: list[tuple[str, list[str], dict, str, dict | None, int | None]] = []  # (code, sectors, pick, model, size, existing id)
    errors, read, unsized, dropped = [], {}, [], []
    for code, sectors in subs:
        try:
            items, errs = await asyncio.to_thread(news, code, transport)
            errors += errs
            read[code] = len(items)
            picks, model, gone = await asyncio.to_thread(pick, code, items, acquirers.get(code), drafter)
            dropped += [f"{code}: {g}" for g in gone]
        except ScoutError as e:
            errors.append(f"{code}: {e}")
            continue
        for p in picks:
            existing = next((i for i, n in known if same_company(n, p["name"])), None)
            size = None
            if existing is None:
                try:
                    size = await asyncio.to_thread(company_size.lookup, p["name"], False, transport)
                except Exception as ex:  # noqa: BLE001 — no sourced figure: shown as "Size not verified", never a guess
                    errors.append(f"size of {p['name']}: {ex}")
                    unsized.append(p["name"])
                known.append((-1, p["name"]))
            found.append((code, sectors, p, model, size, existing))

    added, matched, too_big, signals = [], [], [], 0
    all_subs = (await db.execute(select(Subsidiary))).scalars().all()
    now = datetime.utcnow()
    for code, sectors, p, model, size, existing in found:  # one short write at the end
        if existing is not None:
            e = await db.get(Entity, existing)
            if e is None or e.status == "dismissed":
                continue
            matched.append(e.name)
        else:
            f = company_size.fit(size, acquirers.get(code))
            info = {"for": code, "kind": "target", "found_via": "sector news", "why": p["why"], "model": model,
                    "sources": [{"title": x.get("title") or x["text"][:120], "url": x["url"]} for x in p["items"] if x.get("url")],
                    "found_at": now.isoformat(timespec="seconds"), **({"size_hint": p["size_hint"]} if p["size_hint"] else {})}
            if f["ok"] is False:
                info["set_aside"] = f"Too large to acquire: {f['label']}"
            e = Entity(name=p["name"], sectors=sectors, category=f"Target · {PROFILES[code][1]}", origin="discovered",
                       status="dismissed" if f["ok"] is False else "watching", role="target", watched_since=now, discovery=info)
            db.add(e)
            await db.flush()
            if size:
                await state_store.save(db, company_size.entity_key(e.id), size)
            if f["ok"] is False:
                too_big.append(e.name)
                continue
            added.append(e.name)
        have = {r.headline for r in (await db.execute(select(RawSignal).where(RawSignal.entity_id == e.id))).scalars().all()}
        for x in p["items"]:
            title = (x.get("title") or x["text"])[:500]
            if title in have:
                continue
            have.add(title)
            when = datetime.fromisoformat(x["observed_at"]) if x.get("observed_at") else now
            db.add(RawSignal(entity_id=e.id, signal_type=EVENTS[p["event"]], source_type="news", headline=title,
                             source_excerpt=f"{PROVIDER} · {x['source']}", source_url=x.get("url") or "", provider=PROVIDER,
                             observed_at=when, created_at=now))
            signals += 1
        await db.flush()
        await recompute_cluster_for_entity(db, e, all_subs)
    await db.commit()
    result = {"read": read, "added": added, "matched": matched, "too_big": too_big, "not_sized": unsized, "dropped": dropped, "signals": signals, "errors": errors[:20]}
    await write_audit(db, reviewer, "sector_scout", "entity",
                      detail=f"added={len(added)} matched={len(matched)} too_big={len(too_big)} signals={signals} errors={len(errors)}")
    return result
