"""How big a company is — so the radar only proposes acquisition targets an RPG company could
plausibly buy. Market capitalisation (listed companies) and annual revenue (any company), in ₹
crore, each read from a Tavily search answer and kept with that answer and its first source link
so the figure can be checked. No model of our own is involved; nothing here is a valuation.

Search answers are sometimes wrong (a revenue ten times too high, a market cap for an unlisted
company), so each figure is asked for twice, in different words, and kept only when the two answers
agree within AGREE; a market cap is dropped when the answer says the company is not listed; and a
market cap and revenue that cannot both be true (MAX_MCAP_TO_REVENUE) are both set aside. A figure
set aside is kept with the reason ("conflict") and the company counts as not verified.

A target fits an RPG company when it is at most FIT_RATIO of the company's size, compared on market
cap when both have one, else on revenue. Sizes are kept in ConnectorState rows
(``size:entity:<id>``, ``size:rpg:<code>``) and refreshed after REFRESH_DAYS."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.connectors.live.common import SourceError, get_json
from services import state as state_store
from shared.config import get_settings
from shared.http import client

FIT_RATIO = 0.5
AGREE = 0.35  # two answers agree when they differ by at most this share of the larger
MAX_MCAP_TO_REVENUE = 60  # market cap / revenue beyond this (or below its inverse) is not credible
UNLISTED = re.compile(r"\b(?:private(?:ly held)?|unlisted|not (?:publicly )?listed|not publicly traded|no market cap)", re.I)
REFRESH_DAYS = 30
TAVILY_URL = "https://api.tavily.com/search"
# "₹10,328.80 Cr", "Rs. 405,920 crore", "INR 1250-1500 crore", "₹4.06 lakh crore"
AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]+(?:\.\d+)?)(?:\s*[-–]\s*[\d,.]+)?\s*(lakh\s*crore|l\s*cr|crores?|cr)\b", re.I)


# "over ₹1,000 crore", "less than ₹100 crore": a bound, not the figure
HEDGE = re.compile(r"(?:over|above|more than|exceed\w*|at least|nearly|almost|around|under|below|less than|up to|upto)\s*$", re.I)


def amount_cr(text: str) -> float | None:
    """The first rupee amount in crore in a text that is not a bound ("over ₹1,000 crore"), or None."""
    for m in AMOUNT.finditer(text or ""):
        if HEDGE.search(text[max(0, m.start() - 20): m.start()]):
            continue
        value = float(m.group(1).replace(",", ""))
        return value * 100000 if m.group(2).lower().startswith("l") else value
    return None


def _answer(query: str, transport=None) -> tuple[str, str | None]:
    """Tavily's sourced answer. There is no fallback: a search snippet is not a sourced figure, so when
    Tavily is down the company is reported as not sized (services/web_search.py)."""
    from services import web_search

    key = get_settings().tavily_api_key
    if not key:
        raise SourceError("TAVILY_API_KEY is not set.")
    if web_search.tavily_down() and transport is None:
        raise SourceError("Tavily is unavailable today (credits used up or key refused), so sizes are not checked.")
    with client(transport, timeout=60.0) as c:
        r = c.post(TAVILY_URL, headers={"Authorization": f"Bearer {key}"},
                   json={"query": query, "include_answer": "basic", "max_results": 3, "topic": "general"})
    try:
        body = get_json(r, "Tavily")
    except SourceError as e:
        web_search.tavily_failed(e)
        raise
    return body.get("answer") or "", next((x.get("url") for x in body.get("results") or []), None)


QUERIES = {"market_cap": ["{} market capitalisation in crore", "{} share price market cap today in rupees crore"],
           "revenue": ["{} annual revenue in crore", "{} revenue from operations last financial year in crore"]}
# Asked only when the first two disagree: a figure two of the three answers agree on is kept.
TIEBREAK = {"market_cap": "{} current market cap Rs crore NSE BSE", "revenue": "{} total income annual report Rs crore"}


def agree(a: float, b: float) -> bool:
    return abs(a - b) <= AGREE * max(a, b)


def checked(answers: list[tuple[str, str | None]], metric: str) -> dict:
    """One figure from two answers: {cr, text, url, checks} when they agree (or only one has a figure),
    {cr: None, conflict, ...} when they disagree or a market cap answer says the company is unlisted."""
    (text, url), vals = answers[0], [amount_cr(t) for t, _ in answers]
    out = {"cr": None, "text": text[:300], "url": url}
    if metric == "market_cap" and any(UNLISTED.search(t) for t, _ in answers):
        return {**out, "conflict": "The search answer says it is not listed."}
    got = [v for v in vals if v]
    if not got:
        return out
    pair = next(((a, b) for i, a in enumerate(got) for b in got[i + 1:] if agree(a, b)), None)
    if pair:
        return {**out, "cr": pair[0], "checks": 2}
    if len(got) == 1:
        return {**out, "cr": got[0], "checks": 1}
    return {**out, "conflict": "The searches disagree: " + ", ".join(f"₹{v:,.0f} cr" for v in got) + "."}


def lookup(name: str, listed: bool, transport=None) -> dict:
    """Blocking: market cap (when listed) and revenue for one company, each asked twice."""
    out: dict = {"at": datetime.now().isoformat(timespec="seconds")}
    for metric in (["market_cap"] if listed else []) + ["revenue"]:
        answers = [_answer(q.format(name), transport) for q in QUERIES[metric]]
        out[metric] = checked(answers, metric)
        if "disagree" in out[metric].get("conflict", ""):
            out[metric] = checked(answers + [_answer(TIEBREAK[metric].format(name), transport)], metric)
    m, r = (out.get("market_cap") or {}).get("cr"), (out.get("revenue") or {}).get("cr")
    if m and r and not 1 / MAX_MCAP_TO_REVENUE <= m / r <= MAX_MCAP_TO_REVENUE:
        why = f"Market cap ₹{m:,.0f} cr and revenue ₹{r:,.0f} cr cannot both be right."
        for k in ("market_cap", "revenue"):
            out[k] = {**out[k], "cr": None, "conflict": why}
    return out


def fit(target: dict | None, acquirer: dict | None) -> dict:
    """{ok, ratio, metric, label}: ok is True when the target is at most FIT_RATIO of the acquirer's size,
    False when larger, None when it cannot be told (a size missing)."""
    get = lambda d, m: ((d or {}).get(m) or {}).get("cr")
    name = {"market_cap": "Market cap", "revenue": "Revenue"}
    for metric in ("market_cap", "revenue"):
        t, a = get(target, metric), get(acquirer, metric)
        if t and a:
            return {"ok": t / a <= FIT_RATIO, "ratio": round(t / a, 2), "metric": metric,
                    "label": f"{name[metric]} ₹{t:,.0f} cr · {t / a:.0%} of the RPG company's"}
    known = next(((m, get(target, m)) for m in ("market_cap", "revenue") if get(target, m)), None)
    unclear = any(((target or {}).get(m) or {}).get("conflict") for m in ("market_cap", "revenue"))
    return {"ok": None, "ratio": None, "metric": known[0] if known else None,
            "label": f"{name[known[0]]} ₹{known[1]:,.0f} cr · not compared" if known
            else "Size unclear: the sources disagree" if unclear else "Size not verified"}


def due(saved: dict) -> bool:
    return not saved.get("at") or datetime.now() - datetime.fromisoformat(saved["at"]) >= timedelta(days=REFRESH_DAYS)


def entity_key(entity_id: int) -> str:
    return f"size:entity:{entity_id}"


def rpg_key(code: str) -> str:
    return f"size:rpg:{code}"


async def refresh_due(db: AsyncSession, limit: int = 10, transport=None) -> list[str]:
    """Look up the size of the RPG companies and watched companies that have none or a stale one,
    at most ``limit`` lookups a run. Returns the names done."""
    from db.models import Entity
    from services.company_research import PROFILES
    from sqlalchemy import select

    todo = [(rpg_key(code), full, symbol is not None) for code, (full, _, symbol) in PROFILES.items()]
    todo += [(entity_key(e.id), e.name, bool(e.nse_symbol) or e.role == "competitor")
             for e in (await db.execute(select(Entity).where(Entity.status == "watching"))).scalars().all()]
    done = []
    for key, name, listed in todo:
        if len(done) >= limit:
            break
        if not due(await state_store.load(db, key)):
            continue
        try:
            size = await asyncio.to_thread(lookup, name, listed, transport)
        except SourceError:
            break  # no key or quota: try again next run
        await state_store.save(db, key, size)
        await db.commit()
        done.append(name)
    return done


def with_fincrux(sizes: dict[str, dict], symbols: dict[str, str | None], live: dict) -> dict[str, dict]:
    """Sizes with Fincrux's market cap (the exchange figure) in place of a search answer's, for every listed
    company Fincrux has been asked about. ``symbols``: size key -> NSE symbol."""
    from services.market_data import _figure

    fin = (live.get("market") or {}).get("fin") or {}
    out = dict(sizes)
    for key, sym in symbols.items():
        cap = _figure(((fin.get((sym or "").upper()) or {}).get("top") or {}).get("Market Cap")) if sym else None
        if cap:
            out[key] = {**out.get(key, {}), "market_cap": {"cr": cap, "text": f"Market cap ₹{cap:,.0f} crore (Fincrux, exchange data)",
                                                           "url": None, "source": "Fincrux"}}
    return out


async def load_all(db: AsyncSession) -> dict[str, dict]:
    """Every stored size, by key."""
    from db.models import ConnectorState
    from sqlalchemy import select

    rows = (await db.execute(select(ConnectorState).where(ConnectorState.key.like("size:%")))).scalars().all()
    return {r.key: dict(r.value) for r in rows}
