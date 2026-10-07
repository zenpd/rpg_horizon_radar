"""Target Discovery agent: which smaller companies each RPG company could acquire.

Watchlist discovery (agents/watchlist_discovery.py) finds competitors; most are too big to buy.
This agent looks for acquisition targets instead: for each RPG company, web searches for smaller
players in its segment, for distress or stake-sale situations, and for each acquisition thesis the
team saved for it; a model picks up to MAX_PER_COMPANY smaller companies from the results, and only
names that appear in the results it cites are kept (the same grounding check). Each is added to the
watchlist with role "target", then sized (services/company_size.py): a target that turns out larger
than half the RPG company is set aside (dismissed) with the reason. Runs with the weekly discovery
(services/scheduler.py), or on demand."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.llm_routes import Drafter, LLMError
from agents.watchlist_discovery import GROUP, PROFILES, DiscoveryError, _grounded, _search
from db.models import Entity, Subsidiary
from ingestion.connectors.live.common import same_company
from services import company_size
from services import state as state_store
from services.audit import write_audit
from shared.config import get_settings

MAX_PER_COMPANY = 5

SYSTEM = """You find acquisition targets for an RPG Group company's Corporate Strategy team, from web search results.
Pick up to 5 real companies the RPG company could plausibly buy, most relevant first: smaller players in its segment or in the focus areas given, companies in distress or whose promoters are selling stakes, and companies matching the team's acquisition theses.
Never pick: a market leader or large listed company (anything near or above the RPG company's size), the RPG company itself or another RPG Group company, a conglomerate, a foreign multinational, or a data or news site.
Use only companies named in the results; write each name as the company is usually called, and cite the result numbers that name it.
why: one short, neutral sentence on why it could be a target (size, fit, situation), from the results."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["companies"],
          "properties": {"companies": {"type": "array", "items": {
              "type": "object", "additionalProperties": False, "required": ["name", "why", "results"],
              "properties": {"name": {"type": "string"}, "why": {"type": "string"},
                             "results": {"type": "array", "items": {"type": "integer"}}}}}}}


def queries(code: str, focus: str, theses: list[str]) -> list[str]:
    full, seg = PROFILES.get(code, (code, ""))
    return ([f"small {seg} companies India acquisition target", f"India {seg} company promoter stake sale OR distress OR for sale"]
            + [f"{t} India company" for t in theses[:2]] + ([f"India {focus}"] if focus else []))[:4]


def find(code: str, focus: str, theses: list[str], drafter: Drafter | None = None, transport=None) -> tuple[list[dict], str]:
    """Blocking: search, pick, ground. Returns (targets, model name)."""
    key = get_settings().tavily_api_key
    if not key:
        raise DiscoveryError("TAVILY_API_KEY is not set.")
    full, seg = PROFILES.get(code, (code, ""))
    seen, results = set(), []
    for q in queries(code, focus, theses):
        for x in _search(q, key, transport):
            if x.get("url") not in seen:
                seen.add(x.get("url"))
                results.append(x)
    if not results:
        raise DiscoveryError(f"No search results for {full}'s targets.")
    listing = "\n".join(f"[{i}] {x['title']}\n{(x.get('content') or '')[:600]}" for i, x in enumerate(results, 1))
    drafter = drafter or Drafter(transport=transport)
    brief = f"RPG company: {full}\nSegment: {seg}\nFocus: {focus}\nAcquisition theses: {'; '.join(theses) or 'none saved'}"
    try:
        picks = json.loads(drafter.draft(SYSTEM, [{"role": "user", "content": f"{brief}\n\nSearch results:\n{listing}"}], SCHEMA, "targets"))["companies"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise DiscoveryError(f"Could not read targets from the model: {e}")
    out, names = [], []
    for p in picks:
        name = re.sub(r"\s+", " ", p["name"]).strip(" .")
        if not name or any(same_company(name, n) for n in names) or any(g.lower() in name.lower() for g in GROUP) or not _grounded(name, results, p["results"]):
            continue
        names.append(name)
        out.append({"name": name, "why": p["why"].strip(),
                    "sources": [{"title": results[i - 1]["title"], "url": results[i - 1]["url"]} for i in dict.fromkeys(p["results"]) if 1 <= i <= len(results)]})
        if len(out) == MAX_PER_COMPANY:
            break
    return out, drafter.model


async def discover(db: AsyncSession, reviewer=None, drafter: Drafter | None = None, transport=None) -> dict:
    """Find targets for every RPG company, add new ones to the watchlist as role "target", size them,
    and set aside the ones too big to buy."""
    from radar.bridge import CODE_TO_CO
    from radar.store import STORE

    # plain values: the rollback below expires the ORM rows
    subs = [(s.code, s.signal_focus, list(s.sectors or [])) for s in (await db.execute(select(Subsidiary).order_by(Subsidiary.code))).scalars().all()]
    known = [e.name for e in (await db.execute(select(Entity))).scalars().all()]
    acquirers = {code: await state_store.load(db, company_size.rpg_key(code)) for code, _, _ in subs}
    await db.rollback()  # end the read transaction: the searches and lookups below take minutes
    now = datetime.utcnow()
    added, refreshed, too_big, errors = [], [], [], []
    new: list[tuple[str, list[str], dict, str, dict | None]] = []  # (company code, sectors, target, model, size)
    for code, focus, sectors in subs:
        theses = [t["text"] for t in STORE.theses if t.get("desk") == CODE_TO_CO.get(code)]
        try:
            found, model = await asyncio.to_thread(find, code, focus, theses, drafter, transport)
        except (DiscoveryError, LLMError, httpx.HTTPError) as e:  # one company failing does not stop the rest
            errors.append(f"{code}: {e}")
            continue
        for t in found:
            if any(same_company(t["name"], k) for k in known):
                refreshed.append(t["name"])
                continue
            known.append(t["name"])
            try:
                size = await asyncio.to_thread(company_size.lookup, t["name"], False, transport)
            except Exception as ex:  # noqa: BLE001 — an unsized target stays, shown as not verified
                errors.append(f"size of {t['name']}: {ex}")
                size = None
            new.append((code, sectors, t, model, size))
    for code, sectors, t, model, size in new:  # one short write at the end
        f = company_size.fit(size, acquirers.get(code))
        info = {"for": code, "kind": "target", "why": t["why"], "sources": t["sources"], "model": model,
                "found_at": now.isoformat(timespec="seconds"), "last_seen_at": now.isoformat(timespec="seconds")}
        if f["ok"] is False:
            info["set_aside"] = f"Too large to acquire: {f['label']}"
        e = Entity(name=t["name"], sectors=sectors, category=f"Target · {PROFILES.get(code, ('', ''))[1]}",
                   origin="discovered", status="dismissed" if f["ok"] is False else "watching", role="target",
                   watched_since=now, discovery=info)
        db.add(e)
        await db.flush()
        if size:
            await state_store.save(db, company_size.entity_key(e.id), size)
        (too_big if f["ok"] is False else added).append(e.name)
    await db.commit()
    result = {"subsidiaries": [code for code, _, _ in subs], "added": added, "refreshed": refreshed, "too_big": too_big, "errors": errors}
    await write_audit(db, reviewer, "target_discovery", "entity",
                      detail=f"added={len(added)} too_big={len(too_big)} refreshed={len(refreshed)} errors={len(errors)}")
    return result
