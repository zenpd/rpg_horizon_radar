from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_reviewer
from api.dependencies import get_db
from api.schemas.signal import RawSignalOut, SignalClusterDetail, SignalClusterSummary
from db.models import RawSignal, Reviewer, SignalCluster, Subsidiary
from services.audit import write_audit

router = APIRouter()


async def _subsidiary_map(db: AsyncSession) -> dict[str, Subsidiary]:
    result = await db.execute(select(Subsidiary))
    return {s.code: s for s in result.scalars().all()}


def _build_summary(cluster: SignalCluster) -> SignalClusterSummary:
    score_row = cluster.opportunity_score
    return SignalClusterSummary(
        id=cluster.id,
        entity_name=cluster.entity.name,
        entity_sectors=cluster.entity.sectors or [],
        subsidiaries=[link.subsidiary_code for link in cluster.subsidiary_links],
        score=score_row.score if score_row else 0.0,
        rationale=score_row.rationale if score_row else "",
        signal_types=score_row.signal_types_json if score_row else [],
        status=cluster.status,
        updated_at=cluster.updated_at,
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
    query = select(SignalCluster)
    if status:
        query = query.where(SignalCluster.status == status)
    query = query.order_by(SignalCluster.updated_at.desc())
    clusters = (await db.execute(query)).scalars().all()

    if subsidiary:
        clusters = [c for c in clusters if any(link.subsidiary_code == subsidiary for link in c.subsidiary_links)]

    await write_audit(
        db, reviewer, "view_signal_list", "signal_cluster",
        detail=f"subsidiary={subsidiary} status={status}",
    )

    return [_build_summary(c) for c in clusters]


@router.get("/{cluster_id}", response_model=SignalClusterDetail)
async def get_signal(
    cluster_id: int,
    reviewer: Reviewer = Depends(get_current_reviewer),
    db: AsyncSession = Depends(get_db),
):
    cluster = (await db.execute(select(SignalCluster).where(SignalCluster.id == cluster_id))).scalar_one_or_none()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Signal cluster not found")

    await write_audit(db, reviewer, "view_signal", "signal_cluster", resource_id=cluster_id)

    windowed_raw = await _windowed_raw_signals(db, cluster)
    summary = _build_summary(cluster)
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
