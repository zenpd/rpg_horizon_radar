"""The radar screens' API (/api/v1/radar), ported from the prototype's tests, plus the access
rule the repo adds: reviewer login, scope + open gate, audit row per request. No network: the
SWOT Analyst gets a FakeDrafter, Azure is unconfigured."""
from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import select

from db import base
from db.models import AuditLog
from radar import bridge, evidence, rules, swot_agent
from radar.llm_azure import AZURE
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
    for a in ["escalate", "book_written", "approve", "park", "weekly_run", "outcome"]:
        assert a in actions


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


def test_ask_explains_scoring_and_falls_back(admin):
    r = admin.post("/ask", json={"company": "CEAT", "question": "How is the score calculated?"}).json()
    assert "rule-based" in r["lead"]
    assert admin.post("/ask", json={"company": "CEAT", "question": "zzz"}).json()["fallback"] is True


def test_watch_rule_hits_and_lifecycle(admin):
    r = admin.post("/triggers", json={"metric": "score", "op": "above", "val": "90"}).json()
    assert {h["name"] for h in r["hits"]} == {"Meridian Treadworks Pvt Ltd", "Strata Substations Pvt Ltd"}
    assert admin.patch(f"/triggers/{r['id']}", json={"on": False}).json()["hits"] == []
    assert admin.delete(f"/triggers/{r['id']}").status_code == 204


def test_thesis_parse_and_save(admin):
    c = admin.post("/theses/parse", json={"text": "Cable joint makers in India, revenue ₹100–500 crore, family owned"}).json()["criteria"]
    assert c["sector"] == ["electrical"] and c["rev"] == [100, 500] and c["own"] == ["family"]
    assert admin.post("/theses", json={"desk": "Raychem RPG", "text": "x", "c": c}).status_code == 201


def test_follow_rival_moves_it_to_deep_watch(admin):
    r = admin.post("/competitors/follow", json={"company": "CEAT", "rival": "Rival B"}).json()
    assert next(x for x in r["rivals"] if x["name"] == "Rival B")["watch"] == "Deep"


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
