"""In-memory demo state. Everything a user changes (escalations, decisions, plans,
theses, watch rules, universe) lives here until the server restarts or /demo/reset is called.
Production swaps this for PostgreSQL tables (case, book_page, action_item, audit_log ...)."""
from __future__ import annotations

import copy
import itertools
import json
import time
from datetime import datetime

from . import persistence, rules
from .reference import DATA_DIR, REF, load

TODAY = "29 Sep"
COMPANIES_ORDER = ["CEAT", "KEC", "Zensar", "RPG Life Sciences", "Raychem RPG", "Harrisons"]

# Per-case fields a user can actually change (escalation, decision, plan, updates, outcome).
# Everything else on a case (kind/co/cos/title/date/target/ws) is rebuilt fresh from the current
# reference data on every boot, so only this subset is worth persisting — snapshotting the whole
# case would also freeze a stale copy of `target`/`ws` into the saved state.
_CASE_MUTABLE_FIELDS = ("stage", "in_book", "owner", "approved", "approved_at", "plan", "updates", "up_next", "outcome", "ov_date")
_MAX_ACTIVITY = 500  # unbounded growth guard; the UI only ever shows the newest 40 anyway


class Store:
    def __init__(self) -> None:
        # Filled from the database by radar/bridge.py: SWOTs the agent built (kept in the
        # swot_briefs table) and live signals of approved watchlist companies.
        self.agent_saved: dict = {}
        # Called after the agent saves a SWOT, to persist it (bridge.persist_swot).
        self.on_agent_swot = None
        # Just the demo defaults for now, unpersisted: radar/bridge.py's startup() rebuilds this
        # again (to reload agent SWOTs, also unpersisted — see load_agent_swots()) and only then
        # calls _apply_persisted() once, as the last step of boot. Doing it here too would just
        # get overwritten by that later reset() and waste a DB round trip for nothing.
        self.reset(persist=False)

    # ---------- setup ----------
    def reset(self, keep_agent_swots: bool = True, persist: bool = True) -> None:
        """Back to the demo data. Live signals and SWOTs the agent built always stay: they are
        records of real data, not demo state (keep_agent_swots=False drops them from memory only).

        persist=True (the default, used by the explicit /demo/reset endpoint and every other
        caller) makes this the new durable state too. The one exception is the very first call
        from __init__: it must NOT persist yet, or it would overwrite a real saved session with
        fresh demo defaults before _apply_persisted() below gets a chance to load it back."""
        self.companies: dict = load("companies")
        swot = load("swot")
        self.swot: dict = swot["swot"]
        self.positions: dict = swot["positions"]
        self.swot_source: dict = {co: {"by": "mock"} for co in COMPANIES_ORDER}  # "agent" once the SWOT Analyst rebuilds it
        self.swot_detail: dict = {}  # per company, each item's reasoning and sources once the agent has built it
        # The strategy team's own strengths and weaknesses, kept as the agent's starting point.
        self.team_sw: dict = {co: {"S": list(self.swot[co]["S"]), "W": list(self.swot[co]["W"])} for co in COMPANIES_ORDER}
        saved = self.agent_saved if keep_agent_swots else {}
        for co, a in saved.items():
            if co in self.swot:
                self.swot[co], self.positions[co], self.swot_detail[co], self.swot_source[co] = a["swot"], a["positions"], a["detail"], a["source"]
        settings = load("settings")
        self.theses: list = settings["theses"]
        self.acquisition_theses: list = []
        self.triggers: list = settings["triggers"]
        self.universe: list = settings["universe"]
        self.deals: list = settings["deals"]
        self.targets: list = load("targets")
        for t in self.targets:
            t.update(rules.score_of(t["signals"]))
        # Live signals of approved watchlist companies, loaded by radar/bridge.py from the repo's
        # raw_signals; kept apart from the mock records and across /demo/reset.
        prev_live = getattr(self, "live", None) or {}
        self.live: dict = {co: prev_live.get(co, []) for co in COMPANIES_ORDER}
        self.live_meta: dict = getattr(self, "live_meta", None) or {}
        self.followed: set[str] = set()
        self.book_order: list[str] = []
        self.jobs: dict[str, dict] = {}
        self._job_ids = itertools.count(1)
        self.activity: list[list] = [
            ["28 Sep 16:40", "strategy.harrisons", "universe_add", "Highland Rubber Co."],
            ["28 Sep 09:12", "strategy.kec", "create_trigger", "Promoter pledge above 30%"],
        ]
        self.cases: dict[str, dict] = {}
        for t in self.targets:
            cid = "d_" + t["id"]
            self.cases[cid] = self._new_case(cid, "deal", t["desks"][0], t["desks"], t["title"], t["signals"][0][1], target=t)
        for co in COMPANIES_ORDER:
            w = self.companies[co]
            cid = "t_" + co
            self.cases[cid] = self._new_case(cid, "threat", co, [co], w["threat_title"], w["timeline"][0][0], ws=w)
        # Approved last week, so the Follow-up screen is not empty on first open.
        e = self.cases["t_CEAT"]
        e.update(stage="act", ov_date="22 Sep", owner="Head of Strategy, CEAT", approved="22 Sep")
        e["plan"] = [{**p, "done": i == 0} for i, p in enumerate(rules.plan_for(e))]
        e["updates"] = [{"date": "26 Sep", "text": "CEAT opened talks with two EV 2-wheeler makers (plan step 1).", "fresh": False},
                        {"date": "24 Sep", "text": "Rival A posted 9 more EV battery roles.", "fresh": False}]
        if persist:
            self.persist()

    def _apply_persisted(self) -> None:
        """Overlay a previously-saved snapshot (persist.py) on top of the fresh demo defaults
        reset() just built — restores what a reviewer actually did (escalations, decisions,
        plans, theses, watch rules, universe additions, activity) across a restart."""
        saved = persistence.load()
        if not saved:
            return
        for cid, fields in (saved.get("cases") or {}).items():
            if cid in self.cases:
                self.cases[cid].update({k: v for k, v in fields.items() if k in _CASE_MUTABLE_FIELDS})
        self.book_order = [cid for cid in saved.get("book_order", []) if cid in self.cases]
        self.followed = set(saved.get("followed", []))
        if saved.get("activity"):
            self.activity = saved["activity"]
        if saved.get("theses"):
            self.theses = saved["theses"]
        self.acquisition_theses = saved.get("acquisition_theses", [])
        if saved.get("triggers"):
            self.triggers = saved["triggers"]
        if saved.get("universe"):
            self.universe = saved["universe"]

    def persist(self) -> None:
        """Save everything a reviewer can actually change, so it survives a restart. Called after
        every mutation (from audit(), since every external mutation already calls it — see
        radar/api.py — plus the one place that doesn't: unfollowing a rival)."""
        snapshot = {
            "cases": {cid: {k: c[k] for k in _CASE_MUTABLE_FIELDS} for cid, c in self.cases.items()},
            "book_order": self.book_order,
            "followed": sorted(self.followed),
            "activity": self.activity[:_MAX_ACTIVITY],
            "theses": self.theses,
            "acquisition_theses": self.acquisition_theses,
            "triggers": self.triggers,
            "universe": self.universe,
        }
        persistence.save(snapshot)

    @staticmethod
    def _new_case(cid, kind, co, cos, title, date, target=None, ws=None) -> dict:
        return {"id": cid, "kind": kind, "co": co, "cos": cos, "title": title, "date": date, "target": target, "ws": ws,
                "stage": "digest", "in_book": False, "owner": None, "approved": None, "approved_at": None, "plan": [], "updates": [],
                "up_next": 0, "outcome": None, "ov_date": None}

    def save_agent_swot(self, co: str) -> None:
        self.agent_saved[co] = {"swot": self.swot[co], "positions": self.positions[co],
                                "detail": self.swot_detail[co], "source": self.swot_source[co]}
        if self.on_agent_swot:
            self.on_agent_swot(co, copy.deepcopy(self.agent_saved[co]))

    # ---------- helpers ----------
    def audit(self, user: str, action: str, detail: str) -> None:
        now = datetime.now()
        self.activity.insert(0, [now.strftime("%d %b %H:%M"), user, action, detail])
        del self.activity[_MAX_ACTIVITY:]  # unbounded growth guard; the UI only shows the newest 40
        self.persist()

    def target(self, tid: str) -> dict | None:
        return next((t for t in self.targets if t["id"] == tid), None)

    def recs_for(self, co: str) -> list[dict]:
        return [{"co": co, "type": r[0], "title": r[1], "uses": r[2], "case_id": r[3], "why": r[4]} for r in self.swot[co]["rec"]]

    def rec_for_case(self, cid: str) -> dict | None:
        for co in COMPANIES_ORDER:
            for r in self.recs_for(co):
                if r["case_id"] == cid:
                    return r
        return None

    def group_skips(self) -> list[dict]:
        rec = {r["case_id"] for co in COMPANIES_ORDER for r in self.recs_for(co)}
        return [{"co": co, "case_id": cid, "why": why} for co in COMPANIES_ORDER for cid, why in self.swot[co]["skip"] if cid not in rec]

    def swot_item(self, co: str, ref: str) -> str:
        q, i = ref[0], int(ref[1:]) - 1
        x = self.swot[co][q][i]
        return x[0] if isinstance(x, list) else x

    # ---------- deep-dive jobs (202 + polling) ----------
    TICK = 0.45  # seconds per agent step in the demo; about 2 hours in production

    def start_job(self, case_ids: list[str], user: str) -> dict:
        jid = f"dd_{next(self._job_ids)}"
        for cid in case_ids:
            self.cases[cid]["stage"] = "deep"
            self.audit(user, "escalate", self.who(self.cases[cid]))
        self.jobs[jid] = {"id": jid, "case_ids": case_ids, "started": time.monotonic(), "done": False, "user": user}
        return self.job_status(jid)

    def job_status(self, jid: str) -> dict:
        j = self.jobs[jid]
        tick = int((time.monotonic() - j["started"]) / self.TICK)
        total = 7 + len(j["case_ids"]) - 1
        items = []
        for i, cid in enumerate(j["case_ids"]):
            c = self.cases[cid]
            steps = REF["DD_DEAL"] if c["kind"] == "deal" else REF["DD_THREAT"]
            s = max(0, min(len(steps), tick - i))
            cur = steps[min(s, len(steps) - 1)]
            items.append({"case_id": cid, "who": self.who(c), "title": c["title"], "done_steps": s, "total_steps": len(steps),
                          "current": None if s >= len(steps) else {"task": cur[0], "agent": cur[1]}})
        if tick > total and not j["done"]:
            j["done"] = True
            for cid in j["case_ids"]:
                c = self.cases[cid]
                c.update(stage="decide", ov_date=TODAY, in_book=True)
                if cid not in self.book_order:
                    self.book_order.append(cid)
            self.audit(j["user"], "book_written", f'{len(j["case_ids"])} pages')
        return {"id": jid, "status": "completed" if j["done"] else "running", "items": items}

    def settle_jobs(self) -> None:
        for jid in list(self.jobs):
            if not self.jobs[jid]["done"]:
                self.job_status(jid)

    # ---------- labels ----------
    @staticmethod
    def who(c: dict) -> str:
        return c["target"]["name"] if c["kind"] == "deal" else c["ws"]["rival"]

    def next_update(self, c: dict) -> str:
        nu = REF["NEXT_UPD"]
        if c["id"] in nu:
            lst = nu[c["id"]]
        elif c["kind"] == "deal":
            lst = [f'No new signals for {c["target"]["name"]} this week.', f'{c["target"]["scenario"]["rival"]} made no new moves.']
        else:
            lst = [f'{c["ws"]["rival"]} made no new moves this week.']
        text = lst[c["up_next"] % len(lst)]
        c["up_next"] += 1
        return text

    def snapshot(self) -> dict:
        return copy.deepcopy({k: v["stage"] for k, v in self.cases.items()})


STORE = Store()
