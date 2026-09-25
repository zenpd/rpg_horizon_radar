from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer, require_role
from api.dependencies import get_db
from api.schemas.escalation_brief import EscalationBriefOut
from api.schemas.signal import RawSignalOut, SignalClusterDetail, SignalClusterSummary
from db.models import EscalationBrief, RawSignal, Reviewer, SignalCluster, Subsidiary
from services import visibility
from services.audit import write_audit
from services.escalation_brief import generate_escalation_brief

router = APIRouter()


async def _subsidiary_map(db: AsyncSession) -> dict[str, Subsidiary]:
    result = await db.execute(select(Subsidiary))
    return {s.code: s for s in result.scalars().all()}


def _visible_codes_for(cluster: SignalCluster, reviewer: Reviewer, sub_map: dict) -> list[str]:
    return [
        link.subsidiary_code
        for link in cluster.subsidiary_links
        if visibility.subsidiary_code_visible_to(reviewer, link.subsidiary_code, sub_map)
    ]


def _is_visible(cluster: SignalCluster, reviewer: Reviewer, sub_map: dict) -> bool:
    return len(_visible_codes_for(cluster, reviewer, sub_map)) > 0


def _build_summary(cluster: SignalCluster, reviewer: Reviewer, sub_map: dict) -> SignalClusterSummary:
    score_row = cluster.opportunity_score
    return SignalClusterSummary(
        id=cluster.id,
        entity_name=cluster.entity.name,
        entity_sectors=cluster.entity.sectors or [],
        subsidiaries=_visible_codes_for(cluster, reviewer, sub_map),
        score=score_row.score if score_row else 0.0,
        rationale=score_row.rationale if score_row else "",
        signal_types=score_row.signal_types_json if score_row else [],
        status=cluster.status,
        updated_at=cluster.updated_at,
    )


def _brief_out(brief: EscalationBrief) -> EscalationBriefOut:
    return EscalationBriefOut(
        id=brief.id,
        cluster_id=brief.cluster_id,
        generated_at=brief.generated_at,
        escalated_by=brief.escalated_by.name if brief.escalated_by else None,
        pros=brief.pros,
        cons=brief.cons,
        directional_considerations=brief.directional_considerations,
        deal_complexity=brief.deal_complexity,
        disclaimer=brief.disclaimer,
    )


async def _windowed_raw_signals(db: AsyncSession, cluster: SignalCluster) -> list[RawSignal]:
    result = await db.execute(
        select(RawSignal)
        .where(
            RawSignal.entity_id == cluster.entity_id,
            RawSignal.observed_at >= cluster.window_start,
            RawSignal.observed_at <= cluster.window_end,
        )
        .order_by(RawSignal.observed_at.asc())
    )
    return result.scalars().all()


@router.get("", response_model=list[SignalClusterSummary])
async def list_signals(
    subsidiary: str | None = None,
    status: str = "live",
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    sub_map = await _subsidiary_map(db)

    query = select(SignalCluster)
    if status:
        query = query.where(SignalCluster.status == status)
    query = query.order_by(SignalCluster.updated_at.desc())
    clusters = (await db.execute(query)).scalars().all()

    if subsidiary:
        clusters = [c for c in clusters if any(link.subsidiary_code == subsidiary for link in c.subsidiary_links)]
        target_sub = sub_map.get(subsidiary)
        if target_sub is None or not visibility.subsidiary_visible_to(reviewer, target_sub):
            clusters = []

    visible_clusters = [c for c in clusters if _is_visible(c, reviewer, sub_map)]

    await write_audit(
        db, reviewer, "view_signal_list", "signal_cluster",
        detail=f"subsidiary={subsidiary} status={status}",
    )

    return [_build_summary(c, reviewer, sub_map) for c in visible_clusters]


@router.get("/{cluster_id}", response_model=SignalClusterDetail)
async def get_signal(
    cluster_id: int,
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    sub_map = await _subsidiary_map(db)
    cluster = (await db.execute(select(SignalCluster).where(SignalCluster.id == cluster_id))).scalar_one_or_none()

    # 404 (not 403) when invisible, so the response never confirms existence.
    if cluster is None or not _is_visible(cluster, reviewer, sub_map):
        raise HTTPException(status_code=404, detail="Signal cluster not found")

    await write_audit(db, reviewer, "view_signal", "signal_cluster", resource_id=cluster_id)

    windowed_raw = await _windowed_raw_signals(db, cluster)
    summary = _build_summary(cluster, reviewer, sub_map)
    return SignalClusterDetail(
        **summary.model_dump(),
        entity_id=cluster.entity_id,
        entity_category=cluster.entity.category,
        window_start=cluster.window_start,
        window_end=cluster.window_end,
        raw_signals=[RawSignalOut.model_validate(r) for r in windowed_raw],
        evaluated_by=cluster.evaluated_by.name if cluster.evaluated_by else None,
        evaluated_at=cluster.evaluated_at,
    )


@router.post("/{cluster_id}/mark-under-evaluation", response_model=SignalClusterDetail)
async def mark_under_evaluation(
    cluster_id: int,
    admin: Reviewer = Depends(require_role("compliance_admin")),
    db: AsyncSession = Depends(get_db),
):
    sub_map = await _subsidiary_map(db)
    cluster = (await db.execute(select(SignalCluster).where(SignalCluster.id == cluster_id))).scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Signal cluster not found")

    # One-way hand-off: once marked, the tool's involvement is over. There is
    # deliberately no "unmark" endpoint anywhere in this API.
    cluster.status = "under_evaluation"
    cluster.evaluated_by_id = admin.id
    cluster.evaluated_at = datetime.utcnow()

    # Generate the Escalation Brief in the same transaction as the hand-off —
    # see DESIGN.md §14. Write-once: no regenerate/update endpoint exists.
    if cluster.opportunity_score is not None and cluster.escalation_brief is None:
        routed_subsidiaries = [
            sub_map[link.subsidiary_code] for link in cluster.subsidiary_links if link.subsidiary_code in sub_map
        ]
        db.add(
            generate_escalation_brief(
                cluster, cluster.opportunity_score, cluster.entity, routed_subsidiaries, admin
            )
        )

    await db.commit()
    await db.refresh(cluster)

    await write_audit(db, admin, "mark_under_evaluation", "signal_cluster", resource_id=cluster_id)

    windowed_raw = await _windowed_raw_signals(db, cluster)
    summary = _build_summary(cluster, admin, sub_map)
    return SignalClusterDetail(
        **summary.model_dump(),
        entity_id=cluster.entity_id,
        entity_category=cluster.entity.category,
        window_start=cluster.window_start,
        window_end=cluster.window_end,
        raw_signals=[RawSignalOut.model_validate(r) for r in windowed_raw],
        evaluated_by=cluster.evaluated_by.name if cluster.evaluated_by else None,
        evaluated_at=cluster.evaluated_at,
    )


@router.get("/{cluster_id}/escalation-brief", response_model=EscalationBriefOut)
async def get_escalation_brief(
    cluster_id: int,
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    sub_map = await _subsidiary_map(db)
    cluster = (await db.execute(select(SignalCluster).where(SignalCluster.id == cluster_id))).scalar_one_or_none()

    if cluster is None or not _is_visible(cluster, reviewer, sub_map):
        raise HTTPException(status_code=404, detail="Signal cluster not found")

    if cluster.escalation_brief is None:
        raise HTTPException(
            status_code=404,
            detail="No escalation brief exists for this signal — it is only generated when a "
            "signal is marked under active evaluation.",
        )

    await write_audit(db, reviewer, "view_escalation_brief", "escalation_brief", resource_id=cluster_id)
    return _brief_out(cluster.escalation_brief)
