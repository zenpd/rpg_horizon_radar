"""The radar screens' API (/api/v1/radar) on real-shaped records: the fixture below adds two watched
tyre companies with public signals, scored by the pipeline's own functions, and one with none. No network: Azure is faked or off, and
the SWOT Analyst gets a FakeDrafter."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

import httpx
from ingestion.connectors.live import common

from agents import acquisition_thesis, competitor_profile, opportunity_analyst, sector_scout, swot_analyst
from agents.llm_azure import AZURE
from db import base
from db.models import AuditLog, Entity, OpportunityFinding, RawSignal, Subsidiary
from radar import bridge, evidence
from radar.store import COMPANIES_ORDER, STORE, Store
from agents import target_discovery
from services import company_research, company_size, market_data, scheduler, swot_settings
from services import state as state_store
from services.ingest import recompute_cluster_for_entity
from tests.helpers import FIRST, SECOND, login

R = "/api/v1/radar"
ALPHA, BETA = "Alpha Tyres Ltd", "Beta Rubber Ltd"


class Client:
    """The seeded TestClient, logged in as one user."""

    def __init__(self, c, email):
        self.c, self.h = c, login(c, email)

    def __getattr__(self, method):
        return lambda path, **kw: getattr(self.c, method)(R + path, headers=self.h, **kw)


def size(cr: float) -> dict:
    return {"at": datetime.now().isoformat(), "market_cap": {"cr": cr, "text": f"Market cap ₹{cr} crore", "url": None}}


def ago(days: int) -> datetime:
    return (datetime.utcnow() - timedelta(days=days)).replace(microsecond=0)


SIGNALS = {
    ALPHA: [("promoter_pledge", "filing", "Alpha Tyres Ltd promoters have pledged 9.82% of their shares", "NSE", 2),
            ("credit_downgrade", "filing", "Alpha Tyres Ltd: CRISIL downgrades long-term rating to A-", "NSE", 6),
            ("deal_activity", "news", "Alpha Tyres Ltd to acquire a stake in an EV tyre start-up", "GNews", 9)],
    BETA: [("hiring_scaleup", "hiring", "Beta Rubber Ltd job postings up from 20 to 41", "Adzuna", 4)],
}


async def _add_signal(db, entity: Entity, signal_type: str, source_type: str, headline: str, provider: str, days: int) -> None:
    db.add(RawSignal(entity_id=entity.id, signal_type=signal_type, source_type=source_type, headline=headline,
                     source_excerpt="" if source_type == "news" else "From the exchange disclosure.",
                     source_url=f"https://source.example/{entity.id}/{signal_type}", provider=provider,
                     observed_at=ago(days), created_at=datetime.utcnow()))


@pytest.fixture(scope="session")
def world(seeded):
    """Two watched tyre companies with signals, scored and synced into the radar, each small enough for CEAT
    (and every RPG company) to buy."""
    async def go():
        async with base.get_db_session() as db:
            subs = (await db.execute(select(Subsidiary))).scalars().all()
            ids = {}
            for name in SIGNALS:
                e = Entity(name=name, sectors=["tyres"], category="Competitor · tyres", origin="manual", status="watching",
                           watched_since=datetime.utcnow() - timedelta(days=30))
                db.add(e)
                await db.flush()
                for s in SIGNALS[name]:
                    await _add_signal(db, e, *s)
                await db.flush()
                await recompute_cluster_for_entity(db, e, subs)
                ids[name] = e.id
            db.add(Entity(name="Gamma Tyres Ltd", sectors=["tyres"], category="Competitor · tyres", origin="discovered", status="watching",
                          watched_since=datetime.utcnow(), discovery={"why": "Makes 2-wheeler tyres.", "sources": [{"title": "Tyre makers", "url": "https://example.com/t"}]}))
            for code in company_research.PROFILES:
                await state_store.save(db, company_size.rpg_key(code), {**size(10000), "revenue": {"cr": 8000, "text": "", "url": None}})
            for name, cr in ((ALPHA, 2000), (BETA, 3000)):
                await state_store.save(db, company_size.entity_key(ids[name]), size(cr))
            await db.commit()
        await bridge.sync()
        return ids
    return asyncio.run(go())


@pytest.fixture
def user(seeded, world):
    return Client(seeded, FIRST)


@pytest.fixture
def other(seeded, world):
    return Client(seeded, SECOND)


def case_of(name: str) -> str:
    return next(cid for cid, c in STORE.cases.items() if c["who"] == name)


@pytest.fixture(autouse=True)
def fresh_state(world):
    """Each test starts with every signal open, nothing created, and the radar in sync with the database."""
    asyncio.run(bridge.sync())
    STORE._saved_cases = {}
    for c in STORE.cases.values():
        c.update(Store._new_state())
    STORE.activity, STORE.theses, STORE.triggers, STORE.universe = [], [], [], []
    for co in list(STORE.swot):
        for d in (STORE.swot, STORE.positions, STORE.swot_detail, STORE.swot_source):
            d.pop(co, None)
    AZURE.down_until, AZURE.last_error = 0.0, None
    yield


# ---------- access ----------
def test_radar_needs_a_login_and_every_user_sees_everything(seeded, other):
    assert seeded.get(R + "/home", params={"company": "CEAT"}).status_code == 401
    me = other.get("/me").json()
    assert me == {"name": "Second User", "companies": COMPANIES_ORDER}
    assert other.get("/home").status_code == 200, "the group-wide view"
    for co in COMPANIES_ORDER:
        assert other.get("/home", params={"company": co}).status_code == 200
    r = other.post("/swot/CEAT/rebuild")
    assert r.status_code == 202
    wait(swot_analyst.JOBS[r.json()["id"]])  # let its research step finish before the next test reloads the radar


def test_every_radar_request_is_audited(other):
    other.get("/home", params={"company": "CEAT"})

    async def last():
        async with base.get_db_session() as db:
            return (await db.execute(select(AuditLog).where(AuditLog.resource_type == "radar").order_by(AuditLog.id.desc()).limit(1))).scalar_one()
    row = asyncio.run(last())
    assert (row.action, row.detail, row.reviewer_name_snapshot) == ("view_radar", "GET /home?company=CEAT", "Second User")


# ---------- This week ----------
def test_home_shows_watched_companies_and_their_signals_and_no_invented_swot(user):
    h = user.get("/home", params={"company": "CEAT"}).json()
    assert h["swot"] is None and h["recommended"] == [] and h["positions"] == []
    assert "collects public facts about CEAT" in h["swot_status"]["message"]
    watched = {c["who"]: c for c in h["watched"]}
    assert {ALPHA, BETA} <= set(watched)
    a = watched[ALPHA]
    assert a["score"] == 100 and a["chips"] == ["Pledge", "Rating", "Deal"]
    assert [s["source"] for s in a["quick"]["signals"]] == ["NSE", "NSE", "GNews"]
    assert "promoter pledge" in a["quick"]["score"]["types"]
    feed = [s["text"] for s in h["signals"] if s["who"] in (ALPHA, BETA)]
    assert feed[0].startswith("Promoters have pledged 9.82%"), "newest first, company name trimmed"
    assert "watched compan" in h["analyst"] and "public signals for CEAT" in h["analyst"]


def test_group_home_has_a_tile_per_company(user):
    h = user.get("/home").json()
    tiles = {t["company"]: t for t in h["tiles"]}
    assert list(tiles) == COMPANIES_ORDER and tiles["CEAT"]["watched"] >= 2 and tiles["Zensar"]["watched"] == 0
    assert all(t["swot"] is None for t in tiles.values())


def test_unknown_company_is_404(user):
    assert user.get("/home", params={"company": "Nope"}).status_code == 404


def test_swot_build_researches_first_and_says_why_it_cannot_run_without_research(user):
    r = user.post("/swot/CEAT/rebuild")
    assert r.status_code == 202
    job = r.json()
    for _ in range(300):
        job = user.get(f"/swot-jobs/{job['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "failed" and "No public research on CEAT" in job["error"], job
    assert STORE.research["CEAT"]["at"], "the research step ran (no keys in tests, so it found nothing)"
    assert user.post("/swot/Nope/rebuild").status_code == 404
    assert user.get("/swot-jobs/swot_999").status_code == 404


# ---------- M&A signals: view, shortlist, dismiss ----------
def test_signal_cards_carry_definite_fields_and_move_between_tabs(user, world):
    cid = case_of(ALPHA)
    d = user.get("/signals", params={"company": "CEAT"}).json()
    card = next(c for c in d["signals"] if c["id"] == cid)
    assert (card["who"], card["status"], card["score"], card["signal_count"], card["thesis"]) == (ALPHA, "open", 100, 3, None)
    assert card["chips"] == ["Pledge", "Rating", "Deal"] and card["listing"] is None
    assert d["counts"]["open"] >= 2 and d["counts"]["shortlisted"] == 0

    assert user.post(f"/cases/{cid}/status", json={"status": "shortlisted"}).json()["status"] == "shortlisted"
    assert [c["id"] for c in user.get("/signals", params={"company": "CEAT", "status": "shortlisted"}).json()["signals"]] == [cid]
    assert cid not in [c["id"] for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"]]
    assert user.post(f"/cases/{cid}/status", json={"status": "dismissed"}).json()["status_label"] == "Archived"
    assert [c["id"] for c in user.get("/signals", params={"company": "CEAT", "status": "dismissed"}).json()["signals"]] == [cid]
    assert user.post(f"/cases/{cid}/status", json={"status": "open"}).json()["status"] == "open", "restored from the archive"
    assert user.post(f"/cases/{cid}/status", json={"status": "nope"}).status_code == 422
    actions = [a["action"] for a in user.get("/activity").json()]
    assert {"shortlist", "dismiss", "reopen"} <= set(actions)
    assert user.get("/activity").json()[0]["who"] == "First User", "the real user, not a made-up desk name"
    for gone in ("/book", "/follow-ups"):
        assert user.get(gone).status_code in (404, 405), "the book is gone"


def test_shortlist_and_archive_survive_a_restart_and_old_book_stages_are_upgraded(user, monkeypatch):
    saved = {}
    monkeypatch.setattr("radar.persistence.save", lambda v: saved.update(json.loads(json.dumps(v))))
    a, b = case_of(ALPHA), case_of(BETA)
    user.post(f"/cases/{a}/status", json={"status": "shortlisted"})
    user.post("/triggers", json={"metric": "score", "op": "above", "val": 90})
    saved["cases"][b] = {"stage": "closed", "owner": None, "outcome": "Rejected"}  # saved by the old book
    monkeypatch.setattr("radar.persistence.load", lambda: saved)
    fresh = Store()
    fresh.apply_persisted()
    fresh.set_rivals(STORE.rivals)
    assert fresh.cases[a]["status"] == "shortlisted" and fresh.cases[b]["status"] == "dismissed"
    assert fresh.triggers[0]["val"] == 90
    assert all(v["status"] != "open" for v in saved["cases"].values() if "status" in v), "untouched cases are not stored"


# ---------- the Acquisition Thesis agent (FakeDrafter, no network) ----------
OTHERS = [co for co in COMPANIES_ORDER if co != "CEAT"]


def thesis_draft(ids, ref=None, **over) -> dict:
    d = {"headline": "Adds a tyre maker under financial strain.", "acquisition_type": "partial",
         "background": {"summary": "An Indian tyre maker.", "points": [{"text": "Makes truck tyres.", "evidence": [ids[0]]},
                                                                      {"text": "Promoters hold most shares.", "evidence": [ids[0]]}]},
         "connections": [{"name": "Gamma Tyres Ltd", "relation": "partner", "detail": "Supply pact.", "evidence": [ids[0]]},
                         {"name": "Sunrise Holdings", "relation": "shareholder", "detail": "Holds 12%.", "evidence": [ids[0]]}],
         "acquisition_reason": "Promoters have pledged shares, so a stake is likelier than full control.",
         "target_swot": {k: [{"text": f"A {k[:-1]}.", "evidence": [ids[0]]}] for k in ("strengths", "weaknesses", "opportunities", "threats")},
         "comparison": [{"point": "Its capacity complements the brand.", "effect": "complements", "swot_ref": ref, "evidence": [ids[0]]},
                        {"point": "Both sell replacement tyres.", "effect": "overlaps", "swot_ref": None, "evidence": []}],
         "post_swot": {"strengths": [{"text": "Stronger brand with its truck range.", "change": "strengthened", "swot_ref": ref, "evidence": [ids[0]]}],
                       "weaknesses": [{"text": "Thin margins.", "change": "carried over", "swot_ref": ref, "evidence": [ids[0]]}],
                       "opportunities": [{"text": "Its export network.", "change": "new", "swot_ref": None, "evidence": [ids[0]]}],
                       "threats": [{"text": "Its pledged shares.", "change": "new", "swot_ref": None, "evidence": [ids[0]]}]},
         "fitment": [{"dimension": dim, "rating": "unknown" if dim == "Scale" else "moderate", "reasoning": "From its filings.",
                      "evidence": [] if dim == "Scale" else [ids[0]]} for dim in acquisition_thesis.DIMENSIONS],
         "ripple": [{"company": co, "effect": "neutral", "reasoning": "Different business."} for co in OTHERS],
         "open_questions": ["How large is the pledge?"]}
    d.update(over)
    return d


def test_acquisition_thesis_is_written_checked_and_stored(user):
    cid = case_of(ALPHA)
    STORE.swot["CEAT"] = {"S": ["Strong brand"], "W": ["Thin margins"], "O": [["EV demand", None]], "T": [["Rubber prices", None]], "rec": [], "skip": []}
    ev = acquisition_thesis.evidence(STORE.cases[cid], [])
    ids = [x["id"] for x in ev]
    assert len(ids) == 3, "with no research keys in tests, the evidence is its three signals"
    bad = thesis_draft(ids, "S9", ripple=[{"company": "KEC", "effect": "neutral", "reasoning": "x"}])
    bad["comparison"] = bad["comparison"][:1]  # a real gap: only the model can add comparison points
    fake = FakeDrafter([bad, thesis_draft(ids, "S9", ripple=[{"company": "KEC", "effect": "neutral", "reasoning": "x"}])])
    assert user.get(f"/cases/{cid}/thesis", params={"company": "CEAT"}).json()["thesis"] is None

    async def go():
        async with base.get_db_session() as db:
            return await acquisition_thesis.build(db, cid, "CEAT", fake)
    t = asyncio.run(go())
    retry = fake.calls[1][-1]["content"]
    assert "Give 2-6 comparison points" in retry and "S9" not in retry, "small slips are fixed in code, not sent back"
    sent = fake.calls[0][0]["content"]
    assert "Strong brand" in sent and "Harrisons" in sent, "the RPG company's SWOT and the other companies are given"
    got = user.get(f"/cases/{cid}/thesis", params={"company": "CEAT"}).json()
    assert got["thesis"]["draft"]["acquisition_type"] == "partial" and got["thesis"]["rounds"] == 2
    draft = got["thesis"]["draft"]
    assert draft["comparison"][0]["swot_ref"] is None, "a SWOT reference that does not exist is dropped"
    assert draft["post_swot"]["strengths"][0]["change"] == "new", "a change to an item that does not exist becomes a new item"
    assert draft["post_swot"]["weaknesses"][0]["change"] == "new"
    assert [x["company"] for x in draft["ripple"]] == OTHERS and draft["ripple"][1]["reasoning"] == acquisition_thesis.NOT_ASSESSED
    links = {x["name"]: x["link"] for x in got["thesis"]["draft"]["connections"]}
    assert links == {"Gamma Tyres Ltd": "watched company", "Sunrise Holdings": None}, "links to watched or RPG companies are flagged"
    card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == cid)
    assert card["thesis"]["acquisition_type"] == "partial"
    assert user.get(f"/cases/{cid}/thesis", params={"company": "KEC"}).status_code == 404, "not watched for KEC"

    async def clean():
        async with base.get_db_session() as db:
            await state_store.save(db, acquisition_thesis.key(cid, "CEAT"), {})
            await db.commit()
    asyncio.run(clean())


def test_thesis_rules_reject_unknown_ratings_with_evidence_missing_and_ids_in_text():
    ids = ["E1", "E2"]
    d = thesis_draft(ids)
    d["fitment"][0]["evidence"] = []
    d["headline"] = "See E1 for details."
    d["connections"][0]["evidence"] = []
    d["background"]["points"] = d["background"]["points"][:1]
    d["post_swot"]["threats"] = []
    errs = acquisition_thesis.check(d, set(ids), set(), OTHERS)
    assert any("1-4 post-acquisition threats" in e for e in errs)
    assert any("cites no evidence" in e for e in errs) and any("mention ids" in e for e in errs)
    assert any("must cite the evidence that names the link" in e for e in errs) and any("2-6 background points" in e for e in errs)
    assert acquisition_thesis.check(thesis_draft(ids), set(ids), set(), OTHERS) == []


# ---------- explore ----------
def test_competitors_are_the_watchlist(user):
    rivals = {r["name"]: r for r in user.get("/competitors", params={"company": "CEAT"}).json()["rivals"]}
    assert rivals[ALPHA]["status"] == "watching" and rivals[ALPHA]["signals"] == 3 and rivals[ALPHA]["case_id"]
    assert rivals["Gamma Tyres Ltd"]["status"] == "watching" and rivals["Gamma Tyres Ltd"]["why"] == "Makes 2-wheeler tyres."
    assert rivals["Gamma Tyres Ltd"]["signals"] == 0
    assert rivals["Gamma Tyres Ltd"]["case_id"] is None


def test_rival_deals_come_from_deal_signals(user):
    deals = user.get("/deals", params={"company": "CEAT"}).json()["deals"]
    mine = [d for d in deals if d["company"] == ALPHA]
    assert [d["type"] for d in mine] == ["deal activity"] and mine[0]["source"] == "GNews"


# ---------- Ask Radar ----------
def test_ask_answers_from_live_signals_and_the_scoring_rules(user):
    assert f"What has {ALPHA} been doing?" in user.get("/ask", params={"company": "CEAT"}).json()["suggestions"]
    r = user.post("/ask", json={"company": "CEAT", "question": f"What has {ALPHA} been doing?"}).json()
    assert "public sources on Alpha Tyres Ltd" in r["lead"] and r["sources"] == ["NSE", "GNews"]
    assert r["points"][0][0].endswith("Promoters have pledged 9.82% of their shares. From the exchange disclosure.")
    r = user.post("/ask", json={"company": "CEAT", "question": "How is the score calculated?"}).json()
    assert "rule-based" in r["lead"] and "worth 30" in r["points"][0][0]
    r = user.post("/ask", json={"company": "CEAT", "question": "What risks is the radar watching?"}).json()
    assert all(p[0].split(" · ")[0] in (ALPHA, BETA, "Apollo Tyres Ltd") for p in r["points"])
    r = user.post("/ask", json={"company": "CEAT", "question": "Anything about an EV tyre start-up?"}).json()
    assert "EV tyre start-up" in r["points"][0][0]
    assert user.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()["fallback"] is True


# ---------- Azure OpenAI small model (fake transport, no network) ----------
def fake_azure(settings, monkeypatch, reply=None, status=200):
    import httpx

    calls = []

    def handler(req):
        calls.append(json.loads(req.content))
        assert req.headers["api-key"] == "test-key" and "/deployments/mini/" in str(req.url)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "Public access is disabled."}})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}]})

    settings.azure_openai_endpoint, settings.azure_openai_api_key = "https://x.example.com/", "test-key"
    settings.azure_openai_deployment = "mini"
    monkeypatch.setattr(AZURE, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(AZURE, "_http", None)
    return calls


def test_ask_uses_azure_only_when_rules_cannot_answer_and_drops_uncited_points(user, settings, monkeypatch):
    from radar import ask

    calls = fake_azure(settings, monkeypatch, {"lead": "On the pledge:", "meaning": "watch the lenders.", "confidence": 95,
                                               "points": [{"text": "Promoters pledged shares.", "evidence": 1}, {"text": "Made up.", "evidence": 999}]})
    assert "rule-based" in user.post("/ask", json={"company": "CEAT", "question": "How is the score calculated?"}).json()["lead"] and not calls
    r = user.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()
    assert r["generated_by"] == "mini" and r["points"] == [["Promoters pledged shares.", 1]]
    assert r["sources"] == [ask.evidence_for("CEAT")[0][1]] and r["confidence"] == 70, "generated answers never outrank rule answers"
    assert "Alpha Tyres Ltd: Promoters have pledged" in calls[0]["messages"][1]["content"]


def test_ask_falls_back_when_azure_is_down_or_cites_nothing(user, settings, monkeypatch):
    fake_azure(settings, monkeypatch, {"lead": "x", "meaning": "y", "confidence": 50, "points": [{"text": "Made up.", "evidence": 0}]})
    assert user.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()["fallback"] is True
    AZURE.down_until = 0.0
    fake_azure(settings, monkeypatch, status=403)
    assert user.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()["fallback"] is True


def test_thesis_parse_uses_azure_with_the_real_sector_list(user, settings, monkeypatch):
    calls = fake_azure(settings, monkeypatch, {"sector": ["tyres", "tyres"], "geo": [], "rev_min_crore": 900, "rev_max_crore": 50, "own": ["founder"]})
    r = user.post("/theses/parse", json={"text": "Founder-led tyre makers, revenue 50 to 900 crore"}).json()
    assert r["parsed_by"] == "mini" and r["criteria"] == {"sector": ["tyres"], "geo": ["India"], "rev": [50, 900], "own": ["founder"]}
    assert "electrical-components" in calls[0]["response_format"]["json_schema"]["schema"]["properties"]["sector"]["items"]["enum"]


def test_thesis_parse_falls_back_to_rules_and_backs_off(user, settings, monkeypatch):
    calls = fake_azure(settings, monkeypatch, status=403)
    for _ in range(2):
        r = user.post("/theses/parse", json={"text": "Cable joint makers in India, revenue ₹100–500 crore, family owned"}).json()
        assert r["parsed_by"] == "rules" and r["criteria"]["sector"] == ["electrical-components"]
    assert len(calls) == 1, "after a failure Azure is skipped for the cooldown"


# ---------- settings ----------
def test_thesis_rules_parse_and_save(user):
    r = user.post("/theses/parse", json={"text": "Cable joint makers in India, revenue ₹100–500 crore, family owned"}).json()
    assert r["criteria"] == {"sector": ["electrical-components"], "geo": ["India"], "rev": [100, 500], "own": ["family"]}
    assert r["text"] == ["Sector: Electrical components", "Geography: India", "Revenue ₹100–500 cr", "Ownership: family"]
    assert user.post("/theses", json={"desk": "Raychem RPG", "text": "x y z", "c": {"sector": []}}).status_code == 422
    th = user.post("/theses", json={"desk": "Raychem RPG", "text": "Cable joint makers", "c": r["criteria"]}).json()
    assert th["matches"] == [] and [t["id"] for t in user.get("/theses").json()] == [th["id"]]


def test_watch_rules_match_watched_companies_by_score(user, other):
    r = user.post("/triggers", json={"desk": "CEAT", "metric": "score", "op": "above", "val": 90}).json()
    assert ALPHA in {h["name"] for h in r["hits"]} and BETA not in {h["name"] for h in r["hits"]}
    assert user.post("/triggers", json={"metric": "pledge", "op": "above", "val": 10}).status_code == 422
    assert other.get("/triggers").json()[0]["id"] == r["id"]
    assert user.patch(f"/triggers/{r['id']}", json={"on": False}).json()["hits"] == []
    assert user.delete(f"/triggers/{r['id']}").status_code == 204


def test_universe_records_who_added_a_company(user):
    r = user.post("/universe", json={"company": "Delta Treads", "desk": "CEAT"}).json()
    assert r["added"].startswith("Added by First User")
    assert user.get("/universe").json()[0]["company"] == "Delta Treads"


def test_signals_status_reports_connectors_and_the_watchlist(user):
    s = user.get("/signals/status").json()
    assert {x["name"] for x in s["sources"]} >= {"NSE", "Fincrux", "GNews", "EPO patents"}
    ceat = next(c for c in s["companies"] if c["company"] == "CEAT")
    assert "gate_open" not in ceat and {ALPHA, "Gamma Tyres Ltd"} <= {c["name"] for c in ceat["companies"]}
    assert user.get("/scheduler").json()["enabled"] is False


# ---------- SWOT Analyst agent (FakeDrafter, no network) ----------
def draft_for(co: str, reg: list[dict]) -> dict:
    """A draft that passes the checks: S/W cite evidence about the company, O/T cite watched-company signals."""
    own = [x["id"] for x in reg if x["origin"] == "self"]
    live = [x for x in reg if x["origin"] == "live"]
    item = lambda t, e: {"text": t, "factor": "Market position and brand", "evidence": e, "reasoning": "Follows from the cited evidence."}
    ext = lambda t, x, i, u: {"text": t, "factor": "Competition", "case_id": x["case_id"], "impact": i, "urgency": u, "evidence": [x["id"]], "reasoning": "Follows from the cited signal."}
    return {"strengths": [item("Strong replacement-market brand", own[:1]), item("Wide dealer network", own[1:2])],
            "weaknesses": [item("Thin presence in truck radials", own[:1]), item("Rising raw-material costs", own[1:2])],
            "opportunities": [ext("A watched rival is under financial strain", live[0], 70, 60)],
            "threats": [ext("A watched rival is hiring fast", next(x for x in live if x["case_id"] != live[0]["case_id"]), 40, 30)],
            "moves": [{"type": "SO", "title": "Win dealers from a strained rival", "uses": ["S1", "O1"], "case_id": live[0]["case_id"],
                       "why": "Its pledge and rating cut point to pressure on its dealers."}],
            "set_aside": []}


class FakeDrafter:
    model = "fake-model"

    def __init__(self, drafts):
        self.drafts, self.calls = list(drafts), []

    def draft(self, system, messages, schema, name="draft"):
        self.calls.append(list(messages))
        return json.dumps(self.drafts.pop(0))


def wait(job):
    for _ in range(1500):
        if job["status"] != "running":
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


@pytest.fixture
def with_company_research():
    """CEAT's stored research (services/company_research.py): two public facts about CEAT itself."""
    facts = [{"kind": "results", "text": t, "source": "Fincrux quarterly results", "url": None, "observed_at": "2026-10-01T00:00:00"}
             for t in ("CEAT Q1 quarter: sales ₹3,500 cr (+12% year on year), net profit ₹150 cr (+20% year on year).",
                       "CEAT shareholding: promoters 47.2% (47.2% a quarter earlier).")]

    async def put(value):
        async with base.get_db_session() as db:
            await state_store.save(db, company_research.key("CEAT"), value)
            await db.commit()
        await bridge.sync()
    asyncio.run(put({"at": datetime.now().isoformat(timespec="seconds"), "facts": facts, "errors": []}))
    yield
    asyncio.run(put({}))


def test_agent_revises_a_broken_draft_then_its_swot_shows(user, with_company_research, monkeypatch):
    saved = []
    monkeypatch.setattr(STORE, "on_agent_swot", lambda co, payload: saved.append(co))
    reg = evidence.registry("CEAT")
    bad = draft_for("CEAT", reg)
    bad["moves"][0]["uses"] = ["O1"]  # links no strength or weakness
    fake = FakeDrafter([bad, draft_for("CEAT", reg)])
    assert swot_analyst.missing_evidence("CEAT") is None
    job = wait(swot_analyst.start("CEAT", "Compliance Admin", drafter=fake))
    assert job["status"] == "completed" and len(fake.calls) == 2, job
    assert '"origin": "self"' in fake.calls[0][0]["content"], "the agent is told which evidence is about CEAT itself"
    assert "must use at least one strength or weakness" in fake.calls[1][-1]["content"]
    h = user.get("/home", params={"company": "CEAT"}).json()
    assert h["swot"]["S"][0]["text"] == "Strong replacement-market brand" and h["swot"]["S"][0]["sources"][0]["origin_label"] == "About the company"
    move_case = draft_for("CEAT", reg)["moves"][0]["case_id"]
    assert h["recommended"][0]["case"]["who"] == STORE.cases[move_case]["who"] and saved == ["CEAT"]
    assert "public facts about CEAT" in h["swot"]["method"]["summary"]


def test_strengths_must_cite_research_on_the_company_itself(with_company_research):
    reg = evidence.registry("CEAT")
    draft = draft_for("CEAT", reg)
    live = next(x["id"] for x in reg if x["origin"] == "live")
    draft["strengths"][0]["evidence"] = [live]
    assert any("must cite evidence about the company" in e for e in swot_analyst.check(draft, "CEAT"))


def test_a_company_that_watches_no_one_gets_a_swot_without_moves():
    reg = [{"id": "E1", "origin": "self"}, {"id": "E2", "origin": "self"}]
    item = lambda: {"text": "From research.", "factor": "Financial performance", "evidence": ["E1"], "reasoning": "Follows from it."}
    ext = lambda: {"text": "Market trend.", "factor": "Competition", "case_id": None, "impact": 70, "urgency": 70, "evidence": ["E2"], "reasoning": "Follows from it."}
    draft = {"strengths": [item(), item()], "weaknesses": [item(), item()], "opportunities": [ext()], "threats": [ext()],
             "moves": [], "set_aside": []}
    assert swot_analyst.candidate_cases("Raychem RPG") == []
    assert swot_analyst.check(draft, "Raychem RPG", {"E1", "E2"}) == []
    draft["moves"] = [{"type": "SO", "title": "x", "uses": ["S1", "O1"], "case_id": "r1", "why": "y"}]
    assert any("watches no company" in e for e in swot_analyst.check(draft, "Raychem RPG", {"E1", "E2"}))


def test_agent_gives_up_and_keeps_the_old_swot(with_company_research):
    bad = draft_for("CEAT", evidence.registry("CEAT"))
    bad["moves"] = []
    job = wait(swot_analyst.start("CEAT", "Compliance Admin", drafter=FakeDrafter([bad] * swot_analyst.MAX_ROUNDS)))
    assert job["status"] == "failed" and "moves (one per watched company" in job["error"]
    assert "CEAT" not in STORE.swot



# ---------- SWOT parameters ----------
def test_swot_parameters_default_to_everything_and_change_what_the_agent_reads(user, with_company_research):
    p = user.get("/swot-settings").json()
    assert [x["key"] for x in p["factors"]] == list(swot_settings.FACTORS)
    ceat = next(c for c in p["companies"] if c["company"] == "CEAT")
    assert ceat["sources"] == list(swot_settings.SOURCES) and "natural rubber" in ceat["sector_queries"]
    assert user.put("/swot-settings/CEAT", json={"sources": ["watched"], "factors": ["financial"]}).status_code == 422, "needs a source on CEAT itself"
    assert user.put("/swot-settings/CEAT", json={"sources": ["results"], "factors": []}).status_code == 422
    assert user.put("/swot-settings/CEAT", json={"sources": ["results", "nope"], "factors": ["financial"]}).status_code == 422
    draft = draft_for("CEAT", evidence.registry("CEAT"))  # tags items "Market position and brand" and "Competition"
    try:
        r = user.put("/swot-settings/CEAT", json={"sources": ["results", "shareholding"], "factors": ["financial", "supply"],
                                                   "sector_queries": ["  tyre exports ", "tyre exports", ""]})
        assert r.status_code == 200 and r.json()["sector_queries"] == ["tyre exports"]
        origins = {x["origin"] for x in evidence.registry("CEAT")}
        assert origins == {"self"}, "watched-company signals are off, so the agent no longer reads them"
        assert swot_analyst.factors("CEAT") == ["Financial performance", "Raw materials and supply chain"]
        assert any("needs a factor from: Financial performance" in e for e in swot_analyst.check(draft, "CEAT", {x["id"] for x in evidence.registry("CEAT")}))
    finally:
        user.put("/swot-settings/CEAT", json=swot_settings.defaults("CEAT"))


# ---------- the daily Opportunity Analyst ----------
def gnews_transport(calls: list[str]):
    when = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stories = {'"CEAT"': ("CEAT launches a new EV tyre range", "https://news.example/ev"),
               "natural rubber": ("Natural rubber prices fall 8% this month", "https://news.example/rubber")}

    def handler(req: httpx.Request) -> httpx.Response:
        q = req.url.params["q"]
        calls.append(q)
        hit = stories.get(q)
        return httpx.Response(200, json={"articles": [{"title": hit[0], "description": "", "publishedAt": when, "url": hit[1],
                                                       "source": {"name": "Mint"}}] if hit else []})
    return httpx.MockTransport(handler)


def finding(title: str, ref, evidence=("N1",)) -> dict:
    return {"kind": "opportunity", "title": title, "summary": "Input costs ease.", "swot_ref": ref, "effect": "Eases the margin weakness.",
            "impact": 70, "urgency": 60, "action": "Review rubber buying for the next quarter.", "evidence": list(evidence)}


def test_opportunity_analyst_judges_the_news_against_the_swot_and_users_keep_findings(user, settings):
    settings.gnews_api_key = "gn"
    STORE.swot["CEAT"] = {"S": ["Strong replacement-market brand"], "W": ["Thin operating margins"], "O": [["EV demand", None]],
                          "T": [["Rubber price swings", None]], "rec": [], "skip": []}
    calls: list[str] = []
    bad = {"findings": [finding("Rubber prices fall", "W9")]}
    good = {"findings": [finding("Rubber prices fall", "W1"), {**finding("A new EV tyre line", None), "kind": "threat"}]}
    fake = FakeDrafter([bad, good])

    async def go(drafter):
        async with base.get_db_session() as db:
            return await opportunity_analyst.analyse(db, "CEAT", drafter, gnews_transport(calls))
    try:
        res = asyncio.run(go(fake))
        assert res["findings"] == 2 and res["news"] >= 2, res
        assert '"CEAT"' in calls and "natural rubber" in calls, "the company and its sector searches are read"
        sent = fake.calls[0][0]["content"]
        assert "Thin operating margins" in sent and "Natural rubber prices fall 8%" in sent
        assert "swot_ref W9 is not an item of the current SWOT" in fake.calls[1][-1]["content"]

        d = user.get("/opportunities", params={"company": "CEAT"}).json()
        f = next(x for x in d["findings"] if x["title"] == "Rubber prices fall")
        assert f["swot_ref"] == "W1" and f["swot_text"] == "Thin operating margins" and f["sources"][0]["url"] == "https://news.example/ev"
        assert user.get("/opportunities").json()["counts"]["CEAT"] == 2

        kept = user.patch(f"/opportunities/{f['id']}", json={"status": "kept"}).json()
        assert kept["status"] == "kept"
        assert any(x["origin"] == "daily" and "Rubber prices fall" in x["text"] for x in evidence.registry("CEAT")), \
            "a kept finding is evidence for the next weekly SWOT"
        other = next(x for x in d["findings"] if x["title"] != "Rubber prices fall")
        user.patch(f"/opportunities/{other['id']}", json={"status": "dismissed"})
        assert [x["title"] for x in user.get("/opportunities", params={"company": "CEAT"}).json()["findings"]] == ["Rubber prices fall"]

        again = FakeDrafter([{"findings": []}])
        asyncio.run(go(again))
        assert "EV tyre range" not in again.calls[0][0]["content"], "news already used is not read again"
        assert "Rubber prices fall" in again.calls[0][0]["content"], "earlier findings are listed so they are not repeated"
    finally:
        async def clean():
            async with base.get_db_session() as db:
                await db.execute(delete(OpportunityFinding))
                await db.commit()
        asyncio.run(clean())
        asyncio.run(bridge.sync())


def test_opportunity_analyst_rejects_a_repeat_of_an_earlier_finding():
    errs = opportunity_analyst.check({"findings": [finding("Natural rubber prices fall again", None)]}, {"N1"}, set(),
                                     ["opportunity: Natural rubber prices fall"])
    assert any("already reported" in e for e in errs)
    assert opportunity_analyst.check({"findings": [finding("Steel prices rise", None)]}, {"N1"}, set(), ["opportunity: Natural rubber prices fall"]) == []


def test_everything_that_searches_runs_after_the_daily_news_run_and_never_on_a_restart(settings):
    settings.ingest_daily_at, settings.swot_every_days, settings.discovery_every_days = "17:00", 7, 7
    week = {"discovery": "2026-10-05T17:20:00", "swot": "2026-10-05T17:40:00"}
    done_today = {**week, "ingest": "2026-10-08T17:05:00"}
    assert scheduler.due(datetime(2026, 10, 8, 9, 0), {**week, "ingest": "2026-10-07T17:05:00"}) == [],         "a restart in the morning searches nothing: the daily run is at 17:00"
    assert scheduler.due(datetime(2026, 10, 8, 17, 1), {**week, "ingest": "2026-10-07T17:05:00"}) == ["ingest", "opportunities", "scout", "theses"]
    assert scheduler.due(datetime(2026, 10, 8, 19, 0), done_today) == [], "a restart after today's run repeats nothing"
    assert scheduler.due(datetime(2026, 10, 12, 17, 0), {**week, "ingest": "2026-10-11T17:05:00"}) ==         ["ingest", "opportunities", "scout", "discovery", "swot", "theses"], "the weekly jobs ride on the daily run a week on"
    nxt = scheduler.next_runs(datetime(2026, 10, 8, 19, 0), done_today)
    assert nxt["ingest"] == nxt["scout"] == nxt["theses"] == "2026-10-09T17:00" and nxt["discovery"] == "2026-10-12T17:00"


def test_every_signal_gets_its_thesis_without_anyone_opening_it(user):
    cids = [cid for cid, _ in acquisition_thesis.due_cases()]
    assert {case_of(ALPHA), case_of(BETA)} <= set(cids)
    drafts = []
    for cid, co in acquisition_thesis.due_cases():
        ids = [x["id"] for x in acquisition_thesis.evidence(STORE.cases[cid], [])]
        drafts.append(thesis_draft(ids, ripple=[{"company": c, "effect": "neutral", "reasoning": "Different business."} for c in COMPANIES_ORDER if c != co]))
    res = asyncio.run(acquisition_thesis.write_due("test", FakeDrafter(drafts)))
    assert res["errors"] == [] and {ALPHA, BETA} <= set(res["written"])
    assert asyncio.run(acquisition_thesis.write_due("test", FakeDrafter([])))["written"] == [], "a fresh thesis is not rewritten"
    beta = STORE.cases[case_of(BETA)]
    ids = [x["id"] for x in acquisition_thesis.evidence(beta, [])]
    redo = [thesis_draft(ids, ripple=[{"company": c, "effect": "neutral", "reasoning": "Different business."} for c in OTHERS])]
    beta["signals"] = beta["signals"] + [{**beta["signals"][0], "text": "Promoters sell a 10% stake."}]
    assert asyncio.run(acquisition_thesis.write_due("test", FakeDrafter(redo)))["written"] == [BETA], "new signals make it out of date"
    STORE.swot_source["CEAT"] = {**(STORE.swot_source.get("CEAT") or {}), "at": "rebuilt just now"}
    redo2 = [thesis_draft(ids, ripple=[{"company": c, "effect": "neutral", "reasoning": "Different business."} for c in OTHERS]) for _ in range(2)]
    assert set(asyncio.run(acquisition_thesis.write_due("test", FakeDrafter(redo2)))["written"]) == {ALPHA, BETA}, "so does a rebuilt SWOT"
    card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == case_of(BETA))
    assert card["thesis"] is not None

    async def clean():
        async with base.get_db_session() as db:
            for cid, co in acquisition_thesis.due_cases():
                await state_store.save(db, acquisition_thesis.key(cid, bridge.CO_TO_CODE[co]), {})
            await db.commit()
    asyncio.run(clean())


# ---------- only companies an RPG company could buy are M&A signals ----------
def test_a_competitor_too_big_to_buy_is_not_an_m_and_a_signal(user, world):
    a = case_of(ALPHA)
    assert a in [c["id"] for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"]]
    card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == a)
    assert card["size"]["ok"] is True and card["size"]["label"].startswith("Market cap ₹2,000 cr · 20%")

    async def resize(cr):
        async with base.get_db_session() as db:
            await state_store.save(db, company_size.entity_key(world[ALPHA]), size(cr) if cr else {})
            await db.commit()
        await bridge.sync()
    try:
        asyncio.run(resize(40000))  # four times CEAT's size, like Infosys for Zensar
        assert a not in [c["id"] for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"]]
        assert a not in [cid for cid, _ in acquisition_thesis.due_cases()], "no thesis for a company it cannot buy"
        comp = {r["name"]: r for r in user.get("/competitors", params={"company": "CEAT"}).json()["rivals"]}
        assert comp[ALPHA]["size"]["ok"] is False, "it stays in Competitor Analysis"
        asyncio.run(resize(None))
        assert a not in [c["id"] for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"]], \
            "a competitor of unknown size is not a signal"
        STORE.cases[a]["role"] = "target"
        card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == a)
        assert card["size"]["label"] == "Size not verified", "a target of unknown size is shown, flagged"
    finally:
        asyncio.run(resize(2000))


def test_size_answers_are_read_in_crore_and_compared():
    assert company_size.amount_cr("market capitalization of Zensar Technologies Ltd is reported to be ₹10,328.80 Cr") == 10328.8
    assert company_size.amount_cr("Infosys' market capitalization was Rs. 405,920 crore.") == 405920
    assert company_size.amount_cr("a specific range of ₹1250-1500 crore") == 1250
    assert round(company_size.amount_cr("₹4.06 lakh crore")) == 406000
    assert company_size.amount_cr("no figure here") is None
    assert company_size.amount_cr("Revenue is over ₹1,000 crore; FY25 revenue was ₹5,120 crore.") == 5120, "a bound is not the figure"
    zensar = {"market_cap": {"cr": 9885}, "revenue": {"cr": 5400}}
    assert company_size.fit({"market_cap": {"cr": 405920}}, zensar)["ok"] is False
    assert company_size.fit({"revenue": {"cr": 300}}, zensar)["ok"] is True, "compared on revenue when there is no market cap"
    assert company_size.fit({}, zensar) == {"ok": None, "ratio": None, "metric": None, "label": "Size not verified"}


def test_size_figures_are_kept_only_when_two_searches_agree(settings):
    settings.tavily_api_key = "tv"
    answers = {"Polycab annual revenue in crore": "Revenue of ₹288,838 crore.",
               "Polycab revenue from operations last financial year in crore": "Revenue from operations was ₹22,408 crore.",
               "Polycab market capitalisation in crore": "Market cap ₹1,02,000 crore.",
               "Polycab share price market cap today in rupees crore": "Market cap is ₹1,05,000 Cr.",
               "Tata Projects market capitalisation in crore": "Tata Projects is a private company and has no market cap of ₹17,247 crore.",
               "Tata Projects annual revenue in crore": "Revenue ₹17,500 crore.",
               "Tata Projects revenue from operations last financial year in crore": "₹18,100 crore."}

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": answers.get(json.loads(req.content)["query"], ""), "results": []})
    t = httpx.MockTransport(handler)
    poly = company_size.lookup("Polycab", True, t)
    assert poly["market_cap"]["cr"] == 102000 and poly["market_cap"]["checks"] == 2
    assert poly["revenue"]["cr"] is None and "disagree" in poly["revenue"]["conflict"], "a revenue ten times too high is set aside"
    answers["Polycab total income annual report Rs crore"] = "Total income of ₹22,900 crore."
    assert company_size.lookup("Polycab", True, t)["revenue"]["cr"] == 22408, "a third search breaks the tie"
    tata = company_size.lookup("Tata Projects", True, t)
    assert tata["market_cap"]["cr"] is None and "not listed" in tata["market_cap"]["conflict"]
    assert tata["revenue"]["cr"] == 17500
    assert company_size.fit({"revenue": {"cr": None, "conflict": "x"}}, {"revenue": {"cr": 5000}})["label"] == "Size unclear: the sources disagree"
    assert common.same_company("Continental Tires Co. Ltd", "Continental Tyres")
    assert common.same_company("Plantation Corporation of Kerala Limited (PCKL)", "Plantation Corporation of Kerala Limited")
    assert common.same_company("Techno Electric", "Techno Electric & Engineering Company Ltd") and common.same_company("Goodricke", "Goodricke Group")
    assert not common.same_company("Tata Projects", "Tata Power") and not common.same_company("Infosys", "Infosys BPM")


def tavily_targets(calls: list[str]):
    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        calls.append(body["query"])
        if body.get("include_answer"):  # a size lookup
            answer = "Its revenue is ₹90,000 crore." if "Bigco" in body["query"] else "Annual revenue of ₹420 crore."
            return httpx.Response(200, json={"answer": answer, "results": [{"url": "https://size.example"}]})
        return httpx.Response(200, json={"results": [
            {"title": "Small tyre makers for sale: Delta Treads and Bigco Rubber", "url": "https://example.com/1", "content": "Delta Treads promoters weigh a stake sale."},
            {"title": "Bigco Rubber expands", "url": "https://example.com/2", "content": "Bigco Rubber is a large maker."}]})
    return httpx.MockTransport(handler)


def test_target_discovery_adds_grounded_small_targets_and_sets_aside_big_ones(settings):
    settings.tavily_api_key = "tv"
    calls: list[str] = []
    picks = {"companies": [{"name": "Delta Treads", "why": "A small tyre maker whose promoters weigh a stake sale.", "results": [1]},
                           {"name": "Bigco Rubber", "why": "A tyre maker.", "results": [2]},
                           {"name": "Imaginary Wheels", "why": "Not in the results.", "results": [1]}]}

    class Picks:
        model = "fake-model"

        def __init__(self):
            self.n = 0

        def draft(self, system, messages, schema, name="draft"):
            self.n += 1
            return json.dumps(picks if self.n == 1 else {"companies": []})  # CEAT first, then nothing

    async def go():
        async with base.get_db_session() as db:
            res = await target_discovery.discover(db, drafter=Picks(), transport=tavily_targets(calls))
            delta = (await db.execute(select(Entity).where(Entity.name == "Delta Treads"))).scalar_one()
            big = (await db.execute(select(Entity).where(Entity.name == "Bigco Rubber"))).scalar_one()
            out = (res, (delta.role, delta.status), (big.role, big.status, big.discovery.get("set_aside", "")))
            for e in (delta, big):
                await db.delete(e)
            await db.commit()
            return out
    res, delta, big = asyncio.run(go())
    assert res["added"] == ["Delta Treads"] and res["too_big"] == ["Bigco Rubber"]
    assert delta == ("target", "watching")
    assert big[:2] == ("target", "dismissed") and big[2].startswith("Too large to acquire: Revenue ₹90,000 cr")
    assert any("stake sale" in q for q in calls), "it searches for distress and stake sales, not only competitors"


# ---------- the Competitor Profile agent ----------
def profile_draft(ids, **over) -> dict:
    d = {"summary": "A tyre maker adding truck tyre capacity.",
         "swot": {k: [{"text": f"A {k[:-1]}.", "evidence": [ids[0]]}] for k in ("strengths", "weaknesses", "opportunities", "threats")},
         "versus": [{"point": "Larger truck tyre range.", "side": "ahead", "swot_ref": None, "evidence": [ids[0]]},
                    {"point": "Weaker brand in cars.", "side": "behind", "swot_ref": None, "evidence": [ids[0]]}],
         "threat": {"level": "medium", "reason": "It sells into the same truck tyre market."},
         "watch": ["Its next quarterly results."]}
    d.update(over)
    return d


def test_competitor_overview_groups_moves_and_writes_the_analysis(user, world):
    eid = world[ALPHA]
    got = user.get(f"/competitors/{eid}/overview", params={"company": "CEAT"}).json()
    assert got["profile"] is None and got["rival"]["name"] == ALPHA
    groups = {m["group"]: len(m["signals"]) for m in got["moves"]}
    assert sum(groups.values()) == got["rival"]["signals"] and "News" in groups, "every signal is in one group"
    r = competitor_profile.rival(eid, "CEAT")
    ids = [x["id"] for x in acquisition_thesis.evidence({"signals": r["signals"]}, [])]
    bad = profile_draft(ids, versus=[{"point": "See E1.", "side": "ahead", "swot_ref": "S9", "evidence": []}])
    fake = FakeDrafter([bad, profile_draft(ids)])

    async def go():
        async with base.get_db_session() as db:
            return await competitor_profile.build(db, eid, "CEAT", fake)
    p = asyncio.run(go())
    retry = fake.calls[1][-1]["content"]
    assert "2-6 points" in retry and "must cite" in retry and p["rounds"] == 2
    got = user.get(f"/competitors/{eid}/overview", params={"company": "CEAT"}).json()
    assert got["profile"]["draft"]["threat"]["level"] == "medium"
    assert competitor_profile.stale(got["profile"], r, "CEAT") is None, "up to date until its signals or the SWOT change"
    assert competitor_profile.stale(got["profile"], {**r, "signals": r["signals"][1:]}, "CEAT") == "new public signals"
    assert user.get("/competitors/99999/overview", params={"company": "CEAT"}).status_code == 404

    async def clean():
        async with base.get_db_session() as db:
            await state_store.save(db, competitor_profile.key(eid, "CEAT"), {})
            await db.commit()
    asyncio.run(clean())


# ---------- The financial market (services/market_data.py) ----------
def market_feeds(calls: list[str]):
    quarters = ["Jun 2024", "Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025"]

    def fin(sales, profit, opm):
        return {"success": "true", "data": {"quaterly_results": [["Category", *quarters], ["Sales", *sales], ["Net Profit", *profit], ["OPM %", *opm]],
                                            "shareholding_quarterly": [["Category", "Mar 2025", "Jun 2025"], ["Promoters", "47.2%", "47.2%"], ["FIIs", "18.1%", "17.0%"]]}}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if "fincrux" in req.url.host:
            own = "CEATLTD" in req.url.path
            return httpx.Response(200, json=fin(["3000", "3100", "3200", "3300", "3540"] if own else ["900", "900", "900", "900", "945"],
                                                ["100", "100", "100", "100", "166"] if own else ["50", "50", "50", "50", "40"],
                                                ["11%", "10%", "10%", "9%", "9%"] if own else ["14%", "14%", "13%", "13%", "13%"]))
        own = "CEATLTD" in str(req.url)
        days = {f"2026-{6 + i // 28:02d}-{1 + i % 28:02d}": {"4. close": str((100 + i) if own else (200 - i))} for i in range(60)}
        return httpx.Response(200, json={"Time Series (Daily)": days})
    return httpx.MockTransport(handler)


def test_financial_market_compares_results_and_prices_with_listed_peers(user, settings):
    settings.fincrux_api_key, settings.alpha_vantage_api_key = "fx", "av"
    w = next(x for x in STORE.live_meta["watch"]["CEAT"] if x["name"] == ALPHA)
    w["nse_symbol"] = "ALPHATYRE"
    calls: list[str] = []
    try:
        async def go():
            async with base.get_db_session() as db:
                return await market_data.refresh(db, "CEAT", market_feeds(calls))
        res = asyncio.run(go())
        assert res["prices"][0] == res["results"][0] == "CEATLTD", "the RPG company's own figures first"
        assert "ALPHATYRE" in res["prices"] and "ALPHATYRE" in res["results"]
        assert sum("ALPHATYRE.BSE" in c for c in calls) == 1, "prices on the BSE symbol"
        again = asyncio.run(go())
        assert again["prices"] == [] and again["results"] == [], "fresh figures are not fetched again"
        d = user.get("/market", params={"company": "CEAT"}).json()
        own, alpha = d["own"], next(r for r in d["peers"] if r["name"] == ALPHA)
        assert own["sales_yoy"] == 18.0 and own["profit_yoy"] == 66.0 and own["opm"] == 9 and own["ttm_sales"] == 13140
        assert alpha["sales_yoy"] == 5.0 and alpha["profit_yoy"] == -20.0 and alpha["fiis"] == 17.0
        assert own["chg_30"] > 0 > alpha["chg_30"] and own["prices"][-1][1] == 159
        verdicts = {s["measure"]: s["verdict"] for s in d["standing"]}
        assert verdicts["Sales growth, latest quarter year on year"] == "ahead" and verdicts["Operating margin, latest quarter"] == "behind"
        assert BETA in d["unlisted"]
        assert user.get("/market", params={"company": "Raychem RPG"}).json()["listed"] is False
    finally:
        w["nse_symbol"] = None

        async def clean():
            async with base.get_db_session() as db:
                live = await state_store.load(db, "live")
                live.pop("market", None)
                live.pop("budget", None)
                await state_store.save(db, "live", live)
                await db.commit()
        asyncio.run(clean())


def test_signal_cards_and_theses_show_the_targets_finances(user):
    a = case_of(ALPHA)
    card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == a)
    assert card["finance"] == {"listed": False, "label": "Not listed: no published accounts"}
    w = next(x for x in STORE.live_meta["watch"]["CEAT"] if x["name"] == ALPHA)
    w["nse_symbol"] = "ALPHATYRE"
    stressed = {"at": datetime.now().isoformat(), "quarters": [f"Q{i}" for i in range(8)], "sales": ["100"] * 7 + ["120"],
                "profit": ["10"] * 8, "opm": ["12%"] * 8, "holding_quarters": [], "holding": {},
                "balance": {"periods": ["Mar 2026"], "Equity Capital": ["10"], "Reserves": ["10"], "Borrowings": ["60"], "Total Liabilities": ["200"]},
                "annual": {"periods": ["Mar 2026", "TTM"], "Sales": ["400", "420"], "Operating Profit": ["40", "40"], "Interest": ["30", "30"],
                           "Profit before tax": ["5", "5"], "Net Profit": ["4", "4"]}, "cash": {}, "ratios": {}, "top": {}}

    async def put(entry):
        async with base.get_db_session() as db:
            live = await state_store.load(db, "live")
            if entry is None:
                live.pop("market", None)
            else:
                live.setdefault("market", {}).setdefault("fin", {})["ALPHATYRE"] = entry
            await state_store.save(db, "live", live)
            await db.commit()
    try:
        card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == a)
        assert card["finance"]["pending"] is True and card["finance"]["label"].startswith("Figures pending")
        asyncio.run(put(stressed))
        card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["id"] == a)
        assert card["finance"]["label"] == "debt 3.0x equity" and "debt 3.0 times equity" in card["finance"]["stress"]
        f = user.get(f"/cases/{a}/thesis", params={"company": "CEAT"}).json()["financials"]
        assert f["target"]["sales_yoy"] == 20.0 and f["target"]["health"]["interest_cover"] == 1.2
        assert f["target"]["expected"] == {"quarters": 8, "from": "Q0", "to": "Q7", "sales": 102.5, "profit": 10.0, "opm": 12.0}, \
            "the 8-quarter average is the level to expect after a deal"
        assert f["acquirer"]["listed"] is True and f["acquirer"]["symbol"] == "CEATLTD"
    finally:
        w["nse_symbol"] = None
        asyncio.run(put(None))


def test_zensar_targets_follow_its_profile_and_unsignalled_targets_are_candidates(user, world):
    qs = target_discovery.queries("ZENSAR", "", [])
    assert any("employees" in q for q in qs) and any("US " in q or "UK " in q for q in qs), "headcount and US/UK digital firms"
    assert target_discovery.queries("CEAT", "", [])[0].startswith("small "), "the others keep the generic searches"
    assert user.get("/candidates", params={"company": "CEAT"}).json()["candidates"] == [], "watched targets with signals are M&A signals, not candidates"

    async def add():
        async with base.get_db_session() as db:
            e = Entity(name="Delta Digital Pvt Ltd", sectors=["tyres"], category="Target · tyres", origin="discovered", status="watching",
                       role="target", watched_since=datetime.utcnow(),
                       discovery={"for": "CEAT", "kind": "target", "why": "A small digital firm.", "employees": "about 400",
                                  "clients": "Indian tyre dealers", "headquarters": "Pune, India", "sources": [{"title": "t", "url": "https://x.example"}]})
            db.add(e)
            await db.flush()
            await state_store.save(db, company_size.entity_key(e.id), {})  # an earlier test's company may have had this id
            await db.commit()
            return e.id
    eid = asyncio.run(add())
    asyncio.run(bridge.sync())
    try:
        c = next(x for x in user.get("/candidates", params={"company": "CEAT"}).json()["candidates"] if x["entity_id"] == eid)
        assert (c["employees"], c["clients"], c["headquarters"]) == ("about 400", "Indian tyre dealers", "Pune, India")
        assert c["size"]["label"] == "Size not verified"
        assert user.get(f"/competitors/{eid}/overview", params={"company": "CEAT"}).status_code == 200, "Overview opens for a candidate"
    finally:
        async def drop():
            async with base.get_db_session() as db:
                await db.delete(await db.get(Entity, eid))
                await db.commit()
        asyncio.run(drop())
        asyncio.run(bridge.sync())



def test_sector_scout_turns_industry_news_into_m_and_a_signals(user, settings):
    settings.tavily_api_key, settings.gnews_api_key = "tv", ""
    asked: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        asked.append(body["query"])
        if body.get("include_answer"):  # size lookups
            return httpx.Response(200, json={"answer": "Its annual revenue is ₹300 crore." if "Omega" in body["query"] else "Revenue of ₹90,000 crore.",
                                             "results": []})
        return httpx.Response(200, json={"results": [
            {"title": "Omega Treads raises Rs 50 crore to expand truck tyre plant", "url": "https://news.example/omega", "content": "Omega Treads, a Pune tyre maker...",
             "published_date": "Mon, 05 Oct 2026 08:00:00 GMT"},
            {"title": "Megatyre buys a stake in Omega Treads rival", "url": "https://news.example/mega", "content": "Megatyre is India's largest...",
             "published_date": "Sun, 04 Oct 2026 08:00:00 GMT"}]})
    g = {"scale": "small", "segment": "same", "acquired": False}
    picks = {"companies": [
        {"name": "Omega Treads", "event": "fund_raise", "why": "A small tyre maker raising money to grow.", "size_hint": "Rs 50 crore raise", "items": [1], **g},
        {"name": "Megatyre", "event": "deal", "why": "Large.", "size_hint": None, "items": [2], **g, "scale": "mid"},
        {"name": "Phantom Rubber", "event": "distress", "why": "Not in the news.", "size_hint": None, "items": [1], **g}]}

    async def go():
        async with base.get_db_session() as db:
            res = await sector_scout.scan(db, codes=["CEAT"], drafter=FakeDrafter([picks]), transport=httpx.MockTransport(handler))
        await bridge.sync()
        return res
    res = asyncio.run(go())
    assert res["added"] == ["Omega Treads"] and res["too_big"] == ["Megatyre"] and res["signals"] == 1, res
    assert any("stake sale" in q for q in asked), "it reads the industry's news, not a watchlist"
    card = next(c for c in user.get("/signals", params={"company": "CEAT"}).json()["signals"] if c["who"] == "Omega Treads")
    assert card["found_via"] == "sector news" and card["chips"] == ["Fund raise"] and card["size"]["ok"] is True
    assert card["chip_links"]["Fund raise"]["url"] == "https://news.example/omega"

    async def clean():
        async with base.get_db_session() as db:
            for name in ("Omega Treads", "Megatyre"):
                e = (await db.execute(select(Entity).where(Entity.name == name))).scalar_one()
                for r in (await db.execute(select(RawSignal).where(RawSignal.entity_id == e.id))).scalars().all():
                    await db.delete(r)
                await state_store.save(db, company_size.entity_key(e.id), {})
                await db.delete(e)
            await db.commit()
        await bridge.sync()
    asyncio.run(clean())


def test_fincrux_market_cap_replaces_a_search_answer(user):
    async def put(top):
        async with base.get_db_session() as db:
            live = await state_store.load(db, "live")
            if top is None:
                live.pop("market", None)
            else:
                live.setdefault("market", {}).setdefault("fin", {})["CEATLTD"] = {"at": datetime.now().isoformat(), "top": top}
            await state_store.save(db, "live", live)
            await db.commit()
        await bridge.sync()
    try:
        asyncio.run(put({"Market Cap": "₹13,314Cr."}))
        own = STORE.sizes[company_size.rpg_key("CEAT")]["market_cap"]
        assert own["cr"] == 13314 and own["source"] == "Fincrux"
    finally:
        asyncio.run(put(None))
    assert STORE.sizes[company_size.rpg_key("CEAT")]["market_cap"]["cr"] == 10000, "back to the stored figure"



def test_sector_scout_drops_large_unrelated_and_acquired_picks():
    items = [{"title": f"{n} news", "text": f"{n} news: something happened", "source": "Mint", "observed_at": "2026-10-06T00:00:00", "url": f"https://n.example/{i}"}
             for i, n in enumerate(["Yes Bank", "Gradiant", "Continuus", "Kappa Soft"], 1)]
    g = lambda n, i, **k: {"name": n, "event": "growth", "why": "x", "size_hint": None, "items": [i], "scale": "small", "segment": "same", "acquired": False, **k}
    fake = FakeDrafter([{"companies": [g("Yes Bank", 1, scale="large"), g("Gradiant", 2, segment="unrelated"), g("Continuus", 3, acquired=True), g("Kappa Soft", 4)]}])
    out, _, dropped = sector_scout.pick("ZENSAR", items, None, fake)
    assert [p["name"] for p in out] == ["Kappa Soft"]
    assert dropped == ["Yes Bank (large)", "Gradiant (unrelated)", "Continuus (being acquired)"]


# ---------- Ask Radar conversations (agents/ask_agent.py) ----------
class AskFake:
    """Answers from the evidence it is given: the radar's when that names Alpha, else asks for the web."""
    model = "fake-model"

    def __init__(self):
        self.calls = []

    def draft(self, system, messages, schema, name="draft"):
        payload = json.loads(messages[-1]["content"])
        self.calls.append(payload)
        ev = payload["evidence"] if isinstance(payload["evidence"], list) else []
        web = [x for x in ev if x["id"].startswith("W")]
        mine = [x for x in ev if ALPHA in x["text"]]
        if web:
            return json.dumps({"answer": f"From the web: {web[0]['text']} [{web[0]['id']}]", "needs_web": False, "web_query": None})
        if mine and "Alpha" in payload["question"]:
            return json.dumps({"answer": f"- {mine[0]['text']} [{mine[0]['id']}]", "needs_web": False, "web_query": None})
        return json.dumps({"answer": "The radar has no data on that.", "needs_web": True, "web_query": "Zeta Corp news"})


def test_ask_radar_answers_from_the_radar_then_the_web_and_keeps_chats_private(user, other, monkeypatch):
    from agents import ask_agent

    fake = AskFake()
    monkeypatch.setattr(ask_agent, "Drafter", lambda routes=None: fake)
    monkeypatch.setattr(ask_agent, "web_evidence", lambda q: ([{"id": "W1", "kind": "web", "text": "Zeta Corp opened a plant",
                                                                  "source": "Mint", "date": "2026-10-06", "url": "https://n.example/z"}], []))
    t = user.post("/chats", json={"company": "CEAT"}).json()
    r = user.post(f"/chats/{t['id']}/messages", json={"text": f"What has {ALPHA} been doing?", "company": "CEAT"}).json()
    assert r["answer"]["used_web"] is False and r["answer"]["sources"][0]["kind"] == "radar", "the radar's data first"
    assert ALPHA in r["answer"]["content"] and r["thread"]["title"] == f"What has {ALPHA} been doing?"
    assert any("CEAT SWOT" in x["text"] or "watchlist" in x["source"].lower() for x in fake.calls[0]["evidence"])

    r = user.post(f"/chats/{t['id']}/messages", json={"text": "And what about Zeta Corp?", "company": "CEAT"}).json()
    assert r["answer"]["used_web"] is True and r["answer"]["sources"] == [
        {"id": "W1", "kind": "web", "text": "Zeta Corp opened a plant", "source": "Mint", "date": "2026-10-06", "url": "https://n.example/z"}]
    got = user.get(f"/chats/{t['id']}").json()
    assert [m["role"] for m in got["messages"]] == ["user", "assistant", "user", "assistant"], "the conversation is saved"

    assert t["id"] in [x["id"] for x in user.get("/chats").json()]
    assert t["id"] not in [x["id"] for x in other.get("/chats").json()], "another user does not see it"
    assert other.get(f"/chats/{t['id']}").status_code == 404
    assert other.post(f"/chats/{t['id']}/messages", json={"text": "hi", "company": "CEAT"}).status_code == 404
    assert other.delete(f"/chats/{t['id']}").status_code == 404
    assert user.delete(f"/chats/{t['id']}").status_code == 204 and user.get(f"/chats/{t['id']}").status_code == 404


def test_ask_radar_drops_citations_to_sources_it_was_not_given():
    from agents import ask_agent

    class Bad:
        model = "fake"

        def draft(self, *a, **k):
            return json.dumps({"answer": "Revenue rose 40% [R9].", "needs_web": False, "web_query": None})
    reply, _ = ask_agent.draft("q", [], "CEAT", [{"id": "R1", "kind": "radar", "text": "x", "source": "s"}], Bad())
    assert "[R9]" not in reply["answer"], "after one retry an unknown citation is removed, never shown as a source"
