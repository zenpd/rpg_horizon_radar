"""Live connectors, the approval gate on real companies, watchlist discovery,
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

from db import base
from db.models import AuditLog, ClusterSubsidiaryLink, Entity, RawSignal, SignalCluster, Subsidiary
from ingestion.connectors.live.common import SourceError, classify_headline, short_name
from ingestion.connectors.live.filings import NSE, Fincrux, nse_type
from services import discovery, swot
from services.ingest import run_ingest_for_open_subsidiaries

PASSWORD = "ChangeMe123!"


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


def login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------- fake NSE + Fincrux ----------
def market_transport(calls: list[str], symbol: str = "APOLLOTYRE"):
    now = datetime.now()

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
    e = Entity(category="Competitor · tyres", is_fictional=False, origin="discovered", **kw)
    return e


# ---------- pure rules ----------
def test_headline_classifier_keeps_only_weighed_events():
    assert classify_headline("Apollo Tyres CFO resigns amid restructuring") == "leadership_churn"
    assert classify_headline("ICRA downgrades Kalpataru Projects to A-") == "credit_downgrade"
    assert classify_headline("NCLT admits insolvency plea against McLeod Russel") == "legal_action"
    assert classify_headline("Apollo Tyres bags Rs 500 crore order") == "press_opportunity"
    assert classify_headline("Apollo Tyres share price today live updates") is None
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


# ---------- the approval gate ----------
def test_real_company_is_ingested_only_once_approved_and_gate_open(seeded, settings):
    settings.nse_enabled = True
    settings.fincrux_api_key = "fx"
    calls: list[str] = []

    async def go():
        async with base.get_db_session() as db:
            proposed = _entity(name="Apollo Tyres Ltd", sectors=["tyres", "mobility"], status="proposed", nse_symbol="APOLLOTYRE")
            closed = _entity(name="Kalpataru Projects", sectors=["epc"], status="watching", nse_symbol="KPIL")  # KEC's gate is closed
            db.add_all([proposed, closed])
            await db.commit()
            await run_ingest_for_open_subsidiaries(db, market_transport(calls))
            assert calls == [], "neither a proposed company nor one in a closed sector is fetched"

            proposed.status = "watching"
            await db.commit()
            result = await run_ingest_for_open_subsidiaries(db, market_transport(calls))
            rows = (await db.execute(select(RawSignal).where(RawSignal.entity_id == proposed.id))).scalars().all()
            assert {r.provider for r in rows} == {"NSE", "Fincrux"}
            assert "CEAT" in result["changed_subsidiaries"]
            cluster = (await db.execute(select(SignalCluster).where(SignalCluster.entity_id == proposed.id))).scalar_one()
            links = (await db.execute(select(ClusterSubsidiaryLink).where(ClusterSubsidiaryLink.cluster_id == cluster.id))).scalars().all()
            assert {l.subsidiary_code for l in links} == {"CEAT"}

            before = len(calls)
            again = await run_ingest_for_open_subsidiaries(db, market_transport(calls))
            assert again["new_raw_signals"] == 0, "re-runs are idempotent"
            assert not [c for c in calls[before:] if "fincrux" in c], "Fincrux is paced weekly"
    arun(go())


# ---------- discovery ----------
def tavily_transport(calls: list[dict]):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.host == "api.tavily.com"
        calls.append(json.loads(req.content))
        return httpx.Response(200, json={"results": [
            {"title": "Top tyre companies in India: MRF, JK Tyre and Apollo", "url": "https://example.com/a", "content": "MRF leads; JK Tyre & Industries follows."},
            {"title": "Balkrishna Industries widens off-highway lead", "url": "https://example.com/b", "content": "BKT ..."}]})
    return httpx.MockTransport(handler)


def test_discovery_proposes_only_grounded_companies_for_open_gates(seeded, settings):
    settings.tavily_api_key = "tv"
    calls: list[dict] = []
    drafter = FakeDrafter({"companies": [
        {"name": "MRF", "kind": "competitor", "why": "Largest Indian tyre maker.", "results": [1]},
        {"name": "Imaginary Tyre Co", "kind": "competitor", "why": "Not in the results.", "results": [1]},
        {"name": "CEAT Limited", "kind": "competitor", "why": "The subsidiary itself.", "results": [1]},
        {"name": "Balkrishna Industries", "kind": "adjacent", "why": "Off-highway tyres.", "results": [2]}]})

    async def go():
        async with base.get_db_session() as db:
            res = await discovery.discover(db, drafter=drafter, transport=tavily_transport(calls))
            assert res["subsidiaries"] == ["CEAT"], "only gate-open subsidiaries are searched"
            assert res["proposed"] == ["MRF", "Balkrishna Industries"]
            mrf = (await db.execute(select(Entity).where(Entity.name == "MRF"))).scalar_one()
            assert (mrf.status, mrf.origin, mrf.is_fictional, mrf.sectors) == ("proposed", "discovered", False, ["tyres", "mobility"])
            assert mrf.discovery["sources"] == [{"title": "Top tyre companies in India: MRF, JK Tyre and Apollo", "url": "https://example.com/a"}]
            mrf.status = "dismissed"
            await db.commit()
            again = await discovery.discover(db, drafter=FakeDrafter({"companies": [
                {"name": "MRF", "kind": "competitor", "why": "Largest Indian tyre maker.", "results": [1]}]}), transport=tavily_transport(calls))
            assert again["proposed"] == [] and again["refreshed"] == ["MRF"]
            await db.refresh(mrf)
            assert mrf.status == "dismissed", "a dismissed company is never re-proposed"
    arun(go())
    assert len(calls) == 4


# ---------- SWOT ----------
EVIDENCE = [
    {"id": "E1", "kind": "signal", "entity": "Apollo Tyres Ltd", "signal_type": "earnings_decline", "provider": "Fincrux",
     "headline": "Apollo Tyres Ltd Jun 2026 quarter: net profit -24% YoY", "excerpt": "", "url": None, "observed_at": "2026-09-26T00:00:00"},
    {"id": "E2", "kind": "signal", "entity": "MRF", "signal_type": "press_opportunity", "provider": "GNews",
     "headline": "MRF bags large OEM order", "excerpt": "", "url": "https://x", "observed_at": "2026-09-20T00:00:00"},
    {"id": "N1", "kind": "team_note", "quadrant": "strengths", "headline": "Strong replacement-market brand"},
]


def _ext(text, entity, ev, impact=60, urgency=55):
    return {"text": text, "entity": entity, "impact": impact, "urgency": urgency, "evidence": ev, "reasoning": "Because the filing shows it."}


GOOD = {"summary": "A rival's profit fell while another won an OEM order.",
        "strengths": [{"text": "Strong brand.", "evidence": ["N1"], "reasoning": "The team rates the brand highly."}],
        "weaknesses": [],
        "opportunities": [_ext("Rival margin pressure opens replacement share.", "Apollo Tyres Ltd", ["E1"])],
        "threats": [_ext("MRF gains OEM volume.", "MRF", ["E2"])]}


def test_swot_check_catches_unsupported_items():
    bad = {**GOOD, "weaknesses": [{"text": "Weak in E2.", "evidence": ["E2"], "reasoning": "x"}],
           "threats": [_ext("MRF gains.", "Apollo Tyres Ltd", ["E2"])]}
    errs = swot.check(bad, EVIDENCE)
    assert any("must cite team notes" in e for e in errs)
    assert any("names Apollo Tyres Ltd, but none of the signals" in e for e in errs)
    assert any("mention ids (E2)" in e for e in errs)
    assert swot.check(GOOD, EVIDENCE) == []
    assert any("no team notes" in e for e in swot.check(GOOD, EVIDENCE[:2]))


def test_swot_agent_revises_until_the_rules_pass():
    sub = Subsidiary(code="CEAT", name="CEAT", sectors=["tyres"], signal_focus="tyres")
    drafter = FakeDrafter({**GOOD, "opportunities": []} | {"threats": []}, GOOD)
    draft, rounds, model = swot.run(sub, EVIDENCE, drafter)
    assert (draft, rounds, model) == (GOOD, 2, "fake:model")
    assert "at least one opportunity or threat" in drafter.calls[1][-1]["content"]
    with pytest.raises(swot.SwotError, match="No signals"):
        swot.run(sub, EVIDENCE[2:], FakeDrafter())


# ---------- API ----------
def test_watchlist_is_admin_only_and_approval_is_audited(seeded):
    admin = login(seeded, "compliance.admin@rpg-demo.local")
    ceat = login(seeded, "strategy.ceat@rpg-demo.local")
    assert seeded.get("/api/v1/watchlist", headers=ceat).status_code == 403
    r = seeded.post("/api/v1/watchlist", headers=admin, json={"name": "JK Tyre & Industries", "sectors": ["tyres"], "nse_symbol": "jktyre"})
    assert r.status_code == 201 and r.json()["status"] == "watching" and r.json()["nse_symbol"] == "JKTYRE"
    assert seeded.post("/api/v1/watchlist", headers=admin, json={"name": "X", "sectors": ["unknown"]}).status_code == 422
    eid = r.json()["id"]
    r = seeded.patch(f"/api/v1/watchlist/{eid}", headers=admin, json={"status": "dismissed"})
    assert r.json()["status"] == "dismissed"
    fictional = next(e for e in seeded.get("/api/v1/watchlist", headers=admin).json() if e["is_fictional"])
    assert seeded.patch(f"/api/v1/watchlist/{fictional['id']}", headers=admin, json={"status": "dismissed"}).status_code == 400

    async def audit_rows():
        async with base.get_db_session() as db:
            return (await db.execute(select(AuditLog.detail).where(AuditLog.resource_type == "entity", AuditLog.resource_id == str(eid)))).scalars().all()
    details = arun(audit_rows())
    assert any("watchlist_add" in d for d in details) and any("status watching->dismissed" in d for d in details)
    sources = seeded.get("/api/v1/watchlist/sources", headers=admin).json()
    assert {c["name"] for c in sources["connectors"]} >= {"NSE", "Fincrux", "GNews", "Adzuna", "EPO patents"}
    assert sources["scheduler"]["enabled"] is False


def test_swot_follows_signal_visibility(seeded):
    admin = login(seeded, "compliance.admin@rpg-demo.local")
    kec = login(seeded, "strategy.kec@rpg-demo.local")
    assert seeded.get("/api/v1/swot/CEAT", headers=kec).status_code == 404, "out of scope reads like it does not exist"
    assert seeded.put("/api/v1/swot/CEAT/team-notes", headers=kec, json={"strengths": ["x"]}).status_code == 403
    r = seeded.put("/api/v1/swot/CEAT/team-notes", headers=admin, json={"strengths": [" Brand ", ""], "weaknesses": []})
    assert r.json() == {"strengths": ["Brand"], "weaknesses": []}
    assert seeded.post("/api/v1/swot/KEC/rebuild", headers=admin).status_code == 409, "closed gate"


def test_ingest_runs_as_a_background_job(seeded):
    admin = login(seeded, "compliance.admin@rpg-demo.local")
    r = seeded.post("/api/v1/ingest/run", headers=admin)
    assert r.status_code == 202 and r.json()["kind"] == "ingest"
    job = r.json()
    for _ in range(100):
        job = seeded.get(f"/api/v1/jobs/{job['id']}", headers=admin).json()
        if job["status"] != "running":
            break
        time.sleep(0.2)
    assert job["status"] == "completed", job
    assert job["result"]["via"] == "inline_fallback"
