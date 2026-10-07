"""The radar's working state. It holds real records and what reviewers did with them, nothing
invented:

- rivals / live   watched companies per RPG company, with their recent public signals
                  and rule-based score (filled by bridge.py from the database);
- cases           one per watched company with signals: an M&A signal, which a user views (its
                  acquisition thesis), shortlists or dismisses to the archive. Rebuilt on every
                  sync; its status carries over;
- swot            a company's SWOT once the SWOT Analyst has built one (kept in swot_briefs);
- theses, triggers, universe, activity   what users created.

Everything a reviewer changes is snapshotted to the database after each change (persistence.py)
and restored at startup."""
from __future__ import annotations

import copy
from datetime import datetime

from . import persistence

COMPANIES_ORDER = ["CEAT", "KEC", "Zensar", "RPG Life Sciences", "Raychem RPG", "Harrisons"]

# Per-case fields a user changes. The rest of a case is rebuilt from the database on every sync,
# so only these are persisted. status: open | shortlisted | dismissed (the archive).
CASE_MUTABLE_FIELDS = ("status", "status_at", "status_by")
STATUSES = ("open", "shortlisted", "dismissed")
# Saved by earlier versions (the book: decide, act, closed) -> today's status.
_OLD_STAGE = {"digest": "open", "decide": "shortlisted", "act": "shortlisted", "closed": "dismissed"}
_MAX_ACTIVITY = 500  # growth guard; the UI shows the newest 40


def today() -> str:
    return datetime.now().strftime("%d %b")


def week_label() -> str:
    return f"Week {datetime.now().isocalendar().week}"


class Store:
    def __init__(self) -> None:
        self.on_agent_swot = None  # set by bridge.startup(): persists a SWOT the agent built
        self.agent_saved: dict = {}
        self.swot: dict = {}  # company -> {"S", "W", "O", "T", "rec", "skip"}, only once the agent built it
        self.positions: dict = {}
        self.swot_detail: dict = {}
        self.swot_source: dict = {}
        self.rivals: dict = {co: [] for co in COMPANIES_ORDER}
        self.live: dict = {co: [] for co in COMPANIES_ORDER}
        self.live_meta: dict = {}
        # Public research on each RPG company itself (services/company_research.py): {at, facts, errors}
        self.research: dict = {co: {} for co in COMPANIES_ORDER}
        # Each company's SWOT parameters (services/swot_settings.py), and the daily findings of the
        # last week users kept (agents/opportunity_analyst.py) — both evidence for the weekly SWOT.
        self.swot_settings: dict = {}
        # Company sizes (services/company_size.py), by ConnectorState key: size:entity:<id>, size:rpg:<code>
        self.sizes: dict = {}
        self.kept_findings: dict = {co: [] for co in COMPANIES_ORDER}
        self.cases: dict[str, dict] = {}
        self._saved_cases: dict[str, dict] = {}  # persisted case fields, applied as cases are built
        self.activity: list[list] = []
        self.theses: list[dict] = []
        self.triggers: list[dict] = []
        self.universe: list[list] = []

    # ---------- loading ----------
    def use_agent_swot(self, co: str, saved: dict) -> None:
        self.agent_saved[co] = saved
        self.swot[co], self.positions[co], self.swot_detail[co], self.swot_source[co] = \
            saved["swot"], saved["positions"], saved["detail"], saved["source"]

    def set_rivals(self, rivals: dict[str, list[dict]]) -> None:
        """New data from bridge.sync(): rebuild the cases, keeping what reviewers did with them."""
        self.rivals = rivals
        self.live = {co: sorted((s for r in rs for s in r["signals"]), key=lambda s: s["observed_at"], reverse=True)
                     for co, rs in rivals.items()}
        built: dict[str, dict] = {}
        for co in COMPANIES_ORDER:
            for r in rivals.get(co, []):
                cid = f"r{r['id']}"
                if cid in built:
                    built[cid]["cos"].append(co)
                    continue
                latest = r["signals"][0]
                built[cid] = {"id": cid, "kind": "rival", "entity_id": r["id"], "role": r.get("role", "competitor"), "who": r["name"], "co": co, "cos": [co],
                              "title": f"{r['name']}: {len(r['signals'])} public signal{'s' if len(r['signals']) != 1 else ''}, latest {latest['label'].lower()} on {latest['date']}",
                              "date": latest["date"], "signals": r["signals"], "score": r["score"], "rationale": r["rationale"],
                              "types": r["types"], "watched_since": r["watched_since"]}
        for cid, c in built.items():
            prev = self.cases.get(cid) or self._saved_cases.get(cid) or {}
            c.update(self._new_state() | {k: prev[k] for k in CASE_MUTABLE_FIELDS if k in prev})
        # A shortlisted or archived signal stays (with its last signals) even if its company is no longer watched.
        for cid, c in self.cases.items():
            if cid not in built and c["status"] != "open":
                built[cid] = c
        self.cases = built

    @staticmethod
    def _new_state() -> dict:
        return {"status": "open", "status_at": None, "status_by": None}

    @staticmethod
    def _upgrade(saved: dict) -> dict:
        """A case saved by an earlier version (book stages) in today's fields."""
        if "status" in saved:
            return saved
        return {"status": _OLD_STAGE.get(saved.get("stage", "digest"), "open"), "status_at": saved.get("approved_at"), "status_by": saved.get("owner")}

    def apply_persisted(self) -> None:
        saved = persistence.load()
        if not saved:
            return
        self._saved_cases = {cid: self._upgrade(v) for cid, v in (saved.get("cases") or {}).items()}
        self.activity = saved.get("activity", [])
        self.theses = saved.get("theses", [])
        self.triggers = saved.get("triggers", [])
        self.universe = saved.get("universe", [])

    def persist(self) -> None:
        cases = {**self._saved_cases, **{cid: {k: c[k] for k in CASE_MUTABLE_FIELDS} for cid, c in self.cases.items()}}
        persistence.save({"cases": {cid: v for cid, v in cases.items() if v.get("status", "open") != "open"},
                          "activity": self.activity[:_MAX_ACTIVITY],
                          "theses": self.theses, "triggers": self.triggers, "universe": self.universe})

    def save_agent_swot(self, co: str) -> None:
        self.agent_saved[co] = {"swot": self.swot[co], "positions": self.positions[co],
                                "detail": self.swot_detail[co], "source": self.swot_source[co]}
        if self.on_agent_swot:
            self.on_agent_swot(co, copy.deepcopy(self.agent_saved[co]))

    # ---------- actions ----------
    def audit(self, user: str, action: str, detail: str) -> None:
        self.activity.insert(0, [datetime.now().strftime("%d %b %H:%M"), user, action, detail])
        del self.activity[_MAX_ACTIVITY:]
        self.persist()

    def set_status(self, cid: str, status: str, user: str) -> dict:
        """Shortlist, dismiss to the archive, or reopen an M&A signal."""
        c = self.cases[cid]
        c.update(status=status, status_at=datetime.now().strftime("%d %b %Y"), status_by=user)
        self.audit(user, {"shortlisted": "shortlist", "dismissed": "dismiss", "open": "reopen"}[status], c["who"])
        return c

    # ---------- SWOT lookups ----------
    def recs_for(self, co: str) -> list[dict]:
        rec = (self.swot.get(co) or {}).get("rec", [])
        return [{"co": co, "type": r[0], "title": r[1], "uses": r[2], "case_id": r[3], "why": r[4]} for r in rec if r[3] in self.cases]

    def rec_for_case(self, cid: str) -> dict | None:
        return next((r for co in COMPANIES_ORDER for r in self.recs_for(co) if r["case_id"] == cid), None)

    def skips_for(self, co: str) -> list[dict]:
        skip = (self.swot.get(co) or {}).get("skip", [])
        return [{"co": co, "case_id": cid, "why": why} for cid, why in skip if cid in self.cases]

    def swot_item(self, co: str, ref: str) -> str:
        q, i = ref[0], int(ref[1:]) - 1
        x = self.swot[co][q][i]
        return x[0] if isinstance(x, list) else x


STORE = Store()
