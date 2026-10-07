"""Corporate filings and financials for Indian listed companies.

NSE        Corporate announcements (last 21 days) and promoter pledges from
           NSE's website API. No official API and no key; NSE's terms restrict
           automated access and it blocks heavy use, so this makes two calls per
           entity a day, a second apart. NSE_ENABLED=false turns it off.
Fincrux    Quarterly results and shareholding (api.fincrux.org) by NSE symbol.
           The key allows 5 calls a day: each entity is pulled at most weekly
           (results change quarterly) and a daily budget stops calls at 5.
Alpha Vantage  30-day share-price move from TIME_SERIES_DAILY on the BSE
           listing, and ticker search for symbol resolution. 25 calls a day.

All three need the entity's NSE symbol, resolved by resolve_nse_symbol() and
stored on Entity.nse_symbol (an admin can also set it by hand)."""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta

import httpx

from db.models import Entity
from ingestion.connectors.live.common import LiveConnector, SourceError, about, clip, get_json, num, short_name, spend
from shared.config import get_settings
from shared.http import client

NSE_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36",
               "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.nseindia.com/"}
NSE_API = "https://www.nseindia.com/api"
PLEDGE_MIN_PCT = 5.0  # promoter shares pledged; below this it is not a distress signal


def nse_type(category: str, text: str) -> str | None:
    """The signal type an NSE announcement reports, or None for routine notices
    (trading-window closures, newspaper copies, record dates, appointments,
    rating reaffirmations, results — Fincrux covers results)."""
    both = f"{category} {text}".lower()
    if re.search(r"delay|non[- ]submission|not submitted", both) and re.search(r"result|filing|submission|report", both):
        return "delayed_filing"
    if "credit rating" in both:
        return "credit_downgrade" if re.search(r"downgrad|revised (?:to|from)[^.]*negative|lowered|watch with negative", both) else None
    if "auditor" in both and re.search(r"resign|cessation|ceas|change", both):
        return "auditor_change"
    if re.search(r"change in director|change in management|key managerial|resignation|cessation", both):
        return "leadership_churn" if re.search(r"resign|cessation|ceas|step(?:s|ped)? down|vacat", both) else None
    if re.search(r"insolvency|default|fraud|litigation|action\(s\) taken|orders passed|penalt", both):
        return "legal_action"
    if re.search(r"takeover|acquisition|amalgamation|merger|scheme of arrangement|joint venture|disinvestment|sale or disposal", both):
        return "deal_activity"
    if re.search(r"allotment of securities|preferential issue|qualified institutions placement|\bqip\b|debentures|non convertible|rights issue|fund rais", both):
        return "fund_raise"
    return None


class NSE(LiveConnector):
    name, source_type, needs_symbol = "NSE", "filing", True
    GAP = 1.0
    DAYS = 21  # announcements this recent become signals
    _last = 0.0

    @property
    def configured(self) -> bool:
        return get_settings().nse_enabled

    def get(self, path: str, params: dict) -> httpx.Response:
        wait = NSE._last + self.GAP - time.monotonic()
        if wait > 0 and not self.transport:
            time.sleep(wait)
        with client(self.transport) as c:
            r = c.get(f"{NSE_API}/{path}", params=params, headers=NSE_HEADERS)
        NSE._last = time.monotonic()
        return r

    def pull(self, entity: Entity, query: str) -> list[dict]:
        rows = get_json(self.get("corporate-announcements", {"index": "equities", "symbol": query}), self.name)
        if not isinstance(rows, list):
            raise SourceError(f"{self.name}: unexpected reply for {query}.")
        cutoff = datetime.now() - timedelta(days=self.DAYS)
        out, seen = [], set()
        for a in rows:
            when = datetime.strptime(a["sort_date"], "%Y-%m-%d %H:%M:%S")
            if when < cutoff:
                break  # newest first
            cat = (a.get("desc") or "").strip()
            text = (a.get("attchmntText") or cat).strip()
            kind = nse_type(cat, text)
            if not kind or text in seen:
                continue
            seen.add(text)
            out.append(self.signal(kind, f"{entity.name}: {cat}" if cat else clip(text, 200), when,
                                   excerpt=clip(text, 600), url=a.get("attchmntFile")))
            if len(out) == 8:
                break
        r = self.get("corporate-pledgedata", {"index": "equities", "symbol": query})
        pledge = (get_json(r, self.name).get("data") or [None])[0] if r.status_code == 200 else None
        if pledge and pledge.get("percSharesPledged"):
            pct, promo = num(pledge["percSharesPledged"]), (pledge.get("percPromoterHolding") or "").strip()
            if pct >= PLEDGE_MIN_PCT:
                as_of = f", as of {pledge['disclosureToDate']}" if pledge.get("disclosureToDate") else ""
                out.append(self.signal("promoter_pledge", f"{entity.name} promoters have pledged {pct:g}% of their shares",
                                       datetime.strptime(pledge["broadcastDt"], "%d-%b-%Y %H:%M:%S"),
                                       excerpt=f"Promoter holding {promo}%{as_of}. Source: NSE pledged-shares disclosure.",
                                       url=f"https://www.nseindia.com/get-quotes/equity?symbol={query}"))
        return out


class Fincrux(LiveConnector):
    name, source_type, needs_symbol = "Fincrux", "filing", True
    URL = "https://api.fincrux.org/api"
    min_days = 7
    DAILY_LIMIT = 5
    PROFIT_FALL = -15.0  # net profit YoY, percent
    SALES_FALL = -10.0
    PROMOTER_CUT = 0.5  # percentage points in a quarter
    FII_CUT = 1.5

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        self.key = get_settings().fincrux_api_key

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def get(self, path: str) -> dict:
        spend(self.state, self.name, self.DAILY_LIMIT)
        with client(self.transport) as c:
            body = get_json(c.get(f"{self.URL}/{path}", params={"api_key": self.key}), self.name)
        if str(body.get("success")) != "true":
            raise SourceError(f"{self.name}: {body.get('message') or 'request failed'}")
        return body

    def search(self, name: str) -> str | None:
        hits = self.get(f"search/{name}").get("search_results") or []
        return hits[0]["trading_symbol"] if hits else None

    def pull(self, entity: Entity, query: str) -> list[dict]:
        from services.market_data import keep_financials

        d = self.get(f"financials/{query}")["data"]
        keep_financials(self.state, query, d)  # for The financial market, at no extra call
        when = datetime.fromisoformat(d["last_updated_at"][:19]) if d.get("last_updated_at") else datetime.now()
        out = []
        q = {row[0]: row[1:] for row in d.get("quaterly_results") or []}  # sic, the API's spelling
        qs = q.get("Category") or []
        if len(qs) >= 5 and q.get("Sales") and q.get("Net Profit"):
            sales, profit = q["Sales"], q["Net Profit"]
            s_yoy, p_yoy = _yoy(sales[-1], sales[-5]), _yoy(profit[-1], profit[-5])
            if (p_yoy is not None and p_yoy <= self.PROFIT_FALL) or (s_yoy is not None and s_yoy <= self.SALES_FALL):
                opm = q.get("OPM %") or []
                margin = f" Operating margin {opm[-1]} ({opm[-5]} a year earlier)." if len(opm) >= 5 else ""
                out.append(self.signal("earnings_decline", f"{entity.name} {qs[-1]} quarter: net profit {_pct(p_yoy)} YoY, sales {_pct(s_yoy)} YoY", when,
                                       excerpt=f"Sales ₹{sales[-1]} cr vs ₹{sales[-5]} cr; net profit ₹{profit[-1]} cr vs ₹{profit[-5]} cr.{margin} Source: Fincrux quarterly results."))
        s = {row[0]: row[1:] for row in d.get("shareholding_quarterly") or []}
        ss = s.get("Category") or []
        if len(ss) >= 2:
            cuts = []
            for who, limit in (("Promoters", self.PROMOTER_CUT), ("FIIs", self.FII_CUT)):
                v = s.get(who)
                if v and len(v) >= 2 and num(v[-2]) - num(v[-1]) >= limit:
                    cuts.append(f"{who} down from {v[-2]} to {v[-1]}")
            if cuts:
                out.append(self.signal("stake_selldown", f"{entity.name} {ss[-1]} quarter: " + "; ".join(cuts), when,
                                       excerpt=f"Shareholding {ss[-2]} → {ss[-1]}. Source: Fincrux shareholding pattern."))
        return out


class AlphaVantage(LiveConnector):
    """A 20%+ fall in the BSE share price over about 30 trading days."""
    name, source_type, needs_symbol = "Alpha Vantage", "news", True
    URL = "https://www.alphavantage.co/query"
    DAILY_LIMIT = 25
    min_days = 1
    SLUMP = -20.0
    GAP = 1.5
    _last = 0.0

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        self.key = get_settings().alpha_vantage_api_key

    @property
    def configured(self) -> bool:
        return bool(self.key)

    def call(self, params: dict) -> dict:
        spend(self.state, self.name, self.DAILY_LIMIT)
        wait = AlphaVantage._last + self.GAP - time.monotonic()
        if wait > 0 and not self.transport:
            time.sleep(wait)
        with client(self.transport) as c:
            body = get_json(c.get(self.URL, params={**params, "apikey": self.key}), self.name)
        AlphaVantage._last = time.monotonic()
        if body.get("Information") or body.get("Note"):  # daily limit or throttling
            raise SourceError(f"{self.name}: {(body.get('Information') or body.get('Note'))[:120]}")
        if body.get("Error Message"):
            raise SourceError(f"{self.name}: {body['Error Message'][:120]}")
        return body

    def query(self, entity: Entity) -> str:
        bse = (self.state.get("symbols", {}).get(str(entity.id)) or {}).get("bse")
        return bse or (f"{entity.nse_symbol}.BSE" if entity.nse_symbol else "")

    def pull(self, entity: Entity, query: str) -> list[dict]:
        from services.market_data import keep_prices

        series = self.call({"function": "TIME_SERIES_DAILY", "symbol": query, "outputsize": "compact"}).get("Time Series (Daily)") or {}
        keep_prices(self.state, entity.nse_symbol or query.split(".")[0], series)  # for The financial market
        days = sorted(series)
        if len(days) < 31:
            return []
        now, then = num(series[days[-1]]["4. close"]), num(series[days[-31]]["4. close"])
        move = (now - then) / then * 100 if then else 0
        if move > self.SLUMP:
            return []
        return [self.signal("share_price_slump", f"{entity.name} shares down {abs(move):.0f}% in 30 trading days",
                            datetime.fromisoformat(days[-1]),
                            excerpt=f"Close ₹{now:,.2f} on {days[-1]} vs ₹{then:,.2f} on {days[-31]} ({query}). Source: Alpha Vantage daily prices.")]

    def symbol_search(self, name: str) -> str | None:
        matches = self.call({"function": "SYMBOL_SEARCH", "keywords": name}).get("bestMatches") or []
        return next((m["1. symbol"] for m in matches if m.get("1. symbol", "").endswith(".BSE")), None)


def resolve_nse_symbol(entity: Entity, state: dict, transport=None) -> str | None:
    """The entity's NSE symbol: the BSE ticker's stem (Alpha Vantage search) when
    NSE confirms the same company, otherwise a Fincrux name search. Both lookups
    count against their daily budgets; a miss is retried after a week (ingest.py)."""
    name = short_name(entity.name)
    nse = NSE(state, transport)
    av = AlphaVantage(state, transport)
    if av.configured:
        try:
            bse = av.symbol_search(name)
        except (SourceError, httpx.HTTPError):
            bse = None
        if bse:
            state.setdefault("symbols", {}).setdefault(str(entity.id), {})["bse"] = bse
            stem = bse.split(".")[0]
            if not stem.isdigit() and nse.configured:
                try:
                    rows = get_json(nse.get("corporate-announcements", {"index": "equities", "symbol": stem}), "NSE")
                    if isinstance(rows, list) and rows and about(name, rows[0].get("sm_name", "")):
                        return stem
                except (SourceError, httpx.HTTPError):
                    pass
    fx = Fincrux(state, transport)
    if fx.configured:
        try:
            return fx.search(name)
        except (SourceError, httpx.HTTPError):
            return None
    return None


def _yoy(now: str, then: str) -> float | None:
    a, b = num(then), num(now)
    if not (a == a and b == b) or a == 0:
        return None
    return (b - a) / abs(a) * 100


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:+.0f}%"
