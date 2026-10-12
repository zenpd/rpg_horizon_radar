"""The financial market: each RPG company's quarterly results, shareholding and share price against
its listed watched companies'. Rule-based, no model.

The figures come from the two quota-limited feeds the radar already calls: Fincrux (quarterly results
and shareholding, 5 calls a day) and Alpha Vantage (daily BSE closing prices, 25 calls a day). When
Alpha Vantage is used up or has no key, Marketstack fills the missing NSE closing prices (its v1 API,
up to MARKETSTACK_BATCH companies a call; the free plan allows about 100 calls a month), at most every
MARKETSTACK_HOURS per company. The daily refresh also keeps every listed watched company's prices,
so the share-price slump signal (``slump``) works whichever feed supplied them. Every
call the ingestion connectors and the company research make keeps a compact copy of the figures in
the shared ``live`` state (``keep_financials`` / ``keep_prices``), so the comparison costs no extra
calls. From Fincrux's annual tables it also works out balance-sheet health (``health``: debt to equity,
interest cover, free cash flow, sales growth over 3 and 5 years, and an Altman Z-score) and market
multiples (P/E, P/B, EV/EBITDA, EV/sales) — market facts, not a valuation; refresh() fills the RPG companies' own figures each day (services/scheduler.py, after the
news run) and, on demand, a company's peers that have none yet, within what the budgets leave.
Market caps come from services/company_size.py."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from statistics import median

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.connectors.live.common import SourceError, num
from services import state as state_store

PRICE_HOURS = 20  # prices are refreshed daily
RESULTS_DAYS = 7  # results change quarterly; checked weekly
QUARTERS = 8
PRICE_DAYS = 100
SHAREHOLDERS = ("Promoters", "FIIs", "DIIs", "Public")
ANNUAL_YEARS = 7  # six years (five of growth), plus the last twelve months
# Altman (1968) Z-score zones for listed manufacturers
Z_SAFE, Z_DISTRESS = 2.99, 1.81
# A balance sheet under stress (ingestion/connectors/live/filings.py raises a signal on any one)
STRESS_DEBT_TO_EQUITY = 2.0
STRESS_INTEREST_COVER = 1.5


# ---------- kept by the connectors ----------
def keep_financials(state: dict, symbol: str, d: dict) -> None:
    """Keep the last QUARTERS quarters of sales, net profit and operating margin, and the shareholding."""
    if not symbol:
        return
    q = {row[0]: row[1:] for row in d.get("quaterly_results") or []}  # sic, the API's spelling
    s = {row[0]: row[1:] for row in d.get("shareholding_quarterly") or []}
    cut = lambda v: list(v or [])[-QUARTERS:]
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"), "quarters": cut(q.get("Category")), "sales": cut(q.get("Sales")),
        "profit": cut(q.get("Net Profit")), "opm": cut(q.get("OPM %")),
        "holding_quarters": list(s.get("Category") or [])[-4:], "holding": {k: list(s.get(k) or [])[-4:] for k in SHAREHOLDERS},
        "annual": _table(d.get("profit_and_loss"), ANNUAL_YEARS, ("Sales", "Operating Profit", "Interest", "Profit before tax", "Net Profit")),
        "balance": _table(d.get("balance_sheet"), 3, ("Equity Capital", "Reserves", "Borrowings", "Total Liabilities")),
        "cash": _table(d.get("cash_flows"), 3, ("Cash from Operating Activity", "Free Cash Flow")),
        "ratios": _table(d.get("ratios"), 1, ("Working Capital Days", "ROCE %")),
        "top": {k: v for k, v in (d.get("top_ratios") or {}).items() if isinstance(v, (str, int, float))}}
    state.setdefault("market", {}).setdefault("fin", {})[symbol.upper()] = entry
    return entry


def _table(rows, keep: int, names: tuple[str, ...]) -> dict:
    """A Fincrux table ([["Category", periods...], [name, values...], ...]) cut to its last ``keep`` periods."""
    t = {row[0]: list(row[1:])[-keep:] for row in rows or [] if row}
    return {"periods": t.get("Category") or [], **{n: t[n] for n in names if n in t}}


def _last(t: dict, name: str, at: int = -1):
    v = t.get(name) or []
    return _figure(v[at]) if len(v) >= abs(at) else None


def _cagr(now, then, years: int) -> float | None:
    return round(((now / then) ** (1 / years) - 1) * 100, 1) if now and then and now > 0 and then > 0 else None


def _figure(v) -> float | None:
    """The number in a display value: '₹13,314Cr.' -> 13314, '18.8%' -> 18.8, '' -> None."""
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(v or ""))
    return float(m.group().replace(",", "")) if m else None


def health(fin: dict | None) -> dict:
    """Balance-sheet health and market multiples from the kept annual tables (empty when Fincrux sent none).
    Working capital is not split out by Fincrux, so the Altman Z-score estimates it from working-capital days."""
    if not fin or not (fin.get("balance") or {}).get("periods"):
        return {}
    a, b, c, r, top = fin.get("annual") or {}, fin["balance"], fin.get("cash") or {}, fin.get("ratios") or {}, fin.get("top") or {}
    periods = a.get("periods") or []
    ttm = -1 if periods and periods[-1] == "TTM" else None
    year = -2 if ttm else -1  # the last full year, which the balance sheet matches
    equity = (_last(b, "Equity Capital") or 0) + (_last(b, "Reserves") or 0)
    debt, total = _last(b, "Borrowings"), _last(b, "Total Liabilities")
    sales_y, sales_t = _last(a, "Sales", year), _last(a, "Sales", ttm or year)
    interest_t, pbt_t, op_t = _last(a, "Interest", ttm or year), _last(a, "Profit before tax", ttm or year), _last(a, "Operating Profit", ttm or year)
    out: dict = {"year": b["periods"][-1], "debt": debt, "equity": round(equity) if equity else None,
                 "debt_to_equity": round(debt / equity, 2) if debt is not None and equity > 0 else None,
                 "interest_cover": round((pbt_t + interest_t) / interest_t, 1) if interest_t and pbt_t is not None else None,
                 "cfo": _last(c, "Cash from Operating Activity"), "fcf": _last(c, "Free Cash Flow"), "roce": _last(r, "ROCE %"),
                 "sales_cagr_3y": _cagr(sales_y, _last(a, "Sales", year - 3), 3) if len(periods) >= 4 + bool(ttm) else None,
                 "sales_cagr_5y": _cagr(sales_y, _last(a, "Sales", year - 5), 5) if len(periods) >= 6 + bool(ttm) else None}
    mcap = _figure(top.get("Market Cap"))
    wc_days = _last(r, "Working Capital Days")
    pbt_y, interest_y = _last(a, "Profit before tax", year), _last(a, "Interest", year)
    liabilities = total - equity if total and equity else None
    if total and sales_y and wc_days is not None and pbt_y is not None and interest_y is not None and mcap and liabilities and liabilities > 0:
        parts = {"working_capital": 1.2 * (wc_days * sales_y / 365) / total, "retained_earnings": 1.4 * (_last(b, "Reserves") or 0) / total,
                 "ebit": 3.3 * (pbt_y + interest_y) / total, "market_value_to_liabilities": 0.6 * mcap / liabilities, "sales": 1.0 * sales_y / total}
        z = round(sum(parts.values()), 2)
        out["altman_z"] = {"z": z, "zone": "safe" if z > Z_SAFE else "distress" if z < Z_DISTRESS else "grey",
                           "parts": {k: round(v, 2) for k, v in parts.items()}, "year": b["periods"][-1]}
    price, book = _figure(top.get("Current Price")), _figure(top.get("Book Value"))
    ev = mcap + (debt or 0) if mcap else None
    out.update(market_cap=mcap, pe=_figure(top.get("Stock P/E")),
               pb=round(price / book, 2) if price and book else None, ev=round(ev) if ev else None,
               ev_ebitda=round(ev / op_t, 1) if ev and op_t and op_t > 0 else None,
               ev_sales=round(ev / sales_t, 2) if ev and sales_t else None,
               roe=_figure(top.get("ROE")), dividend_yield=_figure(top.get("Dividend Yield")))
    return out


def stress(h: dict) -> list[str]:
    """Why a balance sheet looks under stress, one plain reason each (none when it does not)."""
    out = []
    z = h.get("altman_z")
    if z and z["zone"] == "distress":
        out.append(f"Altman Z-score {z['z']} (distress zone, below {Z_DISTRESS})")
    if (h.get("debt_to_equity") or 0) >= STRESS_DEBT_TO_EQUITY:
        out.append(f"debt {h['debt_to_equity']} times equity")
    if h.get("interest_cover") is not None and h["interest_cover"] < STRESS_INTEREST_COVER:
        out.append(f"interest cover {h['interest_cover']}x")
    return out


def health_text(name: str, h: dict) -> str | None:
    """One sentence for the agents' evidence: the balance sheet in plain figures (no multiples: no valuation)."""
    if not h:
        return None
    bits = []
    if h.get("debt") is not None and h.get("equity"):
        bits.append(f"borrowings ₹{h['debt']:,.0f} cr against equity ₹{h['equity']:,.0f} cr (debt to equity {h['debt_to_equity']})")
    if h.get("interest_cover") is not None:
        bits.append(f"interest cover {h['interest_cover']}x")
    if h.get("fcf") is not None:
        bits.append(f"free cash flow ₹{h['fcf']:,.0f} cr")
    if h.get("sales_cagr_3y") is not None:
        bits.append(f"sales growth {h['sales_cagr_3y']:+.1f}% a year over 3 years")
    if h.get("altman_z"):
        bits.append(f"Altman Z-score {h['altman_z']['z']} ({h['altman_z']['zone']} zone; working capital estimated)")
    return f"{name} balance sheet, {h['year']}: " + "; ".join(bits) + "." if bits else None


def keep_prices(state: dict, symbol: str, series: dict, source: str = "Alpha Vantage") -> None:
    """Keep the last PRICE_DAYS daily closes from an Alpha Vantage TIME_SERIES_DAILY reply (or one shaped like it)."""
    if not symbol or not series:
        return
    days = sorted(series)[-PRICE_DAYS:]
    state.setdefault("market", {}).setdefault("px", {})[symbol.upper()] = {
        "at": datetime.now().isoformat(timespec="seconds"), "source": source,
        "closes": [[d, round(num(series[d]["4. close"]), 2)] for d in days]}


SLUMP = -20.0  # a share_price_slump: down this much or more over SLUMP_DAYS trading days
SLUMP_DAYS = 30


def slump(px: dict | None) -> dict | None:
    """The fall over the last SLUMP_DAYS trading days in kept closes, when it is SLUMP or worse."""
    c = (px or {}).get("closes") or []
    if len(c) < SLUMP_DAYS + 1:
        return None
    (then_d, then), (now_d, now) = c[-SLUMP_DAYS - 1], c[-1]
    move = (now - then) / then * 100 if then else 0
    return {"move": move, "now": now, "now_date": now_d, "then": then, "then_date": then_d,
            "source": px.get("source") or "Alpha Vantage"} if move <= SLUMP else None


# Marketstack: v1 API (v2 rejects NSE symbols)
MARKETSTACK_MONTHLY = 90  # calls a month we allow ourselves (the free plan allows about 100)
MARKETSTACK_BATCH = 9  # companies a call: 9 x ~100 trading days stays within its 1,000 rows
MARKETSTACK_HOURS = 72  # a company's prices are fetched from it at most this often, to stay within the month


def _marketstack(state: dict, path: str, params: dict, transport=None) -> dict:
    """One Marketstack v1 call, counted against MARKETSTACK_MONTHLY."""
    from ingestion.connectors.live.common import get_json
    from shared.config import get_settings
    from shared.http import client

    month = datetime.now().strftime("%Y-%m")
    b = state.setdefault("budget", {}).get("Marketstack")
    if not b or b.get("month") != month:
        b = {"month": month, "used": 0}
    if b["used"] >= MARKETSTACK_MONTHLY:
        raise SourceError(f"Marketstack: monthly limit of {MARKETSTACK_MONTHLY} calls reached; it continues next month.")
    b["used"] += 1
    state["budget"]["Marketstack"] = b
    with client(transport) as c:
        return get_json(c.get(f"https://api.marketstack.com/v1/{path}",
                              params={**params, "access_key": get_settings().marketstack_api_key}), "Marketstack")


def marketstack_symbol(state: dict, name: str, transport=None) -> str | None:
    """Blocking: the NSE symbol of the listed company called ``name`` (Marketstack ticker search), if one matches."""
    from ingestion.connectors.live.common import about

    for t in _marketstack(state, "tickers", {"search": name, "limit": 10}, transport).get("data") or []:
        if str(t.get("symbol", "")).endswith(".XNSE") and about(name, t.get("name") or ""):
            return t["symbol"].rsplit(".", 1)[0]
    return None


def marketstack_prices(state: dict, symbols: list[str], transport=None) -> tuple[list[str], list[str]]:
    """Blocking: the last PRICE_DAYS NSE closes for each symbol whose kept prices are older than
    MARKETSTACK_HOURS, kept like Alpha Vantage's. Returns (symbols kept, errors)."""
    from shared.config import get_settings

    done, errors = [], []
    px = state.get("market", {}).get("px", {})
    symbols = [s for s in symbols if not _fresh(px.get(s.upper()), timedelta(hours=MARKETSTACK_HOURS))]
    if not get_settings().marketstack_api_key or not symbols:
        return done, errors
    for i in range(0, len(symbols), MARKETSTACK_BATCH):
        batch = symbols[i:i + MARKETSTACK_BATCH]
        params = {"symbols": ",".join(f"{s.upper()}.XNSE" for s in batch), "limit": 1000,
                  "date_from": (datetime.now() - timedelta(days=PRICE_DAYS * 3 // 2)).strftime("%Y-%m-%d")}
        try:
            body = _marketstack(state, "eod", params, transport)
        except (SourceError, httpx.HTTPError) as e:
            errors.append(str(e) if str(e).startswith("Marketstack") else f"Marketstack: {e}")
            break
        series: dict[str, dict] = {}
        for row in body.get("data") or []:
            if row.get("close") is not None and row.get("date"):
                series.setdefault(row["symbol"].split(".")[0].upper(), {})[row["date"][:10]] = {"4. close": row["close"]}
        for s in batch:
            if series.get(s.upper()):
                keep_prices(state, s, series[s.upper()], "Marketstack")
                done.append(s)
            else:
                errors.append(f"Marketstack · {s}: no NSE prices")
    return done, errors


def _fresh(entry: dict | None, delta: timedelta) -> bool:
    return bool(entry and entry.get("at")) and datetime.now() - datetime.fromisoformat(entry["at"]) < delta


# ---------- refresh ----------
def _fill(state: dict, symbols: list[tuple[str, str]], transport=None, prices_only: set[str] = frozenset()) -> dict:
    """Blocking: prices and results for (NSE symbol, BSE symbol) pairs that are missing or stale, in order,
    until a budget runs out; only prices for the symbols in ``prices_only``."""
    from ingestion.connectors.live.filings import AlphaVantage, Fincrux

    av, fx = AlphaVantage(state, transport), Fincrux(state, transport)
    m = state.setdefault("market", {})
    done, errors = {"prices": [], "results": []}, []
    av_ok, fx_ok = av.configured, fx.configured
    no_prices = []  # left for Marketstack
    for nse, bse in symbols:
        if not _fresh(m.get("px", {}).get(nse), timedelta(hours=PRICE_HOURS)):
            if not av_ok:
                no_prices.append(nse)
            else:
                try:
                    keep_prices(state, nse, av.call({"function": "TIME_SERIES_DAILY", "symbol": bse, "outputsize": "compact"}).get("Time Series (Daily)") or {})
                    done["prices"].append(nse)
                except SourceError as e:
                    errors.append(str(e))
                    av_ok = "daily limit" not in str(e) and "Information" not in str(e)
                    no_prices.append(nse)
                except httpx.HTTPError as e:
                    errors.append(f"Alpha Vantage · {nse}: {e}")
                    no_prices.append(nse)
        kept = m.get("fin", {}).get(nse)
        if fx_ok and nse not in prices_only and not (_fresh(kept, timedelta(days=RESULTS_DAYS)) and "balance" in kept):  # kept before the annual tables were: fetch again
            try:
                keep_financials(state, nse, fx.get(f"financials/{nse}")["data"])
                done["results"].append(nse)
            except SourceError as e:
                errors.append(str(e))
                fx_ok = "daily limit" not in str(e)
            except (httpx.HTTPError, KeyError) as e:
                errors.append(f"Fincrux · {nse}: {e}")
    kept, ms_errors = marketstack_prices(state, list(dict.fromkeys(no_prices)), transport)
    return {**done, "prices": done["prices"] + kept, "errors": errors + ms_errors}


async def refresh(db: AsyncSession, co: str | None = None, transport=None, watched_prices: bool = False) -> dict:
    """The RPG companies' own figures (all of them, or ``co``), then — when ``co`` is given — its listed
    peers that have none or stale ones. ``watched_prices`` (the daily run): also every listed watched
    company's share prices, for the slump signal — free when the news run's Alpha Vantage calls kept them."""
    from radar.bridge import CO_TO_CODE
    from services.company_research import PROFILES
    from services.ingest import RUN_LOCK

    codes = [CO_TO_CODE[co]] if co else list(PROFILES)
    symbols = [(PROFILES[c][2], f"{PROFILES[c][2]}.BSE") for c in codes if PROFILES[c][2]]
    async with RUN_LOCK:  # the budgets live in the shared ``live`` state
        live = await state_store.load(db, "live")
        only: set[str] = set()
        if co:
            symbols += [(p["nse_symbol"], p["bse"]) for p in peers(co, live)]
        elif watched_prices:
            own = {s for s, _ in symbols}
            extra = list(dict.fromkeys((p["nse_symbol"].upper(), p["bse"]) for c in CO_TO_CODE for p in peers(c, live)
                                       if p["nse_symbol"].upper() not in own))
            symbols += extra
            only = {s for s, _ in extra}
        res = await asyncio.to_thread(_fill, live, symbols, transport, only)
        await state_store.save(db, "live", live)
        await db.commit()
    return res


# ---------- the comparison ----------
def peers(co: str, live: dict) -> list[dict]:
    """``co``'s listed watched companies (an NSE symbol is known), with their BSE symbol for prices."""
    from radar.store import STORE

    sym = live.get("symbols") or {}
    return [{"entity_id": w["id"], "name": w["name"], "role": w.get("role", "competitor"), "nse_symbol": w["nse_symbol"],
             "bse": (sym.get(str(w["id"])) or {}).get("bse") or f"{w['nse_symbol']}.BSE"}
            for w in (STORE.live_meta.get("watch") or {}).get(co, []) if w["status"] == "watching" and w.get("nse_symbol")]


def _change(a, b) -> float | None:
    a, b = num(a), num(b)
    return round((a - b) / abs(b) * 100, 1) if b else None


def metrics(fin: dict | None, px: dict | None) -> dict:
    out: dict = {"has_results": bool(fin and len(fin.get("sales") or []) >= 1), "has_prices": bool(px and px.get("closes"))}
    if out["has_results"]:
        s, p, o, q = fin["sales"], fin["profit"], fin["opm"], fin["quarters"]
        h = health(fin)
        out.update(health=h, debt_to_equity=h.get("debt_to_equity"), interest_cover=h.get("interest_cover"), roce=h.get("roce"),
                   sales_cagr_3y=h.get("sales_cagr_3y"), quarter=q[-1] if q else None, sales_q=num(s[-1]), profit_q=num(p[-1]) if p else None,
                   ttm_sales=round(sum(num(x) for x in s[-4:])) if len(s) >= 4 else None,
                   ttm_profit=round(sum(num(x) for x in p[-4:])) if len(p) >= 4 else None,
                   sales_yoy=_change(s[-1], s[-5]) if len(s) >= 5 else None,
                   profit_yoy=_change(p[-1], p[-5]) if len(p) >= 5 else None,
                   opm=num(o[-1]) if o else None, opm_series=[_figure(x) for x in o], sales_series=[_figure(x) for x in s], profit_series=[_figure(x) for x in p], quarters=q,
                   promoters=num(fin["holding"].get("Promoters", [None])[-1]) if fin["holding"].get("Promoters") else None,
                   fiis=num(fin["holding"].get("FIIs", [None])[-1]) if fin["holding"].get("FIIs") else None,
                   results_at=fin["at"][:10])
    if out["has_prices"]:
        c = px["closes"]
        out.update(close=c[-1][1], close_date=c[-1][0], chg_30=_change(c[-1][1], c[-31][1]) if len(c) >= 31 else None,
                   chg_period=_change(c[-1][1], c[0][1]), period_from=c[0][0], prices=c, prices_at=px["at"][:10])
    return out


def _median(rows: list[dict], k: str) -> float | None:
    v = [r[k] for r in rows if r.get(k) is not None]
    return round(median(v), 1) if v else None


def standing(own: dict, others: list[dict], co: str, sized_peers: list[dict] | None = None) -> list[dict]:
    """Plain sentences on where ``co`` stands against its listed peers, one per measure with data;
    the market-cap rank counts every peer with a known market cap (``sized_peers``)."""
    out = []
    sized = sorted([r for r in [own, *(sized_peers if sized_peers is not None else others)] if r.get("market_cap")], key=lambda r: -r["market_cap"])
    if own.get("market_cap") and len(sized) > 1:
        out.append({"measure": "Market cap", "verdict": "info",
                    "text": f"₹{own['market_cap']:,.0f} cr: number {sized.index(own) + 1} of {len(sized)} by size among {co} and its listed watched companies with a known market cap."})
    # (field, label, unit, 1 when higher is better / -1 when lower is, the gap that counts as level, signed)
    for k, label, unit, better, tol, signed in (("sales_yoy", "Sales growth, latest quarter year on year", "%", 1, 1, True),
                                                ("profit_yoy", "Net profit growth, latest quarter year on year", "%", 1, 1, True),
                                                ("sales_cagr_3y", "Sales growth a year, last 3 years", "%", 1, 1, True),
                                                ("opm", "Operating margin, latest quarter", "%", 1, 1, False),
                                                ("roce", "Return on capital employed (ROCE)", "%", 1, 1, False),
                                                ("debt_to_equity", "Debt to equity", "x", -1, 0.1, False),
                                                ("interest_cover", "Interest cover", "x", 1, 0.5, False),
                                                ("chg_30", "Share price, last 30 trading days", "%", 1, 1, True),
                                                ("chg_period", "Share price, last ~100 trading days", "%", 1, 1, True)):
        mine, med = own.get(k), _median(others, k)
        if mine is None or med is None:
            continue
        diff = (mine - med) * better
        verdict = "ahead" if diff > tol else "behind" if diff < -tol else "level"
        sign = lambda v: f"{v:+.1f}{unit}" if signed else (f"{v:.2f}{unit}" if unit == "x" else f"{v:.1f}{unit}")
        out.append({"measure": label, "verdict": verdict,
                    "text": f"{co} {sign(mine)} against a median of {sign(med)} for {sum(1 for r in others if r.get(k) is not None)} watched companies: {verdict}."})
    return out


def expected(fin: dict | None) -> dict | None:
    """The average quarter over the last QUARTERS (sales, net profit, operating margin). For small deals the
    average of the 8 quarters before a deal predicted the target's figures after it (Dogan and Ugurlu 2024,
    J. Risk Financial Manag. 17: 581), so the thesis shows it as the level to expect, not a forecast."""
    if not fin or len(fin.get("sales") or []) < 4:
        return None
    avg = lambda v: round(sum(num(x) for x in v) / len(v), 1) if v else None
    q = fin.get("quarters") or []
    return {"quarters": len(fin["sales"]), "from": q[0] if q else None, "to": q[-1] if q else None,
            "sales": avg(fin["sales"]), "profit": avg(fin.get("profit") or []), "opm": avg(fin.get("opm") or [])}


def company(symbol: str | None, live: dict) -> dict:
    """One company's figures for a thesis: results, balance sheet, multiples and the expected level."""
    if not symbol:
        return {"listed": False}
    m = live.get("market") or {}
    fin, px = (m.get("fin") or {}).get(symbol.upper()), (m.get("px") or {}).get(symbol.upper())
    if not fin and not px:
        return {"listed": True, "symbol": symbol, "pending": True}
    return {"listed": True, "symbol": symbol, "pending": False, **metrics(fin, px), "expected": expected(fin)}


def brief(symbol: str | None, live: dict) -> dict:
    """The one line an M&A signal card shows about a company's finances."""
    c = company(symbol, live)
    if not c["listed"]:
        return {**c, "label": "Not listed: no published accounts"}
    if c["pending"]:
        return {**c, "label": "Figures pending (Fincrux, 5 a day)"}
    h = c.get("health") or {}
    z = h.get("altman_z")
    bits = [f"{z['zone'].capitalize()} zone (Z {z['z']})"] if z else []
    if h.get("debt_to_equity") is not None:
        bits.append(f"debt {h['debt_to_equity']}x equity")
    if not bits and c.get("opm") is not None:
        bits.append(f"op. margin {c['opm']:.0f}%")
    if not bits and c.get("sales_yoy") is not None:
        bits.append(f"sales {c['sales_yoy']:+.0f}% YoY")
    return {"listed": True, "pending": False, "zone": z["zone"] if z else None, "stress": stress(h),
            "label": " · ".join(bits) or "Share price only"}


def view(co: str, live: dict, sizes: dict) -> dict:
    from radar.bridge import CO_TO_CODE
    from radar.store import STORE
    from services import company_size
    from services.company_research import PROFILES

    m = live.get("market") or {}
    fin, px = m.get("fin") or {}, m.get("px") or {}
    code = CO_TO_CODE[co]
    full, _, sym = PROFILES[code]
    own_size = sizes.get(company_size.rpg_key(code)) or {}
    own = {"name": co, "own": True, "role": "self", "nse_symbol": sym, "entity_id": None,
           "market_cap": (own_size.get("market_cap") or {}).get("cr"), **(metrics(fin.get(sym), px.get(sym)) if sym else {})}
    rows = []
    for p in peers(co, live):
        size = sizes.get(company_size.entity_key(p["entity_id"])) or {}
        rows.append({**p, "own": False, "market_cap": (size.get("market_cap") or {}).get("cr"),
                     **metrics(fin.get(p["nse_symbol"].upper()), px.get(p["nse_symbol"].upper()))})
    for r in [own, *rows]:  # Fincrux's market cap, where it has one, is the exchange figure: better than a search answer
        r["market_cap"] = (r.get("health") or {}).get("market_cap") or r["market_cap"]
    rows.sort(key=lambda r: -(r.get("market_cap") or 0))
    unlisted = [w["name"] for w in (STORE.live_meta.get("watch") or {}).get(co, [])
                if w["status"] == "watching" and not w.get("nse_symbol")]
    with_data = [r for r in rows if r.get("has_results") or r.get("has_prices")]
    return {"company": co, "listed": bool(sym), "nse_symbol": sym, "own": own, "peers": rows,
            "standing": standing(own, with_data, co, rows) if sym else [],
            "pending": [r["name"] for r in rows if not (r.get("has_results") or r.get("has_prices"))],
            "unlisted": unlisted}
