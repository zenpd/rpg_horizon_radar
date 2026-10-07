"""Shared pieces of the live connectors: the base class, JSON/error handling,
name matching, the headline classifier and the daily call budget.

Every live connector returns the same raw-signal dicts as the mock connectors
(signal_type, source_type, headline, source_excerpt, source_url, observed_at)
plus ``provider``. A connector only emits a signal when the data says
something the scoring rules weigh — a pledge, a rating cut, a profit fall, a
hiring swing. Everything else (routine notices, flat readings, unrelated
headlines) is dropped rather than stored as noise."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from db.models import Entity
from ingestion.connectors.base import Connector


class SourceError(Exception):
    pass


class LiveConnector(Connector):
    """A connector that calls a real API. ``state`` is the shared, persisted
    connector state (pacing, budgets, snapshots); see services/ingest.py."""

    name: str = ""
    min_days: int = 0  # pull a given entity at most this often (quota or slow-changing data)
    needs_symbol: bool = False  # queries by NSE symbol rather than by name

    def __init__(self, state: dict, transport: httpx.BaseTransport | None = None):
        self.state = state
        self.transport = transport

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    def query(self, entity: Entity) -> str:
        return (entity.nse_symbol or "") if self.needs_symbol else query_name(entity)

    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        q = self.query(entity)
        return self.pull(entity, q) if q else []

    def pull(self, entity: Entity, query: str) -> list[dict]:
        raise NotImplementedError

    def signal(self, signal_type: str, headline: str, observed_at: datetime, excerpt: str = "", url: str | None = None) -> dict:
        return {"signal_type": signal_type, "source_type": self.source_type, "headline": clip(headline, 500),
                "source_excerpt": excerpt, "source_url": clip(url or "", 500), "observed_at": observed_at, "provider": self.name}


def get_json(r: httpx.Response, name: str):
    if r.status_code in (401, 403):
        raise SourceError(f"{name} rejected the key (HTTP {r.status_code}).")
    if r.status_code == 429:
        raise SourceError(f"{name} quota or rate limit reached (HTTP 429).")
    if r.status_code != 200:
        raise SourceError(f"{name} error HTTP {r.status_code}: {r.text[:150]}")
    try:
        return r.json()
    except ValueError:
        raise SourceError(f"{name} returned something that is not JSON.")


def spend(state: dict, provider: str, limit: int) -> None:
    """Count one call against a provider's daily allowance; refuse once it is used up."""
    today = datetime.now().strftime("%Y-%m-%d")
    b = state.setdefault("budget", {}).get(provider)
    if not b or b["date"] != today:
        b = {"date": today, "used": 0}
    if b["used"] >= limit:
        raise SourceError(f"{provider}: daily limit of {limit} calls reached; it continues tomorrow.")
    b["used"] += 1
    state["budget"][provider] = b


# ---------- names ----------
SUFFIX = re.compile(r"(?:\s*[,&]?\s*\b(?:ltd|limited|pvt|private|inc|plc|corp|corporation|co|company|industries|international|india)\b\.?)+\s*$", re.I)


def short_name(name: str) -> str:
    """How headlines usually write a company: 'Apollo Tyres Ltd' -> 'Apollo Tyres',
    'Kalpataru Projects International' -> 'Kalpataru Projects'."""
    short = SUFFIX.sub("", name).strip(" ,&")
    return short if len(short) >= 3 else name


_NOISE = re.compile(r"\([^)]*\)|\b(?:ltd|limited|pvt|private|co|company|corporation|corp|inc|plc|group|india|"
                    r"industries|international|holdings|enterprises|and|of|the)\b\.?|[.,&']", re.I)


def company_words(name: str) -> list[str]:
    """The words that identify a company: 'Plantation Corporation of Kerala Limited (PCKL)' ->
    ['plantation', 'kerala']; tyres and tires are the same word."""
    return [w.replace("tyre", "tire") for w in _NOISE.sub(" ", name.lower()).split()]


def same_company(a: str, b: str) -> bool:
    """Two names for one company: the same identifying words, or the shorter (two words or more) is
    the start of the longer ('Techno Electric' and 'Techno Electric & Engineering Company Ltd',
    'Sterlite Power' and 'Sterlite Power Transmission Limited')."""
    x, y = sorted((company_words(a), company_words(b)), key=len)
    return bool(x) and (x == y or (len(x) >= 2 and y[: len(x)] == x))


def query_name(entity: Entity) -> str:
    return (entity.query_name or "").strip() or short_name(entity.name)


def about(name: str, text: str | None) -> bool:
    """The tracked name appears in the text as whole words. Stories that only
    mention the company in the body (market round-ups, lists) are dropped."""
    return bool(text) and re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])", text.lower()) is not None


# ---------- headline classifier ----------
EXEC = r"(?:ceo|cfo|coo|cto|md|managing director|chairman|chairperson|director|president|chief\b[\w ]{0,20}|head of [\w ]{1,20})"
HEADLINE_RULES = [
    (r"\bdowngrad\w*|\brating (?:cut|lowered)|outlook (?:revised )?to negative|watch with negative", "credit_downgrade"),
    (r"\b(?:delay(?:s|ed)?|defers?|postpones?)\b.{0,40}\b(?:results|filing|annual report|agm)\b|fails? to (?:file|submit)", "delayed_filing"),
    (r"\b(?:insolvency|nclt|bankruptcy|defaults?|defaulted|fraud|raids?|raided|probe|penalt(?:y|ies)|show[- ]cause|lawsuit|sues|sued)\b", "legal_action"),
    (rf"\b{EXEC}\b.{{0,60}}\b(?:resigns?|resigned|steps? down|stepped down|quits?|exits?|leaves|ousted|sacked)\b|"
     rf"\b(?:resigns?|resigned|steps? down|quits?|exits?)\b.{{0,40}}\b(?:as|from)\b.{{0,20}}\b{EXEC}\b", "leadership_churn"),
    (r"\b(?:layoffs?|lay off|job cuts?|retrench\w*|cuts? [\d,]+ jobs)\b", "hiring_scaledown"),
    (r"\bpledge[sd]?\b|\bencumb\w*", "promoter_pledge"),
    (r"\b(?:acquir\w*|acquisition|merger|merges?|merged|buyout|takeover|stake sale|sells? (?:\w+ )?stake|divest\w*|demerg\w*)\b", "deal_activity"),
    (r"\b(?:loss(?:es)? widen\w*|net loss|plunge[sd]?|slump(?:s|ed)?|shuts?|shutdown|closure|strike|lockout|halts?)\b|"
     r"\bprofit (?:falls?|drops?|declines?|slumps?|dips?)\b", "press_distress"),
    (r"\b(?:wins?|won|bags?|bagged|secures?|secured)\b.{0,50}\b(?:orders?|contracts?|deals?|projects?|mandates?)\b|"
     r"\b(?:orders? (?:worth|of|from)|order inflow|new orders?|contract (?:worth|from))\b|\bnew (?:plant|factory|facility)\b|"
     r"\bcapacity expansion\b|\bexpands?\b.{0,40}\b(?:capacity|plant|footprint|operations|presence)\b|"
     r"\blaunch(?:es|ed)?\b.{0,60}\b(?:products?|range|tyres?|plant|brand|platform|services?|solutions?|drugs?|cables?|lab|centre|center|fans?)\b|"
     r"\b(?:products?|range|tyres?|brand|platform|services?|solutions?|drugs?|cables?|fans?)\b.{0,40}\blaunched\b",
     "press_opportunity"),
]

# Headlines about sport, sponsorship, awards and hobby videos name a company without saying anything
# about its business (a rally it sponsors, a chess league, an RC model): never a signal.
NOT_BUSINESS = re.compile(
    r"\b(?:rally of|(?:car|motor|road|dakar) rally|racing|race|grand prix|motorsport|championship|tournament|league|chess|grandmasters?|endgame|cricket|"
    r"football|hockey|marathon|trophy|cup|match|innings|wicket|olympic|sponsor\w*|title partner|awards?|awarded|felicitat\w*|"
    r"#shorts|shorts|unboxing|vlog|rc (?:car|plane|model)|inflatable|toy)\b|\bgcl\b", re.I)


def classify_headline(text: str) -> str | None:
    """The signal type a headline reports, or None when it reports none of them."""
    t = text.lower()
    if NOT_BUSINESS.search(t):
        return None
    return next((kind for pat, kind in HEADLINE_RULES if re.search(pat, t)), None)


# ---------- small helpers ----------
def clip(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 3].rsplit(" ", 1)[0] + "..."


def naive_utc(value: str) -> datetime:
    """An ISO timestamp ('2026-09-29T10:00:00Z', '2026-09-29 10:00:00') as naive UTC, as stored."""
    d = datetime.fromisoformat(value.strip().replace("Z", "+00:00").replace(" ", "T", 1))
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("₹", "").strip())
    except ValueError:
        return float("nan")


def as_list(x) -> list:
    return x if isinstance(x, list) else ([] if x is None else [x])
