"""News and press: GNews, NewsData.io, Tavily (web search, news topic) and
YouTube video titles. A story becomes a signal only when the watched company
is named in its headline and the headline reports something the scoring rules
weigh (common.classify_headline): a rating cut, a resignation, a deal, an
order win ...

Quotas: GNews free plan ~100 requests a day, about one a second, 12-hour
delay. NewsData free plan covers the last 48 hours. Tavily 1,000 credits a
month. YouTube: one search costs 100 of the 10,000 daily units."""
from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta, timezone
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
    def configured(self) -> bool:
        return bool(self.key)

    def pull(self, entity: Entity, query: str) -> list[dict]:
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
    def configured(self) -> bool:
        return bool(self.key)

    def pull(self, entity: Entity, query: str) -> list[dict]:
        body_in = {"query": f"{query} India", "topic": "news", "days": 7, "max_results": 8}
        with client(self.transport) as c:
            body = get_json(c.post(self.URL, headers={"Authorization": f"Bearer {self.key}"}, json=body_in), self.name)
        items = []
        for x in body.get("results") or []:
            if not x.get("published_date"):
                continue
            when = parsedate_to_datetime(x["published_date"]).astimezone(timezone.utc).replace(tzinfo=None)
            host = re.sub(r"^www\.", "", httpx.URL(x["url"]).host) if x.get("url") else "web"
            items.append((x.get("title"), when, x.get("url"), host))
        return self.headlines_to_signals(query, items)


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
