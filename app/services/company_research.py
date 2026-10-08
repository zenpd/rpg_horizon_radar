"""Public research on the RPG companies themselves — the evidence the SWOT Analyst
(agents/swot_analyst.py) needs for strengths and weaknesses. The watched-company
connectors keep only events the scoring rules weigh; a SWOT also needs plain
facts, good and bad, so this collects them as they are:

Fincrux   the latest quarter's sales, net profit and margin against a year
          earlier, the last four quarters against the four before, and the
          shareholding pattern (listed companies only; shares the connectors'
          5-calls-a-day budget in the ``live`` state).
Tavily    web results on the company for each analysis factor ticked in its SWOT
          parameters (services/swot_settings.py), and the last 30 days of news
          naming it.
GNews     the latest headlines naming it.

Which of these run follows the company's ticked sources. No model is involved and
nothing is scored. Facts are kept per company in the ``research:<code>``
ConnectorState row, refreshed weekly by the SWOT run; one failing source never
stops the others.

daily_news() gathers the last two days of news for the Opportunity Analyst
(agents/opportunity_analyst.py): about the company, its watched companies and
its sector searches."""
from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.connectors.live.common import SourceError, about, clip, get_json, naive_utc, num
from ingestion.connectors.live.filings import Fincrux
from ingestion.connectors.live.news import GNews
from services import state as state_store
from services import swot_settings, web_search
from shared.config import get_settings
from shared.http import client

REFRESH_DAYS = 7
MAX_NEWS = 12  # per kind (news, web), after duplicates are dropped
MAX_WEB = 18
SAME_STORY = 0.6  # headline word overlap above which two stories are the same one
TAVILY_URL = "https://api.tavily.com/search"
GNEWS_URL = "https://gnews.io/api/v4/search"

# How each company is known: full name, the name headlines use, NSE symbol (None: not listed).
PROFILES = {
    "CEAT": ("CEAT Limited", "CEAT", "CEATLTD"),
    "KEC": ("KEC International", "KEC International", "KEC"),
    "ZENSAR": ("Zensar Technologies", "Zensar", "ZENSARTECH"),
    "RPGLS": ("RPG Life Sciences", "RPG Life Sciences", "RPGLIFE"),
    "RAYCHEM": ("Raychem RPG", "Raychem RPG", None),
    "HARRISONS": ("Harrisons Malayalam", "Harrisons Malayalam", "HARRMALAYA"),
}
DAILY_HOURS = 48  # how far back the daily news reaches (GNews' free plan runs 12 hours behind)
MAX_DAILY = 30
MAX_WATCHED_DAILY = 5
# Pages that are not a source for a company's position: social posts, scraped company profiles,
# document re-uploads, videos, and stock-tip and quote pages (daily price moves and ratings).
WEAK_SOURCES = re.compile(r"(?:^|\.)(?:instagram|facebook|linkedin|twitter|x|youtube|reddit|quora|rocketreach|leadiq|zoominfo|craft|"
                          r"scribd|slideshare|studocu|pinterest|investing|marketsmojo|univest|stockgro|sahi|kalkine|tijorifinance|"
                          r"moneyworks4me|screener|stockanalysis|multibagg|whalesbook|urbanacres|tradingview|stocktwits|"
                          r"allthinginfotech|builtin|cbinsights)\.", re.I)


def key(code: str) -> str:
    return f"research:{code}"


def usable(fact: dict) -> bool:
    """False for a fact from a weak source (WEAK_SOURCES), judged by its link or source name."""
    where = fact.get("url") and httpx.URL(fact["url"]).host or fact.get("source") or ""
    return not WEAK_SOURCES.search(f".{where.lower()}.")


def _fact(kind: str, text: str, source: str, when: datetime | None, url: str | None = None, title: str | None = None,
          factor: str | None = None) -> dict:
    """title: the story's headline, so the same story from two sources is kept once.
    factor: the analysis factor whose web search found it (services/swot_settings.FACTORS)."""
    return {"kind": kind, "text": clip(re.sub(r"\s+", " ", html.unescape(text)), 420), "source": source, "url": url or None,
            "observed_at": when.isoformat(timespec="seconds") if when else None, "title": title, "factor": factor}


# ---------- sources (blocking HTTP; run in a worker thread) ----------
def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.0f}%"


def _change(now, then) -> float | None:
    a, b = num(then), num(now)
    return None if not (a == a and b == b) or a == 0 else (b - a) / abs(a) * 100


def results(name: str, symbol: str, live_state: dict, transport=None) -> list[dict]:
    fx = Fincrux(live_state, transport)
    if not fx.configured:
        return []
    d = fx.get(f"financials/{symbol}")["data"]
    from services.market_data import health, health_text, keep_financials

    kept = keep_financials(live_state, symbol, d)  # for The financial market, at no extra call
    when = datetime.fromisoformat(d["last_updated_at"][:19]) if d.get("last_updated_at") else datetime.now()
    out = []
    q = {row[0]: row[1:] for row in d.get("quaterly_results") or []}  # sic, the API's spelling
    qs, sales, profit, opm = q.get("Category") or [], q.get("Sales") or [], q.get("Net Profit") or [], q.get("OPM %") or []
    if len(qs) >= 5 and len(sales) >= 5 and len(profit) >= 5:
        margin = f" Operating margin {opm[-1]} against {opm[-5]} a year earlier." if len(opm) >= 5 else ""
        out.append(_fact("results", f"{name} {qs[-1]} quarter: sales ₹{sales[-1]} cr ({_pct(_change(sales[-1], sales[-5]))} year on year), "
                                    f"net profit ₹{profit[-1]} cr ({_pct(_change(profit[-1], profit[-5]))} year on year).{margin}",
                         "Fincrux quarterly results", when))
    if len(qs) >= 8 and len(sales) >= 8 and len(profit) >= 8:
        s4, s8 = sum(num(x) for x in sales[-4:]), sum(num(x) for x in sales[-8:-4])
        p4, p8 = sum(num(x) for x in profit[-4:]), sum(num(x) for x in profit[-8:-4])
        out.append(_fact("results", f"{name} last four quarters ({qs[-4]} to {qs[-1]}): sales ₹{s4:,.0f} cr ({_pct(_change(s4, s8))} on the four before), "
                                    f"net profit ₹{p4:,.0f} cr ({_pct(_change(p4, p8))}).", "Fincrux quarterly results", when))
    s = {row[0]: row[1:] for row in d.get("shareholding_quarterly") or []}
    ss = s.get("Category") or []
    if len(ss) >= 2:
        parts = [f"{who} {v[-1]} ({v[-2]} a quarter earlier)" for who in ("Promoters", "FIIs", "DIIs", "Public")
                 if (v := s.get(who)) and len(v) >= 2]
        if parts:
            out.append(_fact("shareholding", f"{name} shareholding, {ss[-1]} quarter: " + ", ".join(parts) + ".",
                             "Fincrux shareholding pattern", when))
    if text := health_text(name, health(kept)):
        out.append(_fact("results", text, "Fincrux annual balance sheet", when))
    return out


def _tavily(body: dict, transport=None) -> list[dict]:
    """A Tavily search; DuckDuckGo answers it instead when Tavily refuses or has no key (services/web_search.py).
    A test transport always goes to Tavily."""
    if web_search.use_tavily() or transport is not None:
        try:
            with client(transport, timeout=60.0) as c:
                r = c.post(TAVILY_URL, headers={"Authorization": f"Bearer {get_settings().tavily_api_key}"}, json=body)
            return get_json(r, "Tavily").get("results") or []
        except SourceError as e:
            web_search.tavily_failed(e)
            if transport is not None or not web_search.enabled():
                raise
    if not web_search.enabled():
        return []
    return web_search.search(body)


def _host(url: str | None) -> str:
    return re.sub(r"^www\.", "", httpx.URL(url).host) if url else "web"


def _published(x: dict) -> datetime | None:
    """Tavily's RFC 2822 date, or DuckDuckGo's ISO 8601 one, as naive UTC."""
    v = x.get("published_date")
    if not v:
        return None
    try:
        return parsedate_to_datetime(v).astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return None


def web(full: str, query: str, factors: list[str], transport=None) -> list[dict]:
    """One basic web search (1 Tavily credit) per ticked analysis factor."""
    if not web_search.available():
        return []
    out = []
    for f in factors:
        for x in _tavily({"query": f"{full} {swot_settings.FACTORS[f][1]}", "topic": "general", "search_depth": "basic", "max_results": 5}, transport):
            title, content = (x.get("title") or "").strip(), (x.get("content") or "").strip()
            if about(query, f"{title} {content}"):
                out.append(_fact("web", f"{title}: {content}", _host(x.get("url")), _published(x), x.get("url"), title, f))
    return out


def tavily_news(query: str, transport=None, days: int = 30, must_name: str | None = None, kind: str = "news") -> list[dict]:
    if not web_search.available():
        return []
    out = []
    for x in _tavily({"query": f"{query} India", "topic": "news", "days": days, "max_results": 10}, transport):
        title = (x.get("title") or "").strip()
        if must_name is None or about(must_name, title):
            text = f"{title}: {x['content'].strip()}" if x.get("content") else title
            out.append(_fact(kind, text, x.get("source") or _host(x.get("url")), _published(x), x.get("url"), title))
    return out


def headlines(query: str, transport=None, since: datetime | None = None, exact: bool = True, kind: str = "news") -> list[dict]:
    """GNews headlines. exact: the query is a company name that must appear in the headline;
    otherwise it is a topic search (sector news)."""
    k = get_settings().gnews_api_key
    if not k:
        return []
    params = {"q": f'"{query}"' if exact else query, "lang": "en", "country": "in", "max": 10, "sortby": "publishedAt", "apikey": k}
    if since:
        params["from"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    with client(transport) as c:
        for _ in range(2):  # paced like the GNews connector (about one call a second), one retry after a 429
            wait = GNews._last + GNews.GAP - time.monotonic()
            if wait > 0 and not transport:
                time.sleep(wait)
            r = c.get(GNEWS_URL, params=params)
            GNews._last = time.monotonic()
            if r.status_code != 429:
                break
            if not transport:
                time.sleep(3)
        body = get_json(r, "GNews")
    if body.get("errors"):
        raise SourceError(f"GNews: {'; '.join(map(str, body['errors']))}")
    return [_fact(kind, f"{a['title']}" + (f": {a['description']}" if a.get("description") else ""),
                  (a.get("source") or {}).get("name") or "news", naive_utc(a["publishedAt"]), a.get("url"), a["title"])
            for a in body.get("articles") or [] if not exact or about(query, a.get("title"))]


def _run(steps: list[tuple[str, object]], label: str) -> tuple[list[dict], list[str]]:
    facts, errors = [], []
    for name, step in steps:
        try:
            facts += step()
        except (SourceError, httpx.HTTPError, KeyError, ValueError, TypeError) as e:
            errors.append(f"{name} · {label}: {e}")
    return facts, errors


def collect(code: str, live_state: dict, settings: dict | None = None, transport=None) -> tuple[list[dict], list[str]]:
    """Blocking: the ticked sources for one RPG company. Returns (facts, errors)."""
    full, query, symbol = PROFILES[code]
    return collect_company(full, query, symbol, live_state, settings or swot_settings.defaults(code), transport)


def collect_company(full: str, query: str, symbol: str | None, live_state: dict, settings: dict, transport=None) -> tuple[list[dict], list[str]]:
    """Blocking: the ticked sources for any company — an RPG company, or a target the Acquisition
    Thesis agent researches. Returns (facts, errors)."""
    src = set(settings["sources"])
    steps = []
    if symbol and src & {"results", "shareholding"}:
        steps.append(("Fincrux", lambda: [f for f in results(full, symbol, live_state, transport) if f["kind"] in src]))
    if "web" in src and settings["factors"]:
        steps.append(("Tavily", lambda: web(full, query, settings["factors"], transport)))
    if "news" in src:
        steps.append(("Tavily news", lambda: tavily_news(query, transport, must_name=query)))
        steps.append(("GNews", lambda: headlines(query, transport)))
    facts, errors = _run(steps, full)
    return _dedupe(facts, query), errors


def daily_news(code: str, settings: dict, watched: list[str], transport=None) -> tuple[list[dict], list[str]]:
    """Blocking: the last DAILY_HOURS of news for the Opportunity Analyst — about the company
    (kind company_news), its watched companies (watched_news) and its sector searches (sector_news).
    GNews first, paced; Tavily news when GNews has no key, refuses a call or finds nothing."""
    full, query, _ = PROFILES[code]
    since = datetime.utcnow() - timedelta(hours=DAILY_HOURS)
    gnews = bool(get_settings().gnews_api_key)

    def read(q: str, exact: bool, kind: str) -> list[dict]:
        if gnews:
            try:
                found = headlines(q, transport, since, exact, kind)
                if found or not web_search.available():
                    return found
            except SourceError:
                if not web_search.available():
                    raise
        return tavily_news(q, transport, 2, q if exact else None, kind)  # no GNews key, GNews refused, or found nothing

    steps = [("News", lambda q=q, exact=exact, kind=kind: read(q, exact, kind))
             for q, exact, kind in ([(query, True, "company_news")] + [(w, True, "watched_news") for w in watched[:MAX_WATCHED_DAILY]]
                                    + [(s, False, "sector_news") for s in settings["sector_queries"]])]
    facts, errors = _run(steps, full)
    recent = [f for f in facts if not f["observed_at"] or datetime.fromisoformat(f["observed_at"]) >= since]
    return _dedupe(recent, query)[:MAX_DAILY], errors


def _dedupe(facts: list[dict], query: str) -> list[dict]:
    own = _words(query)
    kept: list[tuple[dict, set[str]]] = []
    for f in filter(usable, facts):  # first copy of a story wins; results and shareholding come first
        words = _words(f["title"] or f["text"]) - own
        if not any(_same(words, w) for _, w in kept):
            kept.append((f, words))
    out = [f for f, _ in kept]
    newest = lambda kind, n: sorted((f for f in out if f["kind"] == kind), key=lambda f: f["observed_at"] or "", reverse=True)[:n]
    daily = sorted((f for f in out if f["kind"].endswith("_news")), key=lambda f: f["observed_at"] or "", reverse=True)
    return [f for f in out if f["kind"] in ("results", "shareholding")] + newest("news", MAX_NEWS) + newest("web", MAX_WEB) + daily


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 or any(ch.isdigit() for ch in w)}


def _same(a: set[str], b: set[str]) -> bool:
    """Two headlines tell the same story: most words of the shorter one are in the other
    ('CEAT expands Chennai plant capabilities' / 'CEAT expands Chennai plant to make premium tyres')."""
    if len(a) < 3 or len(b) < 3:
        return a == b
    return len(a & b) / min(len(a), len(b)) >= SAME_STORY


# ---------- stored research ----------
def due(saved: dict, days: int = REFRESH_DAYS) -> bool:
    """Missing, older than ``days``, or a day old with a source that failed (e.g. Fincrux's daily quota)."""
    at = saved.get("at")
    if not at or not saved.get("facts"):
        return True
    age = datetime.now() - datetime.fromisoformat(at)
    return age >= timedelta(days=days) or (bool(saved.get("errors")) and age >= timedelta(days=1))


async def refresh(db: AsyncSession, code: str, transport=None) -> dict:
    """Research one RPG company now, following its SWOT parameters, and store it. Returns {at, facts, errors}."""
    from services.ingest import RUN_LOCK  # the Fincrux budget lives in the shared ``live`` state

    settings = await swot_settings.load(db, code)
    async with RUN_LOCK:
        live_state = await state_store.load(db, "live")
        facts, errors = await asyncio.to_thread(collect, code, live_state, settings, transport)
        await state_store.save(db, "live", live_state)
        saved = await state_store.load(db, key(code))
        if not facts and saved.get("facts"):  # every source failed: keep the last good research
            saved.update(errors=errors, tried_at=datetime.now().isoformat(timespec="seconds"))
        else:
            saved = {"at": datetime.now().isoformat(timespec="seconds"), "facts": facts, "errors": errors}
        await state_store.save(db, key(code), saved)
        await db.commit()
    return saved


async def refresh_due(db: AsyncSession, transport=None) -> list[str]:
    """Refresh every company whose research is missing or older than REFRESH_DAYS. Returns their codes."""
    done = []
    for code in PROFILES:
        if due(await state_store.load(db, key(code))):
            await refresh(db, code, transport)
            done.append(code)
    return done


async def load_all(db: AsyncSession) -> dict[str, dict]:
    return {code: await state_store.load(db, key(code)) for code in PROFILES}
