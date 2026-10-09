# DEMO/SYNTHETIC DATA ONLY.
#
# Every "watched entity" seeded below is a fully fictional company invented for
# this prototype — none corresponds to a real business, and none should ever
# be replaced with a real company name without a compliance/legal review of
# the resulting product, since this table drives "distress"/"acquisition
# target" framing. Real companies never come from this file: they enter only
# through the watchlist (discovery proposal or manual add) and a
# compliance_admin's approval — see DESIGN.md §15. The six RPG subsidiaries are
# seeded separately and are used ONLY as internal routing targets (the
# audience) — they are never watched entities themselves.
#
# This module is idempotent: calling seed() against an already-seeded
# database is a no-op.
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import hash_password
from db.models import DigestIssue, DigestItem, Entity, Reviewer, SignalCluster, Subsidiary, SubsidiaryDependency
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

# Hand-curated, same spirit as SUBSIDIARIES/ENTITIES above: each row is a
# known raw-material supplier, byproduct consumer, or shared service/vendor
# (including a sibling RPG subsidiary) for one subsidiary's own operations.
# Never discovered or inferred — powers services/ripple.py's "ripple effect"
# section of the Escalation Brief via pure keyword matching against a
# candidate entity's name/category/sectors, so every ripple claim traces
# back to one of these literal, reviewable rows.
DEPENDENCIES = [
    dict(subsidiary_code="CEAT", dependency_type="raw_material", counterparty_name="Malabar Rubber",
         counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
         description="Natural rubber supply for tyre compounding",
         keywords=["rubber", "latex", "plantation", "tyre"]),
    dict(subsidiary_code="CEAT", dependency_type="shared_service", counterparty_name="Zensar",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="ZENSAR",
         description="IT/software systems integration, analytics and support for connected/smart-tyre programs",
         keywords=["software", "sensor", "iot", "digital", "data", "analytics", "tech", "ai", "cognitive"]),
    dict(subsidiary_code="CEAT", dependency_type="shared_vendor", counterparty_name="Raychem RPG",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="RAYCHEM",
         description="Specialty materials and electrical components used in tyre-adjacent manufacturing",
         keywords=["materials", "electrical", "components"]),
    dict(subsidiary_code="CEAT", dependency_type="byproduct", counterparty_name="Regional retreading & reclaimed-rubber processors",
         counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
         description="Processors of tyre byproducts and end-of-life rubber",
         keywords=["recycl", "retread", "reclaimed", "byproduct"]),
    dict(subsidiary_code="KEC", dependency_type="shared_vendor", counterparty_name="Raychem RPG",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="RAYCHEM",
         description="Cable accessories and power-product components for EPC projects",
         keywords=["cable", "electrical", "power", "grid"]),
    dict(subsidiary_code="KEC", dependency_type="shared_service", counterparty_name="Zensar",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="ZENSAR",
         description="Project-management and ERP systems support for EPC execution",
         keywords=["software", "digital", "erp", "data", "analytics"]),
    dict(subsidiary_code="ZENSAR", dependency_type="shared_vendor", counterparty_name="Hyperscale cloud providers",
         counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
         description="Cloud infrastructure underlying client delivery and GenAI workloads",
         keywords=["cloud", "genai", "ai", "compute", "infrastructure"]),
    dict(subsidiary_code="RPGLS", dependency_type="raw_material", counterparty_name="API & bulk-drug intermediate suppliers",
         counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
         description="Active pharmaceutical ingredient and intermediate supply for formulation manufacturing",
         keywords=["api", "pharma", "intermediate", "bulk drug"]),
    dict(subsidiary_code="RPGLS", dependency_type="shared_service", counterparty_name="Zensar",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="ZENSAR",
         description="Regulatory/quality IT systems and data analytics support",
         keywords=["software", "digital", "data", "analytics", "compliance"]),
    dict(subsidiary_code="RAYCHEM", dependency_type="raw_material", counterparty_name="Specialty polymer & resin suppliers",
         counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
         description="Specialty polymers and resins for electrical/materials-engineering products",
         keywords=["polymer", "resin", "materials", "chemical"]),
    dict(subsidiary_code="RAYCHEM", dependency_type="shared_vendor", counterparty_name="CEAT",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="CEAT",
         description="Shared elastomer/rubber-compounding expertise and sourcing",
         keywords=["rubber", "elastomer", "compounding"]),
    dict(subsidiary_code="HARRISONS", dependency_type="raw_material", counterparty_name="Plantation agri-input suppliers",
         counterparty_kind="external_vendor", counterparty_subsidiary_code=None,
         description="Agricultural inputs (saplings, fertilizer) for plantation operations",
         keywords=["plantation", "agri", "fertilizer", "rubber", "tea"]),
    dict(subsidiary_code="HARRISONS", dependency_type="shared_vendor", counterparty_name="Raychem RPG",
         counterparty_kind="rpg_subsidiary", counterparty_subsidiary_code="RAYCHEM",
         description="Shared materials-testing/quality-lab resources for rubber byproducts",
         keywords=["rubber", "materials", "byproduct"]),
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


async def _seed_dependencies(db: AsyncSession) -> None:
    # Its own idempotency check, separate from seed()'s early return below, so
    # this backfills onto a database that was seeded before this table existed.
    existing = (await db.execute(select(func.count()).select_from(SubsidiaryDependency))).scalar_one()
    if existing > 0:
        return
    for row in DEPENDENCIES:
        db.add(SubsidiaryDependency(**row))
    await db.commit()
    log.info("db_seeded_dependencies", count=len(DEPENDENCIES))


# Which subsidiary each seed entity's M&A-potential signal belongs to — the
# same sector-overlap routing services/routing.py computes at ingest time,
# spelled out here so the historical digests below can pick realistic,
# VARYING per-week combinations without re-deriving it. Entity names must
# match ENTITIES above exactly.
ENTITY_SUBSIDIARY = {
    "Meridian Treadworks Pvt Ltd": "CEAT",
    "Ashford EPC Projects Ltd": "KEC",
    "Veltrix Biopharma Ltd": "RPGLS",
    "Corvane Materials Systems Ltd": "RAYCHEM",
    "Northfield Cognitive Systems Inc": "ZENSAR",
    "Solstice BFSI Analytics Ltd": "ZENSAR",
    "Palmgrove Estates Cooperative": "HARRISONS",
}

# Three past weeks, each a different, realistic subset of entities — directly
# answers "not every subsidiary gets an M&A-potential signal every week."
# Entity lists intentionally overlap/rotate rather than being exhaustive.
HISTORICAL_DIGEST_WEEKS = [
    (24, ["Meridian Treadworks Pvt Ltd"]),  # a quiet week: one subsidiary only
    (17, ["Ashford EPC Projects Ltd", "Corvane Materials Systems Ltd", "Northfield Cognitive Systems Inc"]),  # a busy week
    (9, ["Veltrix Biopharma Ltd", "Palmgrove Estates Cooperative"]),  # a different pair
]


async def _seed_historical_digests(db: AsyncSession) -> None:
    # Own idempotency check: skip if ANY digest already exists (manual
    # generation, the scheduler's own run, or a previous call to this
    # function), so this never double-seeds or fights real digest history.
    existing = (await db.execute(select(func.count()).select_from(DigestIssue))).scalar_one()
    if existing > 0:
        return
    clusters_by_entity_name = dict(
        (await db.execute(
            select(Entity.name, SignalCluster.id).join(SignalCluster, SignalCluster.entity_id == Entity.id)
        )).all()
    )
    now = datetime.utcnow()
    for days_ago, entity_names in HISTORICAL_DIGEST_WEEKS:
        period_end = now - timedelta(days=days_ago)
        digest = DigestIssue(period_start=period_end - timedelta(days=7), period_end=period_end, created_at=period_end)
        db.add(digest)
        await db.flush()
        for name in entity_names:
            cluster_id = clusters_by_entity_name.get(name)
            sub_code = ENTITY_SUBSIDIARY.get(name)
            if cluster_id and sub_code:
                db.add(DigestItem(digest_id=digest.id, cluster_id=cluster_id, subsidiary_code=sub_code))
    log.info("db_seeded_historical_digests", weeks=len(HISTORICAL_DIGEST_WEEKS))


async def seed(db: AsyncSession) -> None:
    await _seed_dependencies(db)

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

    await _seed_historical_digests(db)

    await db.commit()

    log.info("db_seeded", reviewers=[r["email"] for r in REVIEWERS])
    print("\n[RPG Horizon Radar] Seeded demo data. Demo reviewer logins (local prototype only):")
    for row in REVIEWERS:
        print(f"  - {row['email']}  /  {DEMO_PASSWORD}   ({row['role']})")
    print()
