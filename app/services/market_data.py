"""The financial market: each RPG company's quarterly results, shareholding and share price against
its listed watched companies'. Rule-based, no model.

The figures come from the two quota-limited feeds the radar already calls: Fincrux (quarterly results
and shareholding, 5 calls a day) and Alpha Vantage (daily BSE closing prices, 25 calls a day). Every
call the ingestion connectors and the company research make keeps a compact copy of the figures in
the shared ``live`` state (``keep_financials`` / ``keep_prices``), so the comparison costs no extra
calls; refresh() fills the RPG companies' own figures each day (services/scheduler.py, after the
news run) and, on demand, a company's peers that have none yet, within what the budgets leave.
Market caps come from services/company_size.py."""
from __future__ import annotations

import asyncio
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


# ---------- kept by the connectors ----------
def keep_financials(state: dict, symbol: str, d: dict) -> None:
    """Keep the last QUARTERS quarters of sales, net profit and operating margin, and the shareholding."""
    if not symbol:
        return
    q = {row[0]: row[1:] for row in d.get("quaterly_results") or []}  # sic, the API's spelling
    s = {row[0]: row[1:] for row in d.get("shareholding_quarterly") or []}
    cut = lambda v: list(v or [])[-QUARTERS:]
    state.setdefault("market", {}).setdefault("fin", {})[symbol.upper()] = {
        "at": datetime.now().isoformat(timespec="seconds"), "quarters": cut(q.get("Category")), "sales": cut(q.get("Sales")),
        "profit": cut(q.get("Net Profit")), "opm": cut(q.get("OPM %")),
        "holding_quarters": list(s.get("Category") or [])[-4:], "holding": {k: list(s.get(k) or [])[-4:] for k in SHAREHOLDERS}}


def keep_prices(state: dict, symbol: str, series: dict) -> None:
    """Keep the last PRICE_DAYS daily closes from an Alpha Vantage TIME_SERIES_DAILY reply."""
    if not symbol or not series:
        return
    days = sorted(series)[-PRICE_DAYS:]
    state.setdefault("market", {}).setdefault("px", {})[symbol.upper()] = {
        "at": datetime.now().isoformat(timespec="seconds"), "closes": [[d, round(num(series[d]["4. close"]), 2)] for d in days]}


def _fresh(entry: dict | None, delta: timedelta) -> bool:
    return bool(entry and entry.get("at")) and datetime.now() - datetime.fromisoformat(entry["at"]) < delta


# ---------- refresh ----------
def _fill(state: dict, symbols: list[tuple[str, str]], transport=None) -> dict:
    """Blocking: prices and results for (NSE symbol, BSE symbol) pairs that are missing or stale, in order,
    until a budget runs out."""
    from ingestion.connectors.live.filings import AlphaVantage, Fincrux

    av, fx = AlphaVantage(state, transport), Fincrux(state, transport)
    m = state.setdefault("market", {})
    done, errors = {"prices": [], "results": []}, []
    av_ok, fx_ok = av.configured, fx.configured
    for nse, bse in symbols:
        if av_ok and not _fresh(m.get("px", {}).get(nse), timedelta(hours=PRICE_HOURS)):
            try:
                keep_prices(state, nse, av.call({"function": "TIME_SERIES_DAILY", "symbol": bse, "outputsize": "compact"}).get("Time Series (Daily)") or {})
                done["prices"].append(nse)
            except SourceError as e:
                errors.append(str(e))
                av_ok = "daily limit" not in str(e) and "Information" not in str(e)
            except httpx.HTTPError as e:
                errors.append(f"Alpha Vantage · {nse}: {e}")
        if fx_ok and not _fresh(m.get("fin", {}).get(nse), timedelta(days=RESULTS_DAYS)):
            try:
                keep_financials(state, nse, fx.get(f"financials/{nse}")["data"])
                done["results"].append(nse)
            except SourceError as e:
                errors.append(str(e))
                fx_ok = "daily limit" not in str(e)
            except (httpx.HTTPError, KeyError) as e:
                errors.append(f"Fincrux · {nse}: {e}")
    return {**done, "errors": errors}


async def refresh(db: AsyncSession, co: str | None = None, transport=None) -> dict:
    """The RPG companies' own figures (all of them, or ``co``), then — when ``co`` is given — its listed
    peers that have none or stale ones."""
    from radar.bridge import CO_TO_CODE
    from services.company_research import PROFILES
    from services.ingest import RUN_LOCK

    codes = [CO_TO_CODE[co]] if co else list(PROFILES)
    symbols = [(PROFILES[c][2], f"{PROFILES[c][2]}.BSE") for c in codes if PROFILES[c][2]]
    if co:
        symbols += [(p["nse_symbol"], p["bse"]) for p in peers(co, {})]
    async with RUN_LOCK:  # the budgets live in the shared ``live`` state
        live = await state_store.load(db, "live")
        res = await asyncio.to_thread(_fill, live, symbols, transport)
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
        out.update(quarter=q[-1] if q else None, sales_q=num(s[-1]), profit_q=num(p[-1]) if p else None,
                   ttm_sales=round(sum(num(x) for x in s[-4:])) if len(s) >= 4 else None,
                   ttm_profit=round(sum(num(x) for x in p[-4:])) if len(p) >= 4 else None,
                   sales_yoy=_change(s[-1], s[-5]) if len(s) >= 5 else None,
                   profit_yoy=_change(p[-1], p[-5]) if len(p) >= 5 else None,
                   opm=num(o[-1]) if o else None, opm_series=[num(x) for x in o], sales_series=[num(x) for x in s], quarters=q,
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
    for k, label, unit, better in (("sales_yoy", "Sales growth, latest quarter year on year", "%", 1),
                                   ("profit_yoy", "Net profit growth, latest quarter year on year", "%", 1),
                                   ("opm", "Operating margin, latest quarter", "%", 1),
                                   ("chg_30", "Share price, last 30 trading days", "%", 1),
                                   ("chg_period", "Share price, last ~100 trading days", "%", 1)):
        mine, med = own.get(k), _median(others, k)
        if mine is None or med is None:
            continue
        diff = (mine - med) * better
        verdict = "ahead" if diff > 1 else "behind" if diff < -1 else "level"
        sign = lambda v: f"{v:+.1f}{unit}" if k != "opm" else f"{v:.1f}{unit}"
        out.append({"measure": label, "verdict": verdict,
                    "text": f"{co} {sign(mine)} against a median of {sign(med)} for {sum(1 for r in others if r.get(k) is not None)} watched companies: {verdict}."})
    return out


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
    rows.sort(key=lambda r: -(r.get("market_cap") or 0))
    unlisted = [w["name"] for w in (STORE.live_meta.get("watch") or {}).get(co, [])
                if w["status"] == "watching" and not w.get("nse_symbol")]
    with_data = [r for r in rows if r.get("has_results") or r.get("has_prices")]
    return {"company": co, "listed": bool(sym), "nse_symbol": sym, "own": own, "peers": rows,
            "standing": standing(own, with_data, co, rows) if sym else [],
            "pending": [r["name"] for r in rows if not (r.get("has_results") or r.get("has_prices"))],
            "unlisted": unlisted}
