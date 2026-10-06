"""End-to-end: marking a real signal cluster under evaluation produces an
Escalation Brief whose ripple_effects section is populated from the seeded
SubsidiaryDependency rows (see db/seed.py's DEPENDENCIES, services/ripple.py)."""
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


def _a_scored_cluster_routed_to_ceat() -> int:
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
            raise AssertionError("no seeded, scored CEAT-routed signal cluster found to test against")

    return asyncio.run(_find())


def test_mark_under_evaluation_includes_ripple_effects(seeded):
    cluster_id = _a_scored_cluster_routed_to_ceat()
    headers = login(seeded, "compliance.admin@rpg-demo.local")

    r = seeded.post(f"/api/v1/signals/{cluster_id}/mark-under-evaluation", headers=headers)
    assert r.status_code == 200, r.text

    r = seeded.get(f"/api/v1/signals/{cluster_id}/escalation-brief", headers=headers)
    assert r.status_code == 200, r.text
    brief = r.json()
    assert len(brief["ripple_effects"]) > 0
    assert all(r["subsidiary_code"] == "CEAT" for r in brief["ripple_effects"])
    # At least one of CEAT's seeded dependency rows (Zensar/Malabar Rubber/
    # Raychem RPG/retread processors) must surface, cited verbatim.
    names = {r["counterparty_name"] for r in brief["ripple_effects"]}
    assert names & {"Zensar", "Malabar Rubber", "Raychem RPG", "Regional retreading & reclaimed-rubber processors"}
