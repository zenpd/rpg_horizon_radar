# DEMO/SYNTHETIC DATA ONLY.
#
# Every "watched entity" seeded below is a fully fictional company invented for
# this prototype — none corresponds to a real business, and none should ever
# be replaced with a real company name without a compliance/legal review of
# the resulting product, since this table drives "distress"/"acquisition
# target" framing. The six RPG subsidiaries are seeded separately and are used
# ONLY as internal routing targets (the audience) — they are never watched
# entities themselves.
#
# This module is idempotent: calling seed() against an already-seeded
# database is a no-op.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import hash_password
from db.models import Entity, Reviewer, Subsidiary
from services.ingest import fetch_and_store_raw_signals, recompute_cluster_for_entity
from shared.logger import get_logger

log = get_logger("db.seed")

DEMO_PASSWORD = "ChangeMe123!"

SUBSIDIARIES = [
    dict(
        code="CEAT",
        name="CEAT",
        sectors=["tyres", "mobility"],
        compliance_gate=True,  # the MVP/Phase-1 pilot sector — see DESIGN.md §11
        signal_focus="Distressed component suppliers, adjacent mobility/tyre-tech players, regional manufacturing consolidation.",
    ),
    dict(
        code="KEC",
        name="KEC International",
        sectors=["epc", "materials-adjacent"],
        compliance_gate=False,
        signal_focus="Competitor project distress, adjacent EPC/materials capability gaps, overseas market entry openings.",
    ),
    dict(
        code="ZENSAR",
        name="Zensar",
        sectors=["it-services", "ai-genai", "bfsi-services"],
        compliance_gate=False,
        signal_focus="Niche AI/GenAI capability acquisitions, smaller BFSI-focused service providers under pressure.",
    ),
    dict(
        code="RPGLS",
        name="RPG Life Sciences",
        sectors=["pharma", "api-manufacturing"],
        compliance_gate=False,
        signal_focus="Smaller pharma/API manufacturers with regulatory or capital distress signals.",
    ),
    dict(
        code="RAYCHEM",
        name="Raychem RPG",
        sectors=["materials-engineering", "electrical-components"],
        compliance_gate=False,
        signal_focus="Adjacent materials-engineering or electrical-components players showing consolidation potential.",
    ),
    dict(
        code="HARRISONS",
        name="Harrisons Malayalam",
        sectors=["plantations", "agri-processing"],
        compliance_gate=False,
        signal_focus="Regional plantation or agri-processing assets showing distress or succession-driven sale signals.",
    ),
]

ENTITIES = [
    dict(name="Meridian Treadworks Pvt Ltd", sectors=["tyres", "mobility"], category="Regional tyre-components supplier"),
    dict(name="Ashford EPC Projects Ltd", sectors=["epc"], category="Mid-sized EPC contractor"),
    dict(name="Veltrix Biopharma Ltd", sectors=["pharma", "api-manufacturing"], category="API manufacturer"),
    dict(
        name="Corvane Materials Systems Ltd",
        sectors=["materials-engineering", "electrical-components"],
        category="Materials-engineering firm",
    ),
    dict(name="Northfield Cognitive Systems Inc", sectors=["ai-genai"], category="AI/GenAI software vendor"),
    dict(name="Solstice BFSI Analytics Ltd", sectors=["bfsi-services"], category="BFSI-focused analytics provider"),
    dict(
        name="Palmgrove Estates Cooperative",
        sectors=["plantations", "agri-processing"],
        category="Regional plantation / agri-processing cooperative",
    ),
]

REVIEWERS = [
    dict(
        name="Compliance Admin",
        email="compliance.admin@rpg-demo.local",
        role="compliance_admin",
        subsidiary_scopes=[],  # compliance_admin bypasses scope checks entirely
    ),
    dict(
        name="Corporate Strategy — CEAT Desk",
        email="strategy.ceat@rpg-demo.local",
        role="corp_strategy_reviewer",
        subsidiary_scopes=["CEAT"],
    ),
    dict(
        name="Corporate Strategy — KEC Desk",
        email="strategy.kec@rpg-demo.local",
        role="corp_strategy_reviewer",
        subsidiary_scopes=["KEC"],
    ),
]


async def seed(db: AsyncSession) -> None:
    existing = (await db.execute(select(func.count()).select_from(Subsidiary))).scalar_one()
    if existing > 0:
        return  # already seeded

    now = datetime.utcnow()

    for row in SUBSIDIARIES:
        db.add(Subsidiary(**row))

    for row in ENTITIES:
        db.add(Entity(**row, is_fictional=True))

    for row in REVIEWERS:
        db.add(
            Reviewer(
                name=row["name"],
                email=row["email"],
                password_hash=hash_password(DEMO_PASSWORD),
                role=row["role"],
                subsidiary_scopes=row["subsidiary_scopes"],
                created_at=now,
            )
        )

    await db.flush()

    # Populate raw signals + clusters/scores/routing for every seed entity
    # (not just gated-open ones) by reusing the exact same functions the
    # ingestion pipeline calls, so seed data and a live ingest run can never
    # diverge in behavior. Routing links to gated-off subsidiaries are
    # recorded but stay invisible to reviewers until that subsidiary's gate
    # opens (see services/visibility.py).
    all_subsidiaries = (await db.execute(select(Subsidiary))).scalars().all()
    all_entities = (await db.execute(select(Entity))).scalars().all()
    for entity in all_entities:
        await fetch_and_store_raw_signals(db, entity)
    for entity in all_entities:
        await recompute_cluster_for_entity(db, entity, all_subsidiaries)

    await db.commit()

    log.info("db_seeded", reviewers=[r["email"] for r in REVIEWERS])
    print("\n[RPG Horizon Radar] Seeded demo data. Demo reviewer logins (local prototype only):")
    for row in REVIEWERS:
        print(f"  - {row['email']}  /  {DEMO_PASSWORD}   ({row['role']})")
    print()
