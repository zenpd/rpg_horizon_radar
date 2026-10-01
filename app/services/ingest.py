"""Ingestion + clustering orchestration. Both db/seed.py and the ingestion
Temporal activity (workflows/activities.py) call these same functions — there
is exactly one code path that turns RawSignal rows into SignalCluster +
OpportunityScore + ClusterSubsidiaryLink rows, so the two never drift apart.

Fictional seed entities are served by the mock connectors. Real entities
(``is_fictional=False``) are served by the live connectors in
ingestion/connectors/live/, and only while ``status == "watching"`` — i.e.
after a compliance_admin approved them — and their sector's gate is open.
Live calls are blocking HTTP, so they run in a worker thread
(``asyncio.to_thread``); their pacing, budgets and snapshots persist in the
``live`` ConnectorState row between runs."""
from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ClusterSubsidiaryLink, Entity, OpportunityScore, RawSignal, SignalCluster, Subsidiary
from ingestion.connectors.base import Connector
from ingestion.connectors.live import SourceError, live_connectors, resolve_nse_symbol
from ingestion.connectors.mock_filings import MockFilingsConnector
from ingestion.connectors.mock_hiring import MockHiringConnector
from ingestion.connectors.mock_news import MockNewsConnector
from ingestion.connectors.mock_patents import MockPatentsConnector
from services import routing, scoring
from services import state as state_store
from shared.config import get_settings

# "Beginning of time" for this demo — connectors are deterministic/hard-coded,
# so we always ask for everything and rely on the dedupe check below to keep
# re-runs idempotent, rather than tracking a real incremental cursor.
DEFAULT_SINCE = datetime(2000, 1, 1)
SYMBOL_RETRY_DAYS = 7  # a failed NSE-symbol lookup is retried weekly

CONNECTORS: list[Connector] = [
    MockNewsConnector(),
    MockFilingsConnector(),
    MockPatentsConnector(),
    MockHiringConnector(),
]

# One ingestion run at a time per process (the scheduler and an admin click can overlap).
RUN_LOCK = asyncio.Lock()


def collect_live(entity: Entity, state: dict, transport: httpx.BaseTransport | None = None) -> tuple[list[dict], list[str], str | None]:
    """Blocking: every configured live connector for one real entity, honouring
    each connector's pacing. Returns (records, errors, newly resolved NSE symbol).
    One failing connector never stops the others."""
    errors: list[str] = []
    key = str(entity.id)
    resolved = None
    if not entity.nse_symbol:
        missed = state.setdefault("symbol_misses", {}).get(key)
        if not missed or (datetime.now() - datetime.fromisoformat(missed)).days >= SYMBOL_RETRY_DAYS:
            resolved = resolve_nse_symbol(entity, state, transport)
            if resolved:
                state["symbol_misses"].pop(key, None)
                # a plain attribute set (no I/O); the caller's session saves it after this thread returns
                entity.nse_symbol = resolved
            else:
                state["symbol_misses"][key] = datetime.now().isoformat(timespec="seconds")
    records: list[dict] = []
    for src in live_connectors(state, transport):
        if not src.configured:
            continue
        query = src.query(entity)
        if not query:
            continue
        pulled = state.setdefault("pulled", {}).setdefault(src.name, {})
        last = pulled.get(key)
        if last and last.get("query") == query and (datetime.now() - datetime.fromisoformat(last["at"])).days < src.min_days:
            continue  # paced: the last pull still stands
        try:
            got = src.pull(entity, query)
        except (SourceError, httpx.HTTPError, KeyError, ValueError) as ex:
            errors.append(f"{src.name} · {entity.name}: {ex}")
            continue
        pulled[key] = {"at": datetime.now().isoformat(timespec="seconds"), "query": query, "signals": len(got)}
        records.extend(got)
    return records, errors, resolved


async def fetch_and_store_raw_signals(
    db: AsyncSession, entity: Entity, state: dict | None = None,
    transport: httpx.BaseTransport | None = None, errors: list[str] | None = None,
) -> int:
    """Fetch one entity's signals — the 4 mock connectors for a fictional
    entity, the live connectors for a real one (``state`` required) — and
    insert new RawSignal rows. Skips exact duplicates on (entity_id,
    signal_type, headline, observed_at) so this is safely re-runnable.
    Returns the count of newly inserted rows; live errors go to ``errors``."""
    if entity.is_fictional:
        records = [rec for connector in CONNECTORS for rec in connector.fetch(entity, DEFAULT_SINCE)]
    else:
        if state is None or not get_settings().live_connectors_enabled:
            return 0
        records, errs, _ = await asyncio.to_thread(collect_live, entity, state, transport)
        if errors is not None:
            errors.extend(errs)

    result = await db.execute(select(RawSignal).where(RawSignal.entity_id == entity.id))
    existing_keys = {(r.signal_type, r.headline, r.observed_at) for r in result.scalars().all()}

    new_count = 0
    now = datetime.utcnow()
    for record in records:
        key = (record["signal_type"], record["headline"], record["observed_at"])
        if key in existing_keys:
            continue
        db.add(
            RawSignal(
                entity_id=entity.id,
                signal_type=record["signal_type"],
                source_type=record["source_type"],
                headline=record["headline"],
                source_excerpt=record.get("source_excerpt", ""),
                source_url=record.get("source_url") or "",
                provider=record.get("provider", "mock"),
                observed_at=record["observed_at"],
                created_at=now,
            )
        )
        existing_keys.add(key)
        new_count += 1

    if new_count:
        await db.flush()
    return new_count


async def recompute_cluster_for_entity(
    db: AsyncSession, entity: Entity, all_subsidiaries: list[Subsidiary]
) -> SignalCluster | None:
    """Rebuild the rolling-90-day-window cluster, score, and routing links for
    one entity from its current RawSignal rows. Returns the SignalCluster, or
    None if the entity has no signals yet. A cluster already marked
    under_evaluation is frozen — the tool's involvement in it is over, per the
    design doc's one-way hand-off rule — so it is left untouched here."""
    result = await db.execute(select(RawSignal).where(RawSignal.entity_id == entity.id))
    signals = result.scalars().all()
    if not signals:
        return None

    result = await db.execute(select(SignalCluster).where(SignalCluster.entity_id == entity.id))
    cluster = result.scalar_one_or_none()
    if cluster is not None and cluster.status == "under_evaluation":
        return cluster

    window_start, window_end = scoring.cluster_window(signals)
    windowed = scoring.signals_in_window(signals, window_start, window_end)

    routed_subsidiaries = routing.matching_subsidiaries(entity, all_subsidiaries)
    sector_hint = "/".join(entity.sectors or []) or "unclassified"

    score, rationale, contributing_types = scoring.compute_score(
        windowed,
        entity_name=entity.name,
        subsidiary_names=[s.name for s in routed_subsidiaries],
        sector_hint=sector_hint,
    )

    now = datetime.utcnow()
    if cluster is None:
        cluster = SignalCluster(
            entity_id=entity.id,
            window_start=window_start,
            window_end=window_end,
            status="live",
            created_at=now,
            updated_at=now,
        )
        db.add(cluster)
        await db.flush()
    else:
        cluster.window_start = window_start
        cluster.window_end = window_end
        cluster.updated_at = now

    # Query directly rather than touch cluster.opportunity_score: a cluster we
    # just constructed and flushed above was never loaded via a `select()`, so
    # its relationship attributes aren't populated — even with `lazy="selectin"`,
    # that strategy only fires as part of a query, not on an ad hoc attribute
    # touch, and AsyncSession has no implicit fallback lazy-load (MissingGreenlet).
    existing_score = (
        await db.execute(select(OpportunityScore).where(OpportunityScore.cluster_id == cluster.id))
    ).scalar_one_or_none()
    if existing_score is not None:
        await db.delete(existing_score)
        await db.flush()

    db.add(
        OpportunityScore(
            cluster_id=cluster.id,
            score=score,
            signal_types_json=contributing_types,
            rationale=rationale,
            computed_at=now,
        )
    )

    # Rebuild routing links from scratch — cheap and keeps them exactly in
    # sync with the current sector-overlap computation.
    await db.execute(delete(ClusterSubsidiaryLink).where(ClusterSubsidiaryLink.cluster_id == cluster.id))
    for sub in routed_subsidiaries:
        db.add(ClusterSubsidiaryLink(cluster_id=cluster.id, subsidiary_code=sub.code))

    await db.flush()
    return cluster


async def run_ingest_for_open_subsidiaries(db: AsyncSession, transport: httpx.BaseTransport | None = None) -> dict:
    """The ingest-run implementation: only subsidiaries with
    compliance_gate=True get their sectors' entities ingested — a closed gate
    blocks ingestion itself, not just display. Only ``watching`` entities are
    ingested; proposed or dismissed ones are never fetched."""
    async with RUN_LOCK:
        all_subsidiaries = (await db.execute(select(Subsidiary))).scalars().all()
        open_subsidiaries = [s for s in all_subsidiaries if s.compliance_gate]

        all_entities = (await db.execute(select(Entity).where(Entity.status == "watching"))).scalars().all()
        live_state = await state_store.load(db, "live")

        touched_entity_ids: set[int] = set()
        new_by_entity: dict[int, int] = {}
        errors: list[str] = []

        for sub in open_subsidiaries:
            sub_sectors = set(sub.sectors or [])
            entities = [e for e in all_entities if sub_sectors & set(e.sectors or [])]
            for entity in entities:
                if entity.id not in touched_entity_ids:
                    new_by_entity[entity.id] = await fetch_and_store_raw_signals(db, entity, live_state, transport, errors)
                    touched_entity_ids.add(entity.id)
                    if not entity.is_fictional:
                        # keep budgets and pulls even if a later entity fails
                        await state_store.save(db, "live", live_state)
                        await db.commit()

        entities_by_id = {e.id: e for e in all_entities}
        clusters_updated = 0
        changed_subsidiaries: set[str] = set()
        for entity_id in touched_entity_ids:
            cluster = await recompute_cluster_for_entity(db, entities_by_id[entity_id], all_subsidiaries)
            if cluster is not None:
                clusters_updated += 1
                if new_by_entity.get(entity_id):
                    changed_subsidiaries |= {s.code for s in routing.matching_subsidiaries(entities_by_id[entity_id], open_subsidiaries)}

        live_state["last_run"] = {"at": datetime.now().isoformat(timespec="seconds"), "errors": errors[-50:],
                                  "new_raw_signals": sum(new_by_entity.values())}
        await state_store.save(db, "live", live_state)
        await db.commit()
        return {"new_raw_signals": sum(new_by_entity.values()), "clusters_updated": clusters_updated,
                "errors": errors, "changed_subsidiaries": sorted(changed_subsidiaries)}
