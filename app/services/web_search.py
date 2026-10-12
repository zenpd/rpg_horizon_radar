"""Jina and DuckDuckGo as the fallbacks for Tavily's news and web searches.

Tavily serves the radar's web searches (company research, discovery, the Sector Scout, the daily
news). When it refuses — its monthly credits used up, a rejected key — or has no key, the same
searches go to DuckDuckGo through the open-source ``ddgs`` library, which reads DuckDuckGo's result
pages: there is no official DuckDuckGo search API, so it can break or slow down when DuckDuckGo
changes, and it is paced to one search every GAP seconds. A refusal marks Tavily down for the rest
of the day, so later searches go straight to the fallbacks.

Web-page searches try Jina's search API first (``JINA_API_KEY``; an official API, so steadier than
reading DuckDuckGo's pages), then DuckDuckGo. News searches stay with DuckDuckGo: Jina's results carry
no publication date, and the news callers keep only dated stories. Jina, like Tavily, is skipped for
the rest of the day once it refuses.

DuckDuckGo gives titles, links, dates and short snippets — not the sourced answers Tavily writes —
so size checks (services/company_size.py) never fall back to it: a company that cannot be sized is
reported as not sized, never given a figure from a snippet. Results come back in Tavily's shape
(title, url, content, published_date) so callers need no second code path. ``DDG_FALLBACK=false``
turns it off."""
from __future__ import annotations

import threading
import time
from datetime import date

from ingestion.connectors.live.common import SourceError
from shared.config import get_settings

GAP = 3.0  # seconds between DuckDuckGo searches
REGION = "in-en"
_lock = threading.Lock()
_last = 0.0
_down: date | None = None
_jina_down: date | None = None
JINA_URL = "https://s.jina.ai/"


def ddg_on() -> bool:
    return get_settings().ddg_fallback


def jina_up() -> bool:
    return bool(get_settings().jina_api_key) and _jina_down != date.today()


def enabled() -> bool:
    """A fallback can answer when Tavily cannot."""
    return ddg_on() or jina_up()


def available() -> bool:
    """A web search can be made: Tavily has a key, or DuckDuckGo can stand in."""
    return bool(get_settings().tavily_api_key) or enabled()


def tavily_failed(error: Exception) -> None:
    """Note a Tavily refusal: credits used up or the key rejected keep it down for today."""
    global _down
    text = str(error)
    if any(f"HTTP {code}" in text for code in (401, 402, 403, 429, 432)) or "usage limit" in text:
        _down = date.today()


def tavily_down() -> bool:
    return _down == date.today()


def use_tavily() -> bool:
    return bool(get_settings().tavily_api_key) and not tavily_down()


def _call(fn):
    global _last
    with _lock:  # one search at a time, GAP apart: DuckDuckGo slows down or refuses bursts
        wait = _last + GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            from ddgs import DDGS

            return fn(DDGS(timeout=20)) or []
        except Exception as e:  # noqa: BLE001 — the library raises its own types for rate limits and timeouts
            raise SourceError(f"DuckDuckGo: {type(e).__name__}: {str(e)[:120]}")
        finally:
            _last = time.monotonic()


def _when(days: int) -> str:
    return "d" if days <= 1 else "w" if days <= 7 else "m" if days <= 31 else "y"


def news(query: str, days: int = 7, n: int = 10) -> list[dict]:
    """News stories, newest first, in Tavily's result shape (plus ``source``, the outlet)."""
    if not ddg_on():
        return []
    rows = _call(lambda d: d.news(query, region=REGION, timelimit=_when(days), max_results=n))
    return [{"title": r.get("title") or "", "url": r.get("url") or r.get("href"), "content": r.get("body") or "",
             "published_date": r.get("date"), "source": r.get("source")} for r in rows if r.get("title")]


def jina(query: str, n: int = 6, transport=None) -> list[dict]:
    """Web pages from Jina's search API, in Tavily's result shape (content is the page description)."""
    global _jina_down
    from ingestion.connectors.live.common import get_json
    from shared.http import client

    try:
        with client(transport, timeout=40.0) as c:
            body = get_json(c.get(JINA_URL, params={"q": query, "gl": "IN", "num": n},
                                  headers={"Authorization": f"Bearer {get_settings().jina_api_key}", "Accept": "application/json",
                                           "X-Respond-With": "no-content"}), "Jina")
    except SourceError as e:
        if any(f"HTTP {code}" in str(e) for code in (401, 402, 403, 429)):
            _jina_down = date.today()
        raise
    return [{"title": r.get("title") or "", "url": r.get("url"), "content": r.get("description") or ""}
            for r in (body.get("data") or [])[:n] if r.get("title")]


def text(query: str, n: int = 6) -> list[dict]:
    """Web pages, in Tavily's result shape: Jina first, else DuckDuckGo."""
    if jina_up():
        try:
            return jina(query, n)
        except Exception:  # noqa: BLE001 — a timeout or refusal falls through to DuckDuckGo
            if not ddg_on():
                raise
    if not ddg_on():
        return []
    rows = _call(lambda d: d.text(query, region=REGION, max_results=n))
    return [{"title": r.get("title") or "", "url": r.get("href"), "content": r.get("body") or ""} for r in rows if r.get("title")]


def search(body: dict) -> list[dict]:
    """A Tavily request body answered by DuckDuckGo: news for topic "news", else web pages."""
    if body.get("topic") == "news":
        return news(body["query"], body.get("days", 7), body.get("max_results", 10))
    return text(body["query"], body.get("max_results", 6))
