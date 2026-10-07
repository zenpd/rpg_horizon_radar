"""Live connectors, which companies are ingested, watchlist discovery, users,
SWOT briefs and their API. No test reaches the network: connectors get an
``httpx.MockTransport`` and the LLM a FakeDrafter."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from agents import watchlist_discovery
from db import base
from db.models import AuditLog, ClusterSubsidiaryLink, Entity, RawSignal, SignalCluster
from ingestion.connectors.live.common import SourceError, classify_headline, short_name
from ingestion.connectors.live.filings import NSE, Fincrux, nse_type
from services import company_research
from services.ingest import run_ingest_all
from tests.helpers import FIRST, SECOND, login

# One clock for the fake feeds, fixed for the test run (start of today, so the announcements stay
# inside NSE's 21-day window): re-running ingestion must see the very same announcements.
NOW = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def arun(coro):
    return asyncio.run(coro)


class FakeDrafter:
    model = "fake:model"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def draft(self, system, messages, schema, name="draft"):
        self.calls.append(list(messages))
        reply = self.replies.pop(0)
        return reply if isinstance(reply, str) else json.dumps(reply)


# ---------- fake NSE + Fincrux ----------
def market_transport(calls: list[str], symbol: str = "APOLLOTYRE"):
    now = NOW

    def ann(days_ago, desc, text):
        d = now - timedelta(days=days_ago)
        return {"sort_date": d.strftime("%Y-%m-%d %H:%M:%S"), "desc": desc, "attchmntText": text,
                "attchmntFile": f"https://nse.example/{days_ago}.pdf", "sm_name": "Apollo Tyres Limited", "symbol": symbol}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(f"{req.url.host}{req.url.path}")
        if req.url.host == "www.nseindia.com":
            assert req.url.params["symbol"] == symbol
            if req.url.path.endswith("corporate-announcements"):
                return httpx.Response(200, json=[
                    ann(1, "Change in Director(s)", "Mr X has resigned as Independent Director with effect from today."),
                    ann(2, "Change in Director(s)", "Appointment of Ms Y as Additional Director."),
                    ann(3, "Trading Window", "Trading window closure."),
                    ann(4, "Credit Rating", "CRISIL has reaffirmed the rating at AA+/Stable."),
                    ann(5, "Disclosure under SEBI Takeover Regulations", "Acquisition of 5% stake by an investor."),
                    ann(40, "Outcome of Board Meeting", "Old results.")])
            if req.url.path.endswith("corporate-pledgedata"):
                return httpx.Response(200, json={"data": [{"broadcastDt": "30-Sep-2026 16:30:29", "percSharesPledged": "9.82",
                                                          "percPromoterHolding": "  37.33", "disclosureToDate": "31-Mar-2026"}]})
        if req.url.host == "api.fincrux.org":
            assert req.url.params["api_key"] == "fx"
            return httpx.Response(200, json={"success": "true", "data": {
                "last_updated_at": "2026-09-26T22:31:46",
                "quaterly_results": [["Category", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"],
                                     ["Sales", "5,000", "5,100", "5,139", "5,237", "5,462"], ["OPM %", "15%", "14%", "15%", "15%", "12%"],
                                     ["Net Profit", "400", "420", "449", "903", "304"]],
                "shareholding_quarterly": [["Category", "Mar 2026", "Jun 2026"], ["Promoters", "36.93%", "36.93%"],
                                           ["FIIs", "12.15%", "10.09%"], ["DIIs", "27.56%", "29.05%"]]}})
        raise AssertionError(f"unexpected call to {req.url}")

    return httpx.MockTransport(handler)


def _entity(**kw) -> Entity:
    e = Entity(category="Competitor · tyres", origin="discovered", **kw)
    return e


# ---------- pure rules ----------
def test_headline_classifier_keeps_only_weighed_events():
    assert classify_headline("Apollo Tyres CFO resigns amid restructuring") == "leadership_churn"
    assert classify_headline("ICRA downgrades Kalpataru Projects to A-") == "credit_downgrade"
    assert classify_headline("NCLT admits insolvency plea against McLeod Russel") == "legal_action"
    assert classify_headline("Apollo Tyres bags Rs 500 crore order") == "press_opportunity"
    assert classify_headline("Apollo Tyres share price today live updates") is None
    assert classify_headline("JK Tyre launches four new OTR tyres for construction and mining") == "press_opportunity"
    assert classify_headline("KEC International wins orders worth Rs 1,300 crore") == "press_opportunity"
    assert classify_headline("Kalpataru Projects rallies 7% on receiving new orders worth Rs 2,445 crore") == "press_opportunity", \
        "a share-price rally is not motorsport"
    assert classify_headline("Havells Super Hi-Speed BLDC+ and Agentic AI Fans launched") == "press_opportunity"
    for noise in ("Rajiv Yadav wins 2026 JK Tyre Rally of Himalayas", "MRF Indian National Racing Challenge: Ishaan notches up maiden win",
                  "Erigaisi Arjun vs Wei Yi | Brilliant Endgame Win in Petroff Defence | Tech Mahindra GCL 2026",
                  "Cliff edge launch: RC Goodyear Inflatoplan inflatable aircraft! #Shorts", "CEAT wins award for best brand"):
        assert classify_headline(noise) is None, noise
    assert short_name("Apollo Tyres Ltd") == "Apollo Tyres"


def test_nse_announcements_are_typed_and_routine_ones_dropped():
    assert nse_type("Change in Director(s)", "Mr X has resigned as director") == "leadership_churn"
    assert nse_type("Change in Director(s)", "Appointment of Ms Y") is None
    assert nse_type("Credit Rating", "Rating reaffirmed at AA+") is None
    assert nse_type("Credit Rating", "Rating downgraded to A") == "credit_downgrade"
    assert nse_type("Trading Window", "closure") is None


def test_nse_and_fincrux_turn_filings_into_signals(settings):
    settings.nse_enabled = True
    settings.fincrux_api_key = "fx"
    e = _entity(id=999, name="Apollo Tyres Ltd", sectors=["tyres"], status="watching", nse_symbol="APOLLOTYRE")
    calls: list[str] = []
    t = market_transport(calls)
    nse = NSE({}, t).pull(e, "APOLLOTYRE")
    assert [s["signal_type"] for s in nse] == ["leadership_churn", "deal_activity", "promoter_pledge"]
    assert nse[0]["source_url"] == "https://nse.example/1.pdf" and nse[0]["provider"] == "NSE"
    assert nse[-1]["headline"] == "Apollo Tyres Ltd promoters have pledged 9.82% of their shares"

    state: dict = {}
    fx = {s["signal_type"]: s for s in Fincrux(state, t).pull(e, "APOLLOTYRE")}
    assert fx["earnings_decline"]["headline"] == "Apollo Tyres Ltd Jun 2026 quarter: net profit -24% YoY, sales +9% YoY"
    assert fx["stake_selldown"]["headline"] == "Apollo Tyres Ltd Jun 2026 quarter: FIIs down from 12.15% to 10.09%"
    assert state["budget"]["Fincrux"]["used"] == 1


def test_fincrux_stops_at_its_daily_limit(settings):
    settings.fincrux_api_key = "fx"
    calls: list[str] = []
    state = {"budget": {"Fincrux": {"date": datetime.now().strftime("%Y-%m-%d"), "used": 5}}}
    with pytest.raises(SourceError, match="daily limit of 5"):
        Fincrux(state, market_transport(calls)).pull(_entity(id=1, name="X", sectors=[], status="watching"), "X")
    assert calls == []


# ---------- what is ingested ----------
def test_every_watched_company_is_ingested_and_a_removed_one_is_not(seeded, settings):
    settings.nse_enabled = True
    settings.fincrux_api_key = "fx"
    calls: list[str] = []

    async def go():
        async with base.get_db_session() as db:
            apollo = _entity(name="Apollo Tyres Ltd", sectors=["tyres", "mobility"], status="dismissed", nse_symbol="APOLLOTYRE")
            db.add(apollo)
            await db.commit()
            await run_ingest_all(db, market_transport(calls))
            assert calls == [], "a removed company is not fetched"

            apollo.status = "watching"
            await db.commit()
            result = await run_ingest_all(db, market_transport(calls))
            rows = (await db.execute(select(RawSignal).where(RawSignal.entity_id == apollo.id))).scalars().all()
            assert {r.provider for r in rows} == {"NSE", "Fincrux"}
            assert "CEAT" in result["changed_subsidiaries"]
            cluster = (await db.execute(select(SignalCluster).where(SignalCluster.entity_id == apollo.id))).scalar_one()
            links = (await db.execute(select(ClusterSubsidiaryLink).where(ClusterSubsidiaryLink.cluster_id == cluster.id))).scalars().all()
            assert {l.subsidiary_code for l in links} == {"CEAT"}

            before = len(calls)
            again = await run_ingest_all(db, market_transport(calls))
            assert again["new_raw_signals"] == 0, "re-runs are idempotent"
            assert not [c for c in calls[before:] if "fincrux" in c], "Fincrux is paced weekly"
    arun(go())


# ---------- research on the RPG companies themselves ----------
def research_transport(calls: list[str]):
    q = [["Category", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026", "Dec 2026", "Mar 2027"],
         ["Sales", "3000", "3100", "3200", "3300", "3400", "3450", "3500", "3600"],
         ["Net Profit", "100", "110", "120", "130", "150", "140", "160", "170"],
         ["OPM %", "11%", "11%", "12%", "12%", "13%", "13%", "13%", "14%"]]
    sh = [["Category", "Dec 2026", "Mar 2027"], ["Promoters", "47.2", "47.2"], ["FIIs", "18.0", "19.5"]]

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        if req.url.host == "api.fincrux.org":
            assert req.url.path.endswith("/financials/CEATLTD")
            return httpx.Response(200, json={"success": "true", "data": {"last_updated_at": "2027-04-20T10:00:00",
                                                                          "quaterly_results": q, "shareholding_quarterly": sh}})
        if req.url.host == "api.tavily.com":
            body = json.loads(req.content)
            if body["topic"] == "news":
                return httpx.Response(200, json={"results": [
                    {"title": "CEAT opens a new radial plant", "url": "https://news.example/plant", "content": "Capacity rises.",
                     "published_date": "Mon, 05 Oct 2026 10:00:00 GMT"},
                    {"title": "Tyre stocks rally", "url": "https://news.example/rally", "content": "CEAT among gainers."}]})
            return httpx.Response(200, json={"results": [
                {"title": "CEAT annual report", "url": "https://www.ceat.example/ar", "content": "CEAT holds about 14% of the Indian tyre market."},
                {"title": "Unrelated page", "url": "https://other.example", "content": "Nothing about the company."}]})
        if req.url.host == "gnews.io":
            return httpx.Response(200, json={"articles": [
                {"title": "CEAT opens a new radial plant", "description": "Same story.", "publishedAt": "2026-10-05T10:00:00Z",
                 "url": "https://news.example/plant2", "source": {"name": "Mint"}}]})
        raise AssertionError(req.url)
    return httpx.MockTransport(handler)


def test_company_research_collects_results_shareholding_web_and_news(settings):
    settings.fincrux_api_key, settings.tavily_api_key, settings.gnews_api_key = "fx", "tv", "gn"
    calls: list[str] = []
    state: dict = {}
    facts, errors = company_research.collect("CEAT", state, transport=research_transport(calls))
    assert errors == []
    texts = [f["text"] for f in facts]
    assert texts[0] == ("CEAT Limited Mar 2027 quarter: sales ₹3600 cr (+9% year on year), net profit ₹170 cr (+31% year on year). "
                        "Operating margin 14% against 12% a year earlier.")
    assert texts[1].startswith("CEAT Limited last four quarters (Jun 2026 to Mar 2027): sales ₹13,950 cr (+11% on the four before)")
    assert texts[2] == "CEAT Limited shareholding, Mar 2027 quarter: Promoters 47.2 (47.2 a quarter earlier), FIIs 19.5 (18.0 a quarter earlier)."
    assert any("14% of the Indian tyre market" in t for t in texts)
    assert not any("Unrelated" in t or "Tyre stocks rally" in t for t in texts), "only results that name the company"
    assert sum("radial plant" in t for t in texts) == 1, "the same story from two sources is kept once"
    assert state["budget"]["Fincrux"]["used"] == 1, "research shares the connectors' Fincrux budget"
    assert company_research.due({"at": datetime.now().isoformat(), "facts": facts}) is False
    assert company_research.due({"at": (datetime.now() - timedelta(days=8)).isoformat(), "facts": facts}) is True
    yesterday = (datetime.now() - timedelta(days=1, minutes=1)).isoformat()
    assert company_research.due({"at": yesterday, "facts": facts, "errors": ["Fincrux: daily limit"]}) is True, "a failed source is retried next day"
    assert company_research.due({"at": yesterday, "facts": facts, "errors": []}) is False


def test_company_research_skips_weak_sources():
    assert company_research.usable({"url": "https://m.economictimes.com/news/x", "source": "m.economictimes.com"})
    assert company_research.usable({"url": None, "source": "Fincrux quarterly results"})
    for url in ("https://www.instagram.com/p/1", "https://rocketreach.co/ceat", "https://in.investing.com/equities/ceat", "https://x.com/ceat"):
        assert not company_research.usable({"url": url, "source": "web"}), url


def test_company_research_skips_filings_for_an_unlisted_company_and_reports_errors(settings):
    settings.tavily_api_key = "tv"

    def broken(req):
        return httpx.Response(429)
    facts, errors = company_research.collect("RAYCHEM", {}, transport=httpx.MockTransport(broken))
    assert facts == [] and [e.split(" · ")[0] for e in errors] == ["Tavily", "Tavily news"]
    assert errors[0].startswith("Tavily · Raychem RPG")


def test_company_research_follows_the_swot_parameters(settings):
    settings.fincrux_api_key, settings.tavily_api_key, settings.gnews_api_key = "fx", "tv", "gn"
    calls: list[str] = []
    only_results = {"sources": ["results"], "factors": ["financial"], "sector_queries": []}
    facts, _ = company_research.collect("CEAT", {}, only_results, research_transport(calls))
    assert calls == ["api.fincrux.org"] and {f["kind"] for f in facts} == {"results"}, "shareholding, web and news are off"
    calls.clear()
    two_factors = {"sources": ["web"], "factors": ["financial", "supply"], "sector_queries": []}
    facts, _ = company_research.collect("CEAT", {}, two_factors, research_transport(calls))
    assert calls == ["api.tavily.com", "api.tavily.com"], "one web search per ticked factor"
    assert {f["factor"] for f in facts} <= {"financial", "supply"}


# ---------- discovery ----------
def tavily_transport(calls: list[dict]):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "api.tavily.com"
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"results": [
            {"title": "Top tyre companies in India: MRF, JK Tyre and Apollo", "url": "https://example.com/a", "content": "MRF leads; JK Tyre & Industries follows."},
            {"title": "Balkrishna Industries widens off-highway lead", "url": "https://example.com/b", "content": "BKT ..."}]})
    return httpx.MockTransport(handler)


def test_discovery_watches_grounded_companies_for_every_subsidiary(seeded, settings):
    settings.tavily_api_key = "tv"
    calls: list[dict] = []
    none = {"companies": []}  # the other five subsidiaries (searched in code order, CEAT first)
    drafter = FakeDrafter({"companies": [
        {"name": "MRF", "kind": "competitor", "why": "Largest Indian tyre maker.", "results": [1]},
        {"name": "Imaginary Tyre Co", "kind": "competitor", "why": "Not in the results.", "results": [1]},
        {"name": "CEAT Limited", "kind": "competitor", "why": "The subsidiary itself.", "results": [1]},
        {"name": "Balkrishna Industries", "kind": "adjacent", "why": "Off-highway tyres.", "results": [2]}]}, *[none] * 5)

    async def go():
        async with base.get_db_session() as db:
            res = await watchlist_discovery.discover(db, drafter=drafter, transport=tavily_transport(calls))
            assert res["subsidiaries"] == ["CEAT", "HARRISONS", "KEC", "RAYCHEM", "RPGLS", "ZENSAR"], "every subsidiary is searched"
            assert res["added"] == ["MRF", "Balkrishna Industries"]
            mrf = (await db.execute(select(Entity).where(Entity.name == "MRF"))).scalar_one()
            assert (mrf.status, mrf.origin, mrf.sectors) == ("watching", "discovered", ["tyres", "mobility"]), "watched at once"
            assert mrf.watched_since is not None
            assert mrf.discovery["sources"] == [{"title": "Top tyre companies in India: MRF, JK Tyre and Apollo", "url": "https://example.com/a"}]
            mrf.status = "dismissed"
            await db.commit()
            again = await watchlist_discovery.discover(db, drafter=FakeDrafter({"companies": [
                {"name": "MRF", "kind": "competitor", "why": "Largest Indian tyre maker.", "results": [1]},
                {"name": "Balkrishna Industries Ltd", "kind": "adjacent", "why": "Off-highway tyres.", "results": [2]}]}, *[none] * 5),
                transport=tavily_transport(calls))
            assert again["added"] == [] and again["refreshed"] == ["MRF", "Balkrishna Industries"],                 "'Balkrishna Industries Ltd' is the company already watched as 'Balkrishna Industries'"
            await db.refresh(mrf)
            assert mrf.status == "dismissed", "a removed company is never re-added"
    arun(go())
    assert len(calls) == 24, "two searches per subsidiary, twice"


# ---------- API ----------
def test_any_user_changes_the_watchlist_and_it_is_in_the_activity_history(seeded):
    second = login(seeded, SECOND)
    assert seeded.get("/api/v1/watchlist").status_code == 401, "a login is still needed"
    r = seeded.post("/api/v1/watchlist", headers=second, json={"name": "JK Tyre & Industries", "sectors": ["tyres"], "nse_symbol": "jktyre"})
    assert r.status_code == 201 and r.json()["status"] == "watching" and r.json()["nse_symbol"] == "JKTYRE"
    assert r.json()["watched_since"] is not None
    assert seeded.post("/api/v1/watchlist", headers=second, json={"name": "X", "sectors": ["unknown"]}).status_code == 422
    eid = r.json()["id"]
    r = seeded.patch(f"/api/v1/watchlist/{eid}", headers=second, json={"status": "dismissed"})
    assert r.json()["status"] == "dismissed"

    async def audit_rows():
        async with base.get_db_session() as db:
            return (await db.execute(select(AuditLog.detail).where(AuditLog.resource_type == "entity", AuditLog.resource_id == str(eid)))).scalars().all()
    details = arun(audit_rows())
    assert any("watchlist_add" in d for d in details) and any("status watching->dismissed" in d for d in details)
    history = seeded.get("/api/v1/audit-log", headers=second).json()
    assert any(h["action"] == "watchlist_change" and h["reviewer_name_snapshot"] == "Second User" for h in history)
    sources = seeded.get("/api/v1/watchlist/sources", headers=second).json()
    assert {c["name"] for c in sources["connectors"]} >= {"NSE", "Fincrux", "GNews", "Adzuna", "EPO patents"}
    assert sources["scheduler"]["enabled"] is False


def test_users_add_and_remove_each_other_but_not_themselves(seeded):
    first, second = login(seeded, FIRST), login(seeded, SECOND)
    r = seeded.post("/api/v1/reviewers", headers=second, json={"name": "Third User", "email": "third@test.local", "password": "pw-third"})
    assert r.status_code == 200 and set(r.json()) == {"id", "name", "email", "created_at"}, "users have no roles"
    assert seeded.post("/api/v1/reviewers", headers=first, json={"name": "Again", "email": "third@test.local", "password": "x"}).status_code == 400
    me = seeded.get("/api/v1/auth/me", headers=first).json()
    assert seeded.delete(f"/api/v1/reviewers/{me['id']}", headers=first).status_code == 400
    assert seeded.delete(f"/api/v1/reviewers/{r.json()['id']}", headers=first).status_code == 200


def test_ingest_runs_as_a_background_job(seeded):
    second = login(seeded, SECOND)
    r = seeded.post("/api/v1/ingest/run", headers=second)
    assert r.status_code == 202 and r.json()["kind"] == "ingest"
    job = r.json()
    for _ in range(100):
        job = seeded.get(f"/api/v1/jobs/{job['id']}", headers=second).json()
        if job["status"] != "running":
            break
        time.sleep(0.2)
    assert job["status"] == "completed", job
    assert job["result"]["via"] == "inline_fallback"
