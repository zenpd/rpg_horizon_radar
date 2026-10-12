"""News and press: GNews (Currents on a day GNews refuses), NewsData.io, Tavily (web search, news
topic) and YouTube video titles. A story becomes a signal only when the watched company
is named in its headline and the headline reports something the scoring rules
weigh (common.classify_headline): a rating cut, a resignation, a deal, an
order win ...

Quotas: GNews free plan ~100 requests a day, about one a second, 12-hour
delay; once it refuses (the day's calls used up, or the key rejected) it is skipped for the rest
of the day and Currents (about 250 calls a day; thinner Indian coverage) answers instead. GDELT (no key) asks for one request every 5 seconds from a network; it
refuses more, and may refuse a shared office or VPN address used by others. NewsData free plan covers the last 48 hours. Tavily 1,000 credits a
month. YouTube: one search costs 100 of the 10,000 daily units."""
from __future__ import annotations

import html
import re
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from db.models import Entity
from ingestion.connectors.live.common import LiveConnector, SourceError, about, classify_headline, get_json, naive_utc
from shared.config import get_settings
from shared.http import client


class _Headlines(LiveConnector):
    source_type = "news"

    def headlines_to_signals(self, query: str, items: list[tuple[str, datetime, str | None, str]]) -> list[dict]:
        """items: (headline, observed_at, url, outlet)."""
        out, seen = [], set()
        for title, when, url, outlet in items:
            title = html.unescape((title or "").strip())
            kind = classify_headline(title) if about(query, title) else None
            if not kind or title.lower() in seen:
                continue
            seen.add(title.lower())
            out.append(self.signal(kind, title, when, excerpt=f"{self.name} · {outlet}", url=url))
        return out


# GNews' daily allowance is shared by every caller (the connector, company research, the Sector Scout).
_down: dict[str, date] = {}


def failed(provider: str, error: Exception) -> None:
    """Note a refusal that lasts the day: the key rejected, or the day's calls used up."""
    text = str(error)
    if any(f"HTTP {code}" in text for code in (401, 403)) or "limit" in text.lower():
        _down[provider] = date.today()


def down(provider: str) -> bool:
    return _down.get(provider) == date.today()


def gnews_up() -> bool:
    return bool(get_settings().gnews_api_key) and not down("GNews")


def currents_up() -> bool:
    """Currents answers when GNews cannot: no GNews key, or GNews has refused today."""
    return bool(get_settings().currents_api_key) and not down("Currents") and not gnews_up()


CURRENTS_URL = "https://api.currentsapi.services/v1/search"


def currents(query: str, transport=None, since: datetime | None = None, exact: bool = True) -> list[dict]:
    """Currents news search, Indian English-language outlets: [{title, description, observed_at, url, outlet}]."""
    params = {"keywords": f'"{query}"' if exact else query, "language": "en", "country": "IN",
              "apiKey": get_settings().currents_api_key}
    if since:  # Currents searches at most 7 days back
        params["start_date"] = max(since, datetime.utcnow() - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    try:
        with client(transport) as c:
            body = get_json(c.get(CURRENTS_URL, params=params), "Currents")
    except SourceError as e:
        failed("Currents", e)
        raise
    if body.get("status") != "ok":
        raise SourceError(f"Currents: {body.get('msg') or body.get('status')}")
    out = []
    for a in body.get("news") or []:
        try:
            when = datetime.strptime(a.get("published", ""), "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
        host = re.sub(r"^www\.", "", httpx.URL(a["url"]).host) if a.get("url") else "news"
        out.append({"title": a.get("title") or "", "description": a.get("description") or "", "observed_at": when,
                    "url": a.get("url"), "outlet": host})
    return out


class GNews(_Headlines):
    name = "GNews"
    URL = "https://gnews.io/api/v4/search"
    GAP = 1.5  # seconds between requests
    _last = 0.0

    def __init__(self, state, transport=None, sleep=time.sleep):
        super().__init__(state, transport)
        self.key = get_settings().gnews_api_key
        self.sleep = sleep

    @property
    def configured(self) -> bool:  # skipped for the day once it has refused (Currents stands in)
        return bool(self.key) and (self.transport is not None or not down(self.name))

    def pull(self, entity: Entity, query: str) -> list[dict]:
        try:
            return self._pull(query)
        except SourceError as e:
            failed(self.name, e)
            raise

    def _pull(self, query: str) -> list[dict]:
        params = {"q": f'"{query}"', "lang": "en", "country": "in", "max": 10, "sortby": "publishedAt", "apikey": self.key}
        with client(self.transport) as c:
            for _ in range(2):
                wait = GNews._last + self.GAP - time.monotonic()
                if wait > 0 and not self.transport:
                    self.sleep(wait)
                r = c.get(self.URL, params=params)
                GNews._last = time.monotonic()
                if r.status_code != 429:
                    break
                self.sleep(3)
            body = get_json(r, self.name)
        if body.get("errors"):
            raise SourceError(f"{self.name}: {'; '.join(map(str, body['errors']))}")
        return self.headlines_to_signals(query, [
            (a.get("title"), naive_utc(a["publishedAt"]), a.get("url"), (a.get("source") or {}).get("name") or "news")
            for a in body.get("articles") or []])


class Currents(_Headlines):
    """Currents news search: stands in for GNews on a day GNews has refused, or when GNews has no key."""
    name = "Currents"

    @property
    def configured(self) -> bool:
        return currents_up() if self.transport is None else bool(get_settings().currents_api_key)

    def pull(self, entity: Entity, query: str) -> list[dict]:
        return self.headlines_to_signals(query, [(a["title"], a["observed_at"], a["url"], a["outlet"])
                                                 for a in currents(query, self.transport)])


class GDELT(_Headlines):
    """GDELT DOC 2.0 article search, Indian English-language outlets, last 14 days. Free, no key."""
    name = "GDELT"
    URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    GAP = 6.0  # seconds between requests: GDELT allows one every 5
    _last = 0.0

    def __init__(self, state, transport=None, sleep=time.sleep):
        super().__init__(state, transport)
        self.sleep = sleep

    @property
    def configured(self) -> bool:
        return get_settings().gdelt_enabled

    def pull(self, entity: Entity, query: str) -> list[dict]:
        params = {"query": f'"{query}" sourcecountry:IN sourcelang:english', "mode": "artlist", "format": "json",
                  "maxrecords": 25, "timespan": "14d", "sort": "datedesc"}
        with client(self.transport, timeout=40.0) as c:
            for attempt in range(2):
                wait = GDELT._last + self.GAP - time.monotonic()
                if wait > 0 and not self.transport:
                    self.sleep(wait)
                r = c.get(self.URL, params=params)
                GDELT._last = time.monotonic()
                if r.status_code != 429:
                    break
                if attempt == 0:
                    self.sleep(self.GAP)
        if r.status_code == 429:
            raise SourceError(f"{self.name}: refused for rate (one request every 5 seconds per network); it is tried again on the next run.")
        if r.status_code != 200:
            raise SourceError(f"{self.name}: HTTP {r.status_code}")
        try:
            body = r.json() if r.text.strip() else {}
        except ValueError:  # GDELT answers a bad query with a plain-text message
            raise SourceError(f"{self.name}: {r.text.strip()[:120]}")
        items = []
        for a in body.get("articles") or []:
            try:
                when = datetime.strptime(a.get("seendate", ""), "%Y%m%dT%H%M%SZ")
            except ValueError:
                continue
            items.append((a.get("title"), when, a.get("url"), a.get("domain") or "news"))
        return self.headlines_to_signals(query, items)


class NewsData(_Headlines):
    name = "NewsData.io"
    URL = "https://newsdata.io/api/1/latest"

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        self.key = get_settings().newsdata_api_key

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def pull(self, entity: Entity, query: str) -> list[dict]:
        params = {"apikey": self.key, "q": query, "country": "in", "language": "en"}
        with client(self.transport) as c:
            body = get_json(c.get(self.URL, params=params), self.name)
        if body.get("status") != "success":
            raise SourceError(f"{self.name}: {(body.get('results') or {}).get('message', body.get('status'))}")
        return self.headlines_to_signals(query, [
            (a.get("title"), naive_utc(a["pubDate"]), a.get("link"), a.get("source_name") or a.get("source_id") or "news")
            for a in body.get("results") or []])


class Tavily(_Headlines):
    """Web search, news topic, last 7 days. Catches coverage the news APIs miss."""
    name = "Tavily"
    URL = "https://api.tavily.com/search"

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        self.key = get_settings().tavily_api_key

    @property
    def configured(self) -> bool:  # skipped for the day once Tavily has refused (DuckDuckGo stands in)
        from services import web_search

        return bool(self.key) and (self.transport is not None or not web_search.tavily_down())

    def pull(self, entity: Entity, query: str) -> list[dict]:
        from services import web_search

        body_in = {"query": f"{query} India", "topic": "news", "days": 7, "max_results": 8}
        try:
            with client(self.transport) as c:
                body = get_json(c.post(self.URL, headers={"Authorization": f"Bearer {self.key}"}, json=body_in), self.name)
        except SourceError as e:
            web_search.tavily_failed(e)
            raise
        items = []
        for x in body.get("results") or []:
            if not x.get("published_date"):
                continue
            when = parsedate_to_datetime(x["published_date"]).astimezone(timezone.utc).replace(tzinfo=None)
            host = re.sub(r"^www\.", "", httpx.URL(x["url"]).host) if x.get("url") else "web"
            items.append((x.get("title"), when, x.get("url"), host))
        return self.headlines_to_signals(query, items)


class DuckDuckGo(_Headlines):
    """DuckDuckGo news, last 14 days: stands in for Tavily on a day it has refused, or when it has no key
    (services/web_search.py). Paced to one search every 3 seconds."""
    name = "DuckDuckGo"

    @property
    def configured(self) -> bool:
        from services import web_search

        return self.transport is None and web_search.ddg_on() and not web_search.use_tavily()

    def pull(self, entity: Entity, query: str) -> list[dict]:
        from services import web_search

        items = []
        for x in web_search.news(f'"{query}"', days=14, n=10):
            when = _published_any(x.get("published_date"))
            if when:
                items.append((x["title"], when, x.get("url"), x.get("source") or "news"))
        return self.headlines_to_signals(query, items)


def _published_any(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


class YouTube(_Headlines):
    """Video titles from India over the last 7 days, classified like headlines.
    Search results are noisy (dealer shorts, fitment clips), so most are dropped."""
    name = "YouTube"
    URL = "https://www.googleapis.com/youtube/v3/search"

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        self.key = get_settings().youtube_api_key

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def pull(self, entity: Entity, query: str) -> list[dict]:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {"part": "snippet", "q": f'"{query}"', "type": "video", "order": "date", "publishedAfter": since,
                  "regionCode": "IN", "relevanceLanguage": "en", "maxResults": 10, "key": self.key}
        with client(self.transport) as c:
            body = get_json(c.get(self.URL, params=params), self.name)
        return self.headlines_to_signals(query, [
            (i["snippet"]["title"], naive_utc(i["snippet"]["publishedAt"]),
             f"https://www.youtube.com/watch?v={i['id']['videoId']}", i["snippet"].get("channelTitle") or "video")
            for i in body.get("items") or [] if (i.get("id") or {}).get("videoId")])
