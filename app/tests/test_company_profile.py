"""Company Profile is a qualitative read on the signal's target entity
(listing status, directional market-reaction/integration/deal-structure
heuristics) — available for ANY visible signal, live or under_evaluation,
unlike the Escalation Brief which only exists post hand-off."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from db import base
from db.models import ClusterSubsidiaryLink, SignalCluster

PASSWORD = "ChangeMe123!"


def login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _a_scored_live_cluster_routed_to_ceat() -> int:
    async def _find() -> int:
        async with base.get_db_session() as db:
            rows = (
                await db.execute(
                    select(SignalCluster)
                    .join(ClusterSubsidiaryLink, ClusterSubsidiaryLink.cluster_id == SignalCluster.id)
                    .where(ClusterSubsidiaryLink.subsidiary_code == "CEAT", SignalCluster.status == "live")
                )
            ).scalars().unique().all()
            for c in rows:
                if c.opportunity_score is not None:
                    return c.id
            raise AssertionError("no seeded, scored CEAT-routed live signal cluster found to test against")

    return asyncio.run(_find())


def test_company_profile_available_for_a_live_signal(seeded):
    cluster_id = _a_scored_live_cluster_routed_to_ceat()
    headers = login(seeded, "compliance.admin@rpg-demo.local")

    r = seeded.get(f"/api/v1/signals/{cluster_id}/company-profile", headers=headers)
    assert r.status_code == 200, r.text
    profile = r.json()

    assert profile["listing_status"] in ("public", "private")
    assert profile["listing_label"]
    for field in ("market_reaction", "integration_stance", "deal_structure_hint", "regulatory_note", "disclaimer"):
        assert profile[field]

    # Hard rule: no valuation/price/percentage figure ever appears in this payload.
    blob = " ".join(profile.values())
    for banned in ("$", "₹", "crore", "%"):
        assert banned not in blob


def test_company_profile_404_for_unknown_cluster(seeded):
    headers = login(seeded, "compliance.admin@rpg-demo.local")
    r = seeded.get("/api/v1/signals/999999/company-profile", headers=headers)
    assert r.status_code == 404
