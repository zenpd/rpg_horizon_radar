"""Weekly digest compiler. Selects live SignalCluster rows above
DIGEST_THRESHOLD for each gated-open subsidiary and snapshots them into a new
DigestIssue/DigestItem set."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClusterSubsidiaryLink, DigestIssue, DigestItem, Reviewer, SignalCluster, Subsidiary
from shared.config import get_settings

settings = get_settings()
DIGEST_THRESHOLD = settings.digest_threshold


async def generate_digest(db: AsyncSession, created_by: Reviewer | None) -> DigestIssue:
    now = datetime.utcnow()
    period_start = now - timedelta(days=7)

    digest = DigestIssue(
        period_start=period_start,
        period_end=now,
        created_at=now,
        created_by_id=created_by.id if created_by else None,
    )
    db.add(digest)
    await db.flush()

    open_subsidiaries = (
        (await db.execute(select(Subsidiary).where(Subsidiary.compliance_gate.is_(True)))).scalars().all()
    )

    for sub in open_subsidiaries:
        links = (
            (await db.execute(select(ClusterSubsidiaryLink).where(ClusterSubsidiaryLink.subsidiary_code == sub.code)))
            .scalars()
            .all()
        )
        for link in links:
            cluster: SignalCluster = link.cluster
            if cluster is None or cluster.status != "live":
                continue
            score_row = cluster.opportunity_score
            if score_row is None or score_row.score < DIGEST_THRESHOLD:
                continue
            db.add(
                DigestItem(
                    digest_id=digest.id,
                    cluster_id=cluster.id,
                    subsidiary_code=sub.code,
                )
            )

    await db.commit()
    await db.refresh(digest)
    return digest
