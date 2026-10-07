"""Watchlist discovery agent: which real companies each subsidiary should watch.

For every subsidiary: two Tavily web searches
(direct competitors; adjacent players in its signal focus), a reasoning model
picks up to 5 companies from those results, and only names that actually
appear in the results it cites are kept (a grounding check, so the model
cannot add a company from memory). The model picks names only — it never
scores anything.

New companies are watched at once (``status="watching"``) and ingested from
the next run. A company someone removed (``dismissed``) is never re-added.
Weekly re-runs (services/scheduler.py)
refresh ``discovery.last_seen_at`` on companies found again, so a stale
watchlist entry is visible."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_routes import Drafter, LLMError
from db.models import Entity, Subsidiary
from ingestion.connectors.live.common import about, get_json, same_company
from services.audit import write_audit
from shared.config import get_settings
from shared.http import client

TAVILY_URL = "https://api.tavily.com/search"
MAX_PER_SUBSIDIARY = 5

# How each subsidiary is known on the web, and the segment its peers work in.
PROFILES = {
    "CEAT": ("CEAT Limited", "tyres"),
    "KEC": ("KEC International", "power transmission EPC"),
    "ZENSAR": ("Zensar Technologies", "IT services"),
    "RPGLS": ("RPG Life Sciences", "pharmaceuticals"),
    "RAYCHEM": ("Raychem RPG", "cable accessories and power products"),
    "HARRISONS": ("Harrisons Malayalam", "tea and rubber plantations"),
}
GROUP = ["RPG", "CEAT", "KEC International", "Zensar", "Raychem", "Harrisons Malayalam"]

SYSTEM = """You pick the companies an RPG Group subsidiary's Corporate Strategy team should watch, from web search results.
Pick up to 5 real companies, most relevant first: direct competitors (same products or services, same customers, India first) and adjacent players named in the team's focus.
Use only companies named in the results. Write each name as the company is usually called (e.g. "Apollo Tyres", not "Apollo"), and cite the result numbers that name it.
Never list the subsidiary itself, another RPG Group company, a conglomerate whose main business is elsewhere, or a data or news site.
kind: "competitor" or "adjacent". why: one short, neutral sentence on how it relates to the subsidiary, from the results."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["companies"],
          "properties": {"companies": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["name", "kind", "why", "results"],
              "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": ["competitor", "adjacent"]},
                             "why": {"type": "string"}, "results": {"type": "array", "items": {"type": "integer"}}}}}}}


class DiscoveryError(Exception):
    pass


def _search(query: str, key: str, transport=None) -> list[dict]:
    body = {"query": query, "topic": "general", "max_results": 6, "search_depth": "advanced", "chunks_per_source": 3}
    with client(transport, timeout=60.0) as c:
        r = c.post(TAVILY_URL, headers={"Authorization": f"Bearer {key}"}, json=body)
    return [x for x in get_json(r, "Tavily").get("results") or [] if x.get("title")]


def _grounded(name: str, results: list[dict], cited: list[int]) -> bool:
    """The name, or its first word when that is distinctive, appears in a cited result."""
    text = " ".join(f"{results[i - 1]['title']} {results[i - 1].get('content', '')}" for i in cited if 1 <= i <= len(results))
    first = name.split()[0]
    return about(name, text) or (len(first) >= 4 and about(first, text))


def find_companies(code: str, focus: str, drafter: Drafter | None = None, transport=None) -> tuple[list[dict], str]:
    """Blocking: search, pick, ground. Returns (companies, model name)."""
    key = get_settings().tavily_api_key
    if not key:
        raise DiscoveryError("TAVILY_API_KEY is not set.")
    full, seg = PROFILES.get(code, (code, ""))
    results = _search(f"{full} competitors India {seg}", key, transport) + _search(f"India {seg} companies {focus}", key, transport)
    seen, uniq = set(), []
    for x in results:
        if x.get("url") not in seen:
            seen.add(x.get("url"))
            uniq.append(x)
    if not uniq:
        raise DiscoveryError(f"No search results for {full}.")
    listing = "\n".join(f"[{i}] {x['title']}\n{(x.get('content') or '')[:700]}" for i, x in enumerate(uniq, 1))
    drafter = drafter or Drafter(transport=transport)
    try:
        text = drafter.draft(SYSTEM, [{"role": "user", "content": f"Subsidiary: {full}\nSegment: {seg}\nTeam focus: {focus}\n\nSearch results:\n{listing}"}],
                             SCHEMA, "watchlist")
        picks = json.loads(text)["companies"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise DiscoveryError(f"Could not read companies from the model: {e}")
    out, names = [], set()
    for p in picks:
        name = re.sub(r"\s+", " ", p["name"]).strip(" .")
        low = name.lower()
        if not name or low in names or any(g.lower() in low for g in GROUP) or not _grounded(name, uniq, p["results"]):
            continue  # a duplicate, the group itself, or a name the cited results do not contain
        names.add(low)
        out.append({"name": name, "kind": p["kind"], "why": p["why"].strip(),
                    "sources": [{"title": uniq[i - 1]["title"], "url": uniq[i - 1]["url"]}
                                for i in dict.fromkeys(p["results"]) if 1 <= i <= len(uniq)]})
        if len(out) == MAX_PER_SUBSIDIARY:
            break
    return out, drafter.model


async def discover(db: AsyncSession, reviewer=None, drafter: Drafter | None = None, transport=None) -> dict:
    """Run discovery for every subsidiary and add the companies it finds to the watchlist."""
    subs = (await db.execute(select(Subsidiary).order_by(Subsidiary.code))).scalars().all()
    # Matched by common.same_company, so "Apollo Tyres" matches "Apollo Tyres Ltd" and "Continental Tires".
    existing = list((await db.execute(select(Entity))).scalars().all())
    now = datetime.utcnow()
    added, refreshed, errors = [], [], []
    for sub in subs:
        try:
            found, model = await asyncio.to_thread(find_companies, sub.code, sub.signal_focus, drafter, transport)
        except (DiscoveryError, LLMError, httpx.HTTPError) as e:  # one subsidiary failing does not stop the rest
            errors.append(f"{sub.code}: {e}")
            continue
        for c in found:
            info = {"for": sub.code, "kind": c["kind"], "why": c["why"], "sources": c["sources"],
                    "last_seen_at": now.isoformat(timespec="seconds"), "model": model}
            e = next((x for x in existing if same_company(x.name, c["name"])), None)
            if e is not None:
                e.discovery = {**(e.discovery or {}), **info}  # status is left as is: dismissed stays dismissed
                refreshed.append(e.name)
                continue
            e = Entity(name=c["name"], sectors=list(sub.sectors or []),
                       category=f"{c['kind'].capitalize()} · {PROFILES.get(sub.code, ('', ''))[1]}",
                       origin="discovered", status="watching", watched_since=now,
                       discovery={**info, "found_at": now.isoformat(timespec="seconds")})
            db.add(e)
            existing.append(e)
            added.append(e.name)
    await db.commit()
    result = {"subsidiaries": [s.code for s in subs], "added": added, "refreshed": refreshed, "errors": errors}
    await write_audit(db, reviewer, "watchlist_discovery", "entity",
                      detail=f"subsidiaries={','.join(result['subsidiaries'])} added={len(added)} refreshed={len(refreshed)} errors={len(errors)}")
    return result
