"""The Executive Dashboard's data source: GET /api/v1/radar/digest-swot.
Verifies the historical seed digests exist with varying subsidiary coverage
(the "not every subsidiary gets a signal every week" realism) and that the
endpoint scopes SWOT to exactly the subsidiaries with a signal in a digest."""
from __future__ import annotations

PASSWORD = "ChangeMe123!"
R = "/api/v1/radar"


class Client:
    def __init__(self, c, email):
        self.c = c
        tok = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["token"]
        self.h = {"Authorization": f"Bearer {tok}"}

    def __getattr__(self, method):
        return lambda path, **kw: getattr(self.c, method)(R + path, headers=self.h, **kw)


def test_historical_digests_seeded_with_varying_subsidiary_coverage(seeded):
    admin_token = seeded.post("/api/v1/auth/login", json={"email": "compliance.admin@rpg-demo.local", "password": PASSWORD}).json()["token"]
    h = {"Authorization": f"Bearer {admin_token}"}
    digests = seeded.get("/api/v1/digests", headers=h).json()
    assert len(digests) >= 3, "historical seed digests should exist"
    coverage = {d["id"]: sorted(d["subsidiary_breakdown"]) for d in digests}
    # The three seeded weeks have different subsidiary counts/sets — not identical every week.
    distinct_sets = {tuple(v) for v in coverage.values() if v}
    assert len(distinct_sets) > 1, f"expected varying weekly coverage, got {coverage}"
    assert any(len(v) == 1 for v in coverage.values()), "expected at least one single-subsidiary week"


def test_digest_swot_scopes_to_subsidiaries_with_a_signal(seeded):
    admin = Client(seeded, "compliance.admin@rpg-demo.local")
    digests = seeded.get("/api/v1/digests", headers=admin.h).json()
    one_subsidiary_digest = next(d for d in digests if len(d["subsidiary_breakdown"]) == 1)

    out = admin.get("/digest-swot", params={"digest_id": one_subsidiary_digest["id"]}).json()
    assert out["digest"]["id"] == one_subsidiary_digest["id"]
    assert len(out["subsidiaries"]) == 1
    sub = out["subsidiaries"][0]
    assert sub["signal_count"] == 1
    assert "swot" in sub and sub["swot"]["company"] == sub["co"]


def test_digest_swot_defaults_to_latest_digest(seeded):
    admin = Client(seeded, "compliance.admin@rpg-demo.local")
    digests = seeded.get("/api/v1/digests", headers=admin.h).json()
    latest = max(digests, key=lambda d: d["created_at"])

    out = admin.get("/digest-swot").json()
    assert out["digest"]["id"] == latest["id"]


def test_digest_swot_unknown_id_is_an_honest_empty_state(seeded):
    admin = Client(seeded, "compliance.admin@rpg-demo.local")
    out = admin.get("/digest-swot", params={"digest_id": 999999}).json()
    assert out == {"digest": None, "subsidiaries": []}
