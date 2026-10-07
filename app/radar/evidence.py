"""The numbered evidence the radar's agents and Ask Radar may cite for one RPG company. Each item:
{id, case_id, date, source, text, origin, url}. Origin "self" is public research on the RPG company
itself (services/company_research.py: results, shareholding, web and news); origin "live" is a
watched company's signal fetched by the repo's connectors, tied to that company's case; origin
"daily" is a finding of the daily Opportunity Analyst that a user kept. Which of them a company's
evidence includes follows its SWOT parameters (services/swot_settings.py)."""
from __future__ import annotations

from datetime import datetime

from services import swot_settings
from services.company_research import usable

from .store import STORE

ORIGIN_LABEL = {"live": "Live", "self": "About the company", "daily": "Daily finding"}


def rival_names(co: str) -> list[str]:
    return [r["name"] for r in STORE.rivals.get(co, [])]


def settings(co: str) -> dict:
    from .bridge import CO_TO_CODE  # imported here: bridge imports this package's store first

    return STORE.swot_settings.get(co) or swot_settings.defaults(CO_TO_CODE[co])


def _day(iso: str | None, fallback: str) -> str:
    return datetime.fromisoformat(iso).strftime("%d %b %Y") if iso else fallback


def research(co: str) -> list[dict]:
    """Facts about the company itself, from its ticked sources."""
    r = STORE.research.get(co) or {}
    kinds = set(settings(co)["sources"])
    retrieved = f"retrieved {_day(r.get('at'), '')}".strip()
    return [{"case_id": None, "date": _day(f["observed_at"], retrieved), "source": f["source"], "text": f["text"],
             "origin": "self", "url": f.get("url")} for f in r.get("facts") or [] if usable(f) and f["kind"] in kinds]


def daily(co: str) -> list[dict]:
    """Findings of the last week a user kept (STORE.kept_findings, loaded by bridge.sync)."""
    if "daily" not in settings(co)["sources"]:
        return []
    return [{"case_id": None, "date": f["date"], "source": f["source"], "text": f"{f['kind'].capitalize()}: {f['title']}. {f['summary']}",
             "origin": "daily", "url": f.get("url")} for f in STORE.kept_findings.get(co, [])]


def registry(co: str) -> list[dict]:
    live = [{"case_id": f"r{x['entity_id']}", "date": x["date"], "source": x["source"], "text": f"{x['company']}: {x['text']}",
             "origin": "live", "url": x.get("url")} for x in STORE.live.get(co, [])] if "watched" in settings(co)["sources"] else []
    raw = research(co) + daily(co) + live
    return [{"id": f"E{i}", **x} for i, x in enumerate(raw, 1)]


def cite(items: list[dict]) -> list[dict]:
    """The shape the screen shows for a source."""
    return [{"id": x["id"], "text": x["text"], "source": x["source"], "date": x["date"], "url": x.get("url"),
             "origin": x["origin"], "origin_label": ORIGIN_LABEL[x["origin"]]} for x in items]
