"""The radar screens' API (/api/v1/radar), including reviewer scope, compliance gates, and
audit rows. Tests use fake LLM drafters and never access external providers."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from db import base
from db.models import AuditLog, Entity, RawSignal, Subsidiary
from radar import api as radar_api, ask as ask_mod, bridge, evidence, persistence, rules, swot_agent
from radar.llm_azure import AZURE, AzureError
from radar.store import COMPANIES_ORDER, STORE

PASSWORD = "ChangeMe123!"
R = "/api/v1/radar"


class Client:
    """The seeded TestClient, logged in as one reviewer."""

    def __init__(self, c, email):
        self.c = c
        tok = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def __getattr__(self, method):
        return lambda path, **kw: getattr(self.c, method)(R + path, headers=self.h, **kw)


@pytest.fixture
def admin(seeded):
    return Client(seeded, "compliance.admin@rpg-demo.local")


@pytest.fixture
def ceat(seeded):
    return Client(seeded, "strategy.ceat@rpg-demo.local")


@pytest.fixture(autouse=True)
def fresh_state(seeded):
    saved = []
    STORE.agent_saved = {}
    STORE.on_agent_swot = lambda co, payload: saved.append((co, payload))
    STORE.live = {co: [] for co in COMPANIES_ORDER}  # demo evidence only, whatever other tests ingested
    bridge._last_sync = time.monotonic()  # and no re-sync from the database during the test
    STORE.reset()
    STORE.TICK = 0.01  # deep dives finish quickly
    AZURE.down_until, AZURE.last_error = 0.0, None
    yield saved


# ---------- rules ----------
def test_score_matches_weights_and_multiplier():
    s = rules.score_of([["credit_downgrade", "", "", ""], ["delayed_filing", "", "", ""], ["leadership_churn", "", "", ""]])
    assert s["base"] == 75 and s["m"] == 1.6 and s["score"] == 100  # 75 × 1.6 = 120, capped at 100


def test_score_counts_each_type_once():
    s = rules.score_of([["patent_shift", "", "", ""], ["patent_shift", "", "", ""]])
    assert s["types"] == ["patent_shift"] and s["score"] == 15


# ---------- access ----------
def test_radar_needs_a_login_scope_and_open_gate(seeded, admin, ceat):
    assert seeded.get(R + "/home", params={"company": "CEAT"}).status_code == 401
    assert ceat.get("/me").json()["companies"] == ["CEAT"], "CEAT desk: in scope and gate open"
    assert ceat.get("/home", params={"company": "KEC"}).status_code == 404, "out of scope reads as unknown"
    assert ceat.get("/home").status_code == 403, "the group-wide view is admin only"
    kec = Client(seeded, "strategy.kec@rpg-demo.local")
    assert kec.get("/home", params={"company": "KEC"}).status_code == 403, "KEC's gate is closed"
    me = admin.get("/me").json()
    assert me["group_view"] is True and me["companies"] == COMPANIES_ORDER
    assert ceat.post("/swot/CEAT/rebuild").status_code == 403
    assert ceat.post("/signals/refresh").status_code == 403
    assert ceat.post("/demo/reset").status_code == 403


def test_every_radar_request_is_audited(ceat):
    ceat.get("/home", params={"company": "CEAT"})

    async def rows():
        async with base.get_db_session() as db:
            return (await db.execute(select(AuditLog).where(AuditLog.resource_type == "radar")
                                     .order_by(AuditLog.id.desc()).limit(1))).scalars().all()
    last = __import__("asyncio").run(rows())[0]
    assert (last.action, last.detail, last.reviewer_name_snapshot) == ("view_radar", "GET /home?company=CEAT", "Corporate Strategy — CEAT Desk")


def test_lists_only_show_the_reviewers_companies(admin, ceat):
    job = admin.post("/deep-dives", json={"case_ids": ["d_meridian", "t_KEC"], "company": "CEAT"}).json()["id"]
    for _ in range(200):
        if admin.get(f"/deep-dives/{job}").json()["status"] == "completed":
            break
        time.sleep(0.02)
    assert [p["id"] for p in admin.get("/book").json()["pages"]] == ["d_meridian", "t_KEC"]
    assert [p["id"] for p in ceat.get("/book").json()["pages"]] == ["d_meridian"]
    assert ceat.get("/cases/t_KEC/overview").status_code == 404
    assert {t["desk"] for t in ceat.get("/theses").json()} <= {"CEAT"}


# ---------- SWOT home ----------
def test_home_for_a_company_has_swot_positions_and_moves(admin):
    r = admin.get("/home", params={"company": "CEAT"}).json()
    assert [x["id"] for x in r["swot"]["O"]][:2] == ["O1", "O2"]
    assert "Secure Meridian before Rival A does" in [m["title"] for m in r["recommended"]]
    assert any(s["case_id"] == "d_rovan" for s in r["set_aside"])
    assert all(p["used"] for p in r["positions"] if p["impact"] > 50 and p["urgency"] > 50)


def test_group_home_has_tiles_and_no_duplicate_set_asides(admin):
    r = admin.get("/home").json()
    assert len(r["tiles"]) == 6 and r["swot"] is None
    assert not {m["case_id"] for m in r["recommended"]} & {s["case_id"] for s in r["set_aside"]}


def test_unknown_company_is_404(admin):
    assert admin.get("/home", params={"company": "Nope"}).status_code == 404


# ---------- full journey ----------
def test_shortlist_deep_dive_book_decide_follow_up(admin):
    r = admin.post("/deep-dives", json={"case_ids": ["d_meridian", "t_KEC"], "company": "CEAT"})
    assert r.status_code == 202 and r.headers["location"].startswith("/api/v1/radar/deep-dives/")
    job = r.json()["id"]
    for _ in range(200):
        s = admin.get(f"/deep-dives/{job}").json()
        if s["status"] == "completed":
            break
        time.sleep(0.02)
    assert s["status"] == "completed"
    assert [p["id"] for p in admin.get("/book").json()["pages"]] == ["d_meridian", "t_KEC"]
    ov = admin.get("/cases/d_meridian/overview").json()
    assert ov["why"]["title"] == "Secure Meridian before Rival A does"
    assert ov["health"]["verdict"][0] == "Badly funded, business is sound"
    assert admin.post("/cases/d_meridian/decision", json={"action": "approve"}).status_code == 422
    assert admin.post("/cases/d_meridian/decision", json={"action": "approve", "owner": "CFO, CEAT"}).json()["stage"] == "act"
    assert admin.post("/cases/t_KEC/decision", json={"action": "park"}).json()["outcome"] == "Parked for 90 days"
    assert admin.post("/cases/t_KEC/decision", json={"action": "reject"}).status_code == 409
    f = admin.post("/cases/d_meridian/simulate-week", json={}).json()
    assert f["updates"][0]["text"].startswith("Rival A raised its stake")
    assert admin.patch("/cases/d_meridian/plan/0", json={"done": True}).json()["plan"][0]["done"] is True
    assert admin.post("/cases/d_meridian/outcome", json={"outcome": "acted"}).json()["stage"] == "closed"
    actions = [a["action"] for a in admin.get("/activity").json()]
    assert f["used_demo_fallback"] is True and f["new_signal_count"] == 0
    assert f["updates"][0]["source"] == "demo"
    for a in ["escalate", "book_written", "approve", "park", "follow_up_check", "outcome"]:
        assert a in actions


def test_follow_up_returns_new_routed_live_signals_once_and_marks_demo_fallback(admin):
    approved_at = datetime.utcnow()
    observed_at = approved_at + timedelta(seconds=1)
    case = STORE.cases["t_CEAT"]
    case.update(stage="act", approved="04 Oct", approved_at=approved_at.isoformat(timespec="seconds"), updates=[])

    async def add_signals():
        async with base.get_db_session() as db:
            ceat = (await db.execute(select(Subsidiary).where(Subsidiary.code == "CEAT"))).scalar_one()
            ceat.compliance_gate = True
            watched = Entity(name="Follow-up test approved rival", sectors=["tyres"], category="test", is_fictional=False,
                             origin="manual", status="watching")
            unrelated = Entity(name="Follow-up test unrelated rival", sectors=["epc"], category="test", is_fictional=False,
                               origin="manual", status="watching")
            db.add_all([watched, unrelated])
            await db.flush()
            db.add_all([
                RawSignal(entity_id=watched.id, signal_type="credit_downgrade", source_type="filing",
                          headline="Rating downgraded to A", source_excerpt="Exchange filing", source_url="https://example.test/live",
                          provider="NSE", observed_at=observed_at, created_at=observed_at),
                RawSignal(entity_id=watched.id, signal_type="promoter_pledge", source_type="filing",
                          headline="Older pledge announcement", source_excerpt="", source_url="", provider="NSE",
                          observed_at=approved_at - timedelta(hours=1), created_at=approved_at - timedelta(hours=1)),
                RawSignal(entity_id=unrelated.id, signal_type="credit_downgrade", source_type="filing",
                          headline="Unrelated company downgrade", source_excerpt="", source_url="", provider="NSE",
                          observed_at=observed_at, created_at=observed_at),
            ])
            await db.commit()

    asyncio.run(add_signals())

    live_result = admin.post("/cases/t_CEAT/simulate-week", json={}).json()
    assert live_result["new_signal_count"] == 1
    assert live_result["used_demo_fallback"] is False
    assert live_result["updates"][0]["source"] == "live"
    assert live_result["updates"][0]["provider"] == "NSE"
    assert live_result["updates"][0]["url"] == "https://example.test/live"
    assert "Follow-up test approved rival" in live_result["updates"][0]["text"]

    fallback_result = admin.post("/cases/t_CEAT/simulate-week", json={}).json()
    assert fallback_result["new_signal_count"] == 0
    assert fallback_result["used_demo_fallback"] is True
    assert fallback_result["updates"][0]["source"] == "demo"
    assert sum(u.get("source") == "live" for u in fallback_result["updates"]) == 1


def test_cannot_escalate_twice(admin):
    admin.post("/deep-dives", json={"case_ids": ["d_strata"]})
    assert admin.post("/deep-dives", json={"case_ids": ["d_strata"]}).status_code == 409


def test_overview_needs_a_deep_dive(admin):
    assert admin.get("/cases/d_sensa/overview").status_code == 409


# ---------- explore and settings ----------
def test_market_series_are_deterministic_and_indexed(admin):
    a = admin.get("/market", params={"company": "CEAT", "period": "1Y"}).json()
    b = admin.get("/market", params={"company": "CEAT", "period": "1Y"}).json()
    assert a["base_series"] == b["base_series"] and a["base_series"][0] == 100.0 and len(a["base_series"]) == 53
    assert a["live_price"] is False


def test_competitors_roster_comes_from_proposed_and_approved_watchlist(admin, monkeypatch):
    watch = {**STORE.live_meta.get("watch", {}), "CEAT": [
        {"id": 901, "name": "Apollo Tyres Ltd", "sectors": ["tyres"], "status": "watching", "signals": 3,
         "latest_signal": {"date": "05 Oct", "label": "Filing", "text": "A public filing", "source": "NSE",
                           "url": "https://example.test/filing"}, "origin": "manual"},
        {"id": 902, "name": "MRF Ltd", "sectors": ["tyres"], "status": "proposed", "signals": 0,
         "latest_signal": None, "why": "Discovered rival", "sources": [{"title": "Source", "url": "https://example.test"}],
         "origin": "discovered"},
        {"id": 903, "name": "Dismissed Ltd", "sectors": ["tyres"], "status": "dismissed", "signals": 0,
         "latest_signal": None, "origin": "manual"},
    ]}
    monkeypatch.setitem(STORE.live_meta, "watch", watch)

    response = admin.get("/competitors", params={"company": "CEAT"})

    assert response.status_code == 200
    rivals = response.json()["rivals"]
    assert [r["name"] for r in rivals] == ["Apollo Tyres Ltd", "MRF Ltd"]
    assert rivals[0]["approved"] is True and rivals[0]["signals"] == 3
    assert rivals[0]["latest_signal"]["text"] == "A public filing"
    assert rivals[1]["approved"] is False and rivals[1]["signals"] == 0
    assert rivals[1]["latest_signal"] is None
    assert admin.post("/competitors/follow", json={"company": "CEAT", "rival": "MRF Ltd"}).status_code == 404


def test_market_uses_cached_prices_for_approved_watchlist_companies(admin, monkeypatch):
    daily = {f"2026-09-{day:02}": 100 + day for day in range(1, 24)}
    watch = {**STORE.live_meta.get("watch", {}), "CEAT": [{"id": 999, "name": "Apollo Tyres Ltd", "status": "watching"}]}
    monkeypatch.setitem(STORE.live_meta, "watch", watch)

    async def cached_state(db, key):
        assert key == "live"
        return {"prices": {"999": {"daily": daily, "updated_at": "2026-10-04T17:00:00"}}}

    monkeypatch.setattr(radar_api.state_store, "load", cached_state)
    result = admin.get("/market", params={"company": "CEAT", "rival": "Apollo Tyres Ltd", "period": "3Y"}).json()

    assert result["live_price"] is True
    assert result["price_source"] == "Alpha Vantage"
    assert result["period"] == "1M" and result["periods"] == ["1M"]
    assert result["rival_series"][0] == 100.0
    assert result["rival_series"][-1] == round(123 / 101 * 100, 2)
    assert result["rival_return"] == round((123 / 101 - 1) * 100, 1)
    assert any(x["name"] == "Apollo Tyres Ltd" and x["live"] for x in result["rivals"])


def test_ask_explains_scoring_and_falls_back(admin):
    r = admin.post("/ask", json={"company": "CEAT", "question": "How is the score calculated?"}).json()
    assert "rule-based" in r["lead"]
    assert admin.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()["fallback"] is True


def test_ask_falls_back_when_azure_fails(admin, monkeypatch):
    class FailedAzure:
        available = True

        def complete_json(self, *args, **kwargs):
            raise AzureError("Azure unavailable")

    monkeypatch.setattr(ask_mod, "AZURE", FailedAzure())

    result = admin.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()

    assert result["fallback"] is True
    assert result["suggestions"]


def test_ask_falls_back_when_azure_returns_no_valid_citations(admin, monkeypatch):
    class UncitedAzure:
        available = True

        def complete_json(self, *args, **kwargs):
            return {"lead": "An answer", "points": [{"text": "Unsupported claim", "evidence": 999}],
                    "meaning": "unsupported", "confidence": 90}

    monkeypatch.setattr(ask_mod, "AZURE", UncitedAzure())

    result = admin.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()

    assert result["fallback"] is True
    assert result["suggestions"]


def test_watch_rule_hits_and_lifecycle(admin):
    r = admin.post("/triggers", json={"metric": "score", "op": "above", "val": "90"}).json()
    assert {h["name"] for h in r["hits"]} == {"Meridian Treadworks Pvt Ltd", "Strata Substations Pvt Ltd"}
    assert admin.patch(f"/triggers/{r['id']}", json={"on": False}).json()["hits"] == []
    assert admin.delete(f"/triggers/{r['id']}").status_code == 204


def test_thesis_parse_and_save(admin):
    c = admin.post("/theses/parse", json={"text": "Cable joint makers in India, revenue ₹100–500 crore, family owned"}).json()["criteria"]
    assert c["sector"] == ["electrical"] and c["rev"] == [100, 500] and c["own"] == ["family"]
    assert admin.post("/theses", json={"desk": "Raychem RPG", "text": "x", "c": c}).status_code == 201


def _approved_live_target(with_signal=True):
    async def create():
        now = datetime.utcnow()
        async with base.get_db_session() as db:
            entity = Entity(
                name=f"Acquisition test target {time.time_ns()}",
                sectors=["tyres"],
                category="tyre manufacturer",
                is_fictional=False,
                origin="manual",
                status="watching",
                query_name="Acquisition test target",
            )
            db.add(entity)
            await db.flush()
            if with_signal:
                db.add(RawSignal(
                    entity_id=entity.id,
                    signal_type="press_opportunity",
                    source_type="news",
                    headline=f"{entity.name} expanded its export capacity",
                    source_excerpt="The company reported a new export facility.",
                    source_url="https://news.example/target-expansion",
                    provider="GNews",
                    observed_at=now,
                    created_at=now,
                ))
            await db.commit()
            return entity.id, entity.name

    return asyncio.run(create())


def _current_swot():
    return {
        q: [{"text": f"Target {q} evidence", "source": f"GNews: cited {q} evidence (2026-10-06)",
             "source_url": f"https://news.example/{q.lower()}"}]
        for q in ("S", "W", "O", "T")
    }


def _post_swot():
    return {
        q: [{"text": f"Combined {q} scenario", "basis": "assumption", "rationale": "Depends on successful integration."}]
        for q in ("S", "W", "O", "T")
    }


def test_acquisition_thesis_options_are_target_specific_and_scoped(admin, ceat):
    target_id, target_name = _approved_live_target()
    response = ceat.get("/acquisition-theses/options", params={"company": "CEAT"})
    assert response.status_code == 200
    options = response.json()
    assert options["company"] == "CEAT"
    assert options["baseline_source"]["by"] == "mock"
    assert any(target["id"] == str(target_id) and target["name"] == target_name
               and not target["is_demo"] and target["live_signal_count"] == 1 for target in options["targets"])
    assert admin.get("/acquisition-theses/options", params={"company": "Unknown"}).status_code == 404
    assert ceat.get("/acquisition-theses/options", params={"company": "KEC"}).status_code == 404


def test_acquisition_baseline_automatically_starts_swot_analyst_for_allowed_company(admin, ceat, monkeypatch):
    calls = []

    def start(company, reviewer):
        calls.append((company, reviewer))
        return {"id": "swot_automatic", "company": company, "status": "running", "round": 0,
                "max_rounds": 3, "error": None}

    monkeypatch.setattr(radar_api.swot_agent, "start", start)
    response = ceat.post("/acquisition-theses/baseline/CEAT")

    assert response.status_code == 202
    assert response.json()["id"] == "swot_automatic"
    assert len(calls) == 1 and calls[0][0] == "CEAT" and calls[0][1]
    assert ceat.post("/acquisition-theses/baseline/KEC").status_code == 404
    assert admin.post("/acquisition-theses/baseline/Unknown").status_code == 404


def test_acquisition_baseline_includes_agent_evidence_sources(admin):
    STORE.swot_source["CEAT"] = {"by": "agent", "model": "test-model", "evidence": {"live": 1}}
    STORE.swot_detail["CEAT"] = {
        "S": [{"sources": [{"source": "Annual report", "origin_label": "Live source"}]}],
        "W": [], "O": [], "T": [],
    }
    options = admin.get("/acquisition-theses/options", params={"company": "CEAT"}).json()

    assert options["baseline_source"]["model"] == "test-model"
    assert options["baseline_swot"]["S"][0]["source"] == "Annual report · Live source"


def test_acquisition_current_swot_requires_approved_target_and_collected_live_signals(ceat):
    empty_id, _ = _approved_live_target(with_signal=False)
    response = ceat.post("/acquisition-theses/current-swot", json={"company": "CEAT", "target_id": str(empty_id)})
    assert response.status_code == 422
    assert "no collected live-source evidence" in response.json()["detail"]

    response = ceat.post("/acquisition-theses/current-swot", json={"company": "CEAT", "target_id": 999999})
    assert response.status_code == 404


def test_acquisition_target_refresh_fetches_only_the_selected_approved_company(admin, monkeypatch):
    target_id, target_name = _approved_live_target(with_signal=False)
    calls = []

    class ConfiguredConnector:
        name = "TestLiveProvider"
        configured = True

    async def fake_fetch(db, entity, state, errors=None):
        calls.append(entity.id)
        now = datetime.utcnow()
        db.add(RawSignal(
            entity_id=entity.id,
            signal_type="press_opportunity",
            source_type="news",
            headline=f"{entity.name} added export capacity",
            source_excerpt="Live provider report.",
            source_url="https://news.example/export",
            provider="TestLiveProvider",
            observed_at=now,
            created_at=now,
        ))
        await db.flush()
        return 1

    async def fake_recompute(*args):
        return None

    monkeypatch.setattr(radar_api, "live_connectors", lambda state: [ConfiguredConnector()])
    monkeypatch.setattr(radar_api.ingest_svc, "fetch_and_store_raw_signals", fake_fetch)
    monkeypatch.setattr(radar_api.ingest_svc, "recompute_cluster_for_entity", fake_recompute)
    response = admin.post("/acquisition-theses/targets/refresh", json={
        "company": "CEAT", "target_id": target_id,
    })

    assert response.status_code == 202
    job = response.json()
    for _ in range(100):
        job = admin.get(f"/acquisition-theses/target-jobs/{job['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.01)
    assert job["status"] == "completed", job
    assert job["result"]["target_name"] == target_name
    assert job["result"]["new_signals"] == 1
    assert job["result"]["live_signal_count"] == 1
    assert calls == [target_id]


def test_acquisition_current_swot_is_generated_from_cited_live_evidence(admin, monkeypatch):
    target_id, target_name = _approved_live_target()

    class FakeDrafter:
        model = "test-live-model"

        def __init__(self, routes):
            assert routes == []

        def close(self):
            pass

        def draft(self, system, messages, schema, name):
            assert name == "target_current_swot"
            assert "only the supplied live-source evidence" in system
            prompt = json.loads(messages[0]["content"])
            source = prompt["live_evidence"][0]
            return json.dumps({
                "S": [{"text": "Export facility supports wider reach.", "evidence": [source["id"]]}],
                "W": [], "O": [], "T": [],
            })

    from shared import llm_chat
    monkeypatch.setattr(llm_chat, "Drafter", FakeDrafter)
    monkeypatch.setattr(llm_chat, "routes_from_settings", lambda: [])
    response = admin.post("/acquisition-theses/current-swot", json={"company": "CEAT", "target_id": str(target_id)})

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["target_name"] == target_name
    assert result["evidence_count"] == 1
    assert result["generated_by"] == "test-live-model"
    assert result["is_demo_target"] is False
    assert result["current_swot"]["S"][0]["source"].startswith("GNews:")
    assert result["current_swot"]["S"][0]["source_url"] == "https://news.example/target-expansion"
    assert result["current_swot"]["W"] == []


def test_acquisition_thesis_draft_labels_and_confirmed_save(admin, monkeypatch):
    target_id, target_name = _approved_live_target()

    class FakeDrafter:
        model = "test-deployment"

        def __init__(self, routes):
            assert routes == []

        def close(self):
            pass

        def draft(self, system, messages, schema, name):
            assert name == "post_acquisition_swot"
            assert "Do not invent facts" in system
            prompt = json.loads(messages[0]["content"])
            assert prompt["target_current_swot"]["S"][0]["source"] == "GNews: cited S evidence (2026-10-06)"
            assert prompt["acquisition_thesis"] == "Acquire to add manufacturing capacity."
            return json.dumps(_post_swot())

    from shared import llm_chat
    monkeypatch.setattr(llm_chat, "Drafter", FakeDrafter)
    monkeypatch.setattr(llm_chat, "routes_from_settings", lambda: [])
    options = admin.get("/acquisition-theses/options", params={"company": "CEAT"}).json()
    draft = admin.post("/acquisition-theses/draft", json={
        "company": "CEAT", "target_id": str(target_id), "text": "Acquire to add manufacturing capacity.",
        "current_swot": _current_swot(),
    })
    assert draft.status_code == 200
    assert draft.json()["is_demo_target"] is False
    assert draft.json()["post_acquisition_swot"]["S"][0]["basis"] == "assumption"

    saved = admin.post("/acquisition-theses", json={
        "company": "CEAT", "target_id": str(target_id), "text": "Acquire to add manufacturing capacity.",
        "current_swot": _current_swot(), "post_acquisition_swot": _post_swot(),
    })
    assert saved.status_code == 201, saved.text
    assert saved.json()["status"] == "reviewer_confirmed"
    assert saved.json()["target_name"] == target_name
    assert admin.get("/acquisition-theses", params={"company": "CEAT"}).json() == [saved.json()]
    assert persistence.load()["acquisition_theses"] == [saved.json()]


def test_acquisition_thesis_draft_fails_explicitly_when_no_llm_is_configured(admin, monkeypatch):
    target_id, _ = _approved_live_target()
    from shared import llm_chat
    monkeypatch.setattr(llm_chat, "routes_from_settings", lambda: [])
    response = admin.post("/acquisition-theses/draft", json={
        "company": "CEAT", "target_id": str(target_id),
        "text": "Acquire to add manufacturing capacity.", "current_swot": _current_swot(),
    })
    assert response.status_code == 502
    assert "No LLM is configured" in response.json()["detail"]


def test_thesis_parse_uses_azure_criteria_when_available(admin, monkeypatch):
    class FakeAzure:
        available = True
        deployment = "test-deployment"

        def complete_json(self, system, user, schema, name, max_tokens):
            assert name == "thesis_criteria"
            assert max_tokens == 300
            assert user == "Targets in several regions"
            return {"sector": ["electrical", "electrical"], "geo": [], "rev_min_crore": 500,
                    "rev_max_crore": 100, "own": ["family", "family"]}

    monkeypatch.setattr(radar_api, "AZURE", FakeAzure())

    response = admin.post("/theses/parse", json={"text": "Targets in several regions"})

    assert response.status_code == 200
    assert response.json() == {
        "criteria": {"sector": ["electrical"], "geo": ["India"], "rev": [100, 500], "own": ["family"]},
        "labels": {"sector": ["Electrical"]},
        "parsed_by": "test-deployment",
    }


def test_thesis_parse_falls_back_to_rules_when_azure_fails(admin, monkeypatch):
    class FailedAzure:
        available = True

        def complete_json(self, *args, **kwargs):
            raise AzureError("Azure unavailable")

    monkeypatch.setattr(radar_api, "AZURE", FailedAzure())

    response = admin.post(
        "/theses/parse",
        json={"text": "Cable joint makers in India, revenue 100-500 crore, family owned"},
    )

    assert response.status_code == 200
    assert response.json()["criteria"] == {
        "sector": ["electrical"], "geo": ["India"], "rev": [100, 500], "own": ["family"],
    }
    assert response.json()["parsed_by"] == "rules"





# ---------- live data through the bridge ----------
def test_live_signals_of_an_approved_company_replace_the_demo_rival_story(admin):
    STORE.live["CEAT"] = [{"date": "30 Sep", "company": "Apollo Tyres Ltd", "label": "Pledge", "text": "Promoters have pledged 9.82% of their shares",
                           "source": "NSE", "url": "https://nse.example/p", "kind": "filing", "provider": "NSE"}]
    reg = evidence.registry("CEAT")
    live = [x for x in reg if x["origin"] == "live"]
    assert live and live[0]["text"] == "Apollo Tyres Ltd: Promoters have pledged 9.82% of their shares"
    assert not [x for x in reg if x["case_id"] == "t_CEAT" and x["origin"] == "demo"], "the invented rival story is left out"
    assert evidence.rival_name("CEAT") == "Apollo Tyres Ltd"


def test_signals_status_reports_the_repo_connectors_and_watchlist(admin):
    s = admin.get("/signals/status").json()
    assert {x["name"] for x in s["sources"]} >= {"NSE", "Fincrux", "GNews", "EPO patents"}
    assert [c["company"] for c in s["companies"]] == COMPANIES_ORDER
    sch = admin.get("/scheduler").json()
    assert sch["enabled"] is False and sch["signals_at"] == "17:00"


# ---------- SWOT Analyst agent (FakeDrafter, no network) ----------
def mock_draft(co):
    """The current mock SWOT in the agent's output shape, citing the evidence each item links to."""
    s, p = STORE.swot[co], STORE.positions[co]
    reg = evidence.registry(co)
    team = {x["text"]: x["id"] for x in reg if x["origin"] == "team"}
    rival = next(x["id"] for x in reg if x["case_id"] == f"t_{co}")
    case_ev = lambda cid: [x["id"] for x in reg if x["case_id"] == cid][:2] or [rival]
    sw = lambda q: [{"text": x, "evidence": [team[x]], "reasoning": "On the strategy team's list."} for x in s[q]]
    ot = lambda q: [{"text": x[0], "case_id": x[1], "impact": p[q][i][0], "urgency": p[q][i][1], "evidence": case_ev(x[1]),
                     "reasoning": "Follows from the linked signals."} for i, x in enumerate(s[q])]
    return {"strengths": sw("S"), "weaknesses": sw("W"), "opportunities": ot("O"), "threats": ot("T"),
            "moves": [{"type": r[0], "title": r[1], "uses": r[2], "case_id": r[3], "why": r[4]} for r in s["rec"]],
            "set_aside": [{"case_id": c, "why": w} for c, w in s["skip"]]}


class FakeDrafter:
    model = "fake-model"

    def __init__(self, drafts):
        self.drafts, self.calls = list(drafts), []

    def draft(self, system, messages, schema):
        self.calls.append(list(messages))
        text = json.dumps(self.drafts.pop(0))
        return text, {"role": "assistant", "content": text}


def wait(job):
    for _ in range(1500):
        if job["status"] != "running":
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_mock_swot_passes_the_agent_checks():
    for co in COMPANIES_ORDER:
        assert swot_agent.check(mock_draft(co), co) == [], co


def test_agent_revises_a_broken_draft_then_updates_home_and_is_persisted(admin, fresh_state):
    bad = mock_draft("CEAT")
    bad["moves"][0]["uses"] = ["O1"]  # links no strength or weakness
    good = mock_draft("CEAT")
    good["strengths"][0]["text"] = "Agent-checked: strong 2-wheeler brand"
    good["threats"][0]["reasoning"] = "Rival A's hiring and patents point to an EV range."
    fake = FakeDrafter([bad, good])
    job = wait(swot_agent.start("CEAT", "Compliance Admin", drafter=fake))
    assert job["status"] == "completed" and len(fake.calls) == 2, job
    assert "must use at least one strength or weakness" in fake.calls[1][-1]["content"]
    s = admin.get("/home", params={"company": "CEAT"}).json()["swot"]
    assert s["S"][0]["text"] == "Agent-checked: strong 2-wheeler brand"
    assert s["source"]["by"] == "agent" and s["source"]["model"] == "fake-model" and s["source"]["rounds"] == 2
    assert s["T"][0]["reasoning"] == "Rival A's hiring and patents point to an EV range."
    assert s["T"][0]["sources"][0]["origin_label"] == "Demo data"
    assert [co for co, _ in fresh_state] == ["CEAT"], "saved for swot_briefs"
    assert fresh_state[0][1]["swot"]["S"][0] == "Agent-checked: strong 2-wheeler brand"


def test_demo_swot_shows_the_records_each_item_links_to_and_no_reasoning(admin):
    s = admin.get("/home", params={"company": "CEAT"}).json()["swot"]
    assert s["method"]["built_by"] == "demo" and s["S"][0]["reasoning"] is None
    assert s["S"][0]["sources"][0]["origin_label"] == "Team list (demo data)"
    o1 = s["O"][0]
    assert o1["case_id"] == "d_meridian" and {x["source"] for x in o1["sources"]} >= {"Company profile", "Rating agency"}


def test_agent_gives_up_and_keeps_the_old_swot(fresh_state):
    bad = mock_draft("KEC")
    bad["moves"] = []
    before = json.dumps(STORE.swot["KEC"])
    job = wait(swot_agent.start("KEC", "Compliance Admin", drafter=FakeDrafter([bad] * swot_agent.MAX_ROUNDS)))
    assert job["status"] == "failed" and "Recommend 1-4 moves" in job["error"]
    assert json.dumps(STORE.swot["KEC"]) == before and fresh_state == []


def test_rebuild_endpoint_rejects_unknown_company(admin):
    assert admin.post("/swot/Nope/rebuild").status_code == 404
    assert admin.get("/swot-jobs/swot_999").status_code == 404
