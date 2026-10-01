"""Connectors that read a level and signal a change in it: job postings
(Adzuna) and patent publications (EPO OPS). A level on its own says little;
the swing since the last reading is the signal. Adzuna's first reading only
sets the baseline (kept in connector state); EPO compares two windows in one
pull.

Adzuna    ~250 calls a month on the free key; weekly pull.
EPO OPS   free 4 GB a week; OAuth client credentials; weekly pull, two
          count-only searches (last 6 months and the 6 before)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta

import httpx

from db.models import Entity
from ingestion.connectors.live.common import LiveConnector, get_json
from shared.config import get_settings
from shared.http import client


def _snapshot(state: dict, provider: str, entity: Entity, value: dict) -> dict | None:
    """Store this reading and return the previous one."""
    snaps = state.setdefault("snapshots", {}).setdefault(provider, {})
    prev = snaps.get(str(entity.id))
    snaps[str(entity.id)] = {**value, "at": datetime.now().isoformat(timespec="seconds")}
    return prev


class Adzuna(LiveConnector):
    name, source_type = "Adzuna", "hiring"
    URL = "https://api.adzuna.com/v1/api/jobs/in/search/1"
    min_days = 7
    UP, DOWN, MIN_BASE = 1.5, 0.5, 20  # ratio thresholds; swings on tiny counts are ignored

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        s = get_settings()
        self.app_id, self.app_key = s.adzuna_app_id, s.adzuna_app_key

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.app_key)

    def pull(self, entity: Entity, query: str) -> list[dict]:
        params = {"app_id": self.app_id, "app_key": self.app_key, "company": query, "max_days_old": 30,
                  "results_per_page": 20, "content-type": "application/json"}
        with client(self.transport) as c:
            body = get_json(c.get(self.URL, params=params), self.name)
        count = int(body.get("count") or 0)
        prev = _snapshot(self.state, self.name, entity, {"count": count})
        if not prev:
            return []
        before = prev["count"]
        if count >= self.MIN_BASE and count >= before * self.UP:
            kind, verb = "hiring_scaleup", "up"
        elif before >= self.MIN_BASE and count <= before * self.DOWN:
            kind, verb = "hiring_scaledown", "down"
        else:
            return []
        titles = list(dict.fromkeys(j.get("title", "").strip() for j in body.get("results") or [] if j.get("title")))[:3]
        return [self.signal(kind, f"{entity.name} job postings {verb} from {before} to {count} (30-day window)", datetime.now(),
                            excerpt=f"Adzuna India postings naming {query}, compared with the reading on {prev['at'][:10]}."
                                    + (f" Recent titles: {'; '.join(titles)}." if titles else ""))]


class EPOPatents(LiveConnector):
    """GET /published-data/search/biblio with a CQL query on applicant and
    publication date; only the total count is read."""
    name, source_type = "EPO patents", "patent"
    TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
    URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
    min_days = 7
    HALF = 182  # days per window
    MIN_COUNT = 5
    _token: tuple[str, float] | None = None  # (token, expiry), shared by instances

    def __init__(self, state, transport=None):
        super().__init__(state, transport)
        s = get_settings()
        self.key, self.secret = s.epo_ops_consumer_key, s.epo_ops_consumer_secret

    @property
    def configured(self) -> bool:
        return bool(self.key and self.secret)

    def _access_token(self, c: httpx.Client) -> str:
        tok = EPOPatents._token
        if tok and tok[1] > time.time() + 60:
            return tok[0]
        body = get_json(c.post(self.TOKEN_URL, auth=(self.key, self.secret), data={"grant_type": "client_credentials"}), self.name)
        EPOPatents._token = (body["access_token"], time.time() + int(body.get("expires_in", 1200)))
        return body["access_token"]

    def _count(self, c: httpx.Client, applicant: str, start: datetime, end: datetime) -> int:
        cql = f'pa="{applicant}" and pd within "{start:%Y%m%d} {end:%Y%m%d}"'
        r = c.get(self.URL, params={"q": cql, "Range": "1-1"},
                  headers={"Authorization": f"Bearer {self._access_token(c)}", "Accept": "application/json"})
        if r.status_code == 404:  # OPS answers "no results" with 404
            return 0
        search = get_json(r, self.name).get("ops:world-patent-data", {}).get("ops:biblio-search", {})
        return int(search.get("@total-result-count", 0))

    def pull(self, entity: Entity, query: str) -> list[dict]:
        today = datetime.now()
        mid, start = today - timedelta(days=self.HALF), today - timedelta(days=2 * self.HALF)
        with client(self.transport) as c:
            recent = self._count(c, query, mid, today)
            before = self._count(c, query, start, mid - timedelta(days=1))
        if recent >= self.MIN_COUNT and recent >= 2 * before:
            verb = "up"
        elif before >= self.MIN_COUNT and recent <= before / 2:
            verb = "down"
        else:
            return []
        return [self.signal("patent_shift", f"{entity.name} patent publications {verb} from {before} to {recent} (last 6 months vs the 6 before)",
                            today, excerpt=f"EPO worldwide publications naming {query} as applicant.",
                            url="https://worldwide.espacenet.com/patent/search?q=pa%3D%22" + query.replace(" ", "%20") + "%22")]
