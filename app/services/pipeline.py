"""One entry point for an ingestion run, shared by the ingest router, the radar's
"Refresh live signals" and the scheduler. Primary path: IngestionWorkflow on
Temporal (durable, retried on transient failure). Fallback: if Temporal or the
worker isn't reachable — e.g. the API running alone without ``docker compose
up`` — run the same services.ingest code inline. Afterwards the radar screens
reload the live signals (radar/bridge.py), and research on an RPG company whose
last research had a failing source (e.g. Fincrux's daily quota) is retried
(services/company_research.py). SWOTs are rebuilt weekly by the scheduler, not
after each ingestion run."""
from __future__ import annotations

from temporalio.client import Client

from db.base import get_db_session
from services import company_research
from services.audit import write_audit
from services.ingest import run_ingest_all
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("services.pipeline")


async def _run_via_temporal() -> dict | None:
    s = get_settings()
    try:
        from workflows.ingestion_workflow import IngestionWorkflow

        client = await Client.connect(s.temporal_host, namespace=s.temporal_namespace)
        return await client.execute_workflow(
            IngestionWorkflow.run,
            id=f"ingestion-{s.temporal_namespace}",
            task_queue=s.temporal_task_queue_agents,
        )
    except Exception as exc:  # noqa: BLE001 — Temporal/worker unreachable is an expected local-dev case
        log.warning("temporal_ingest_unavailable_falling_back_inline", error=str(exc))
        return None


async def run_ingest(reviewer=None) -> dict:
    from radar import bridge  # imported here: radar.api imports this module

    result = await _run_via_temporal()
    via = "temporal"
    if result is None:
        async with get_db_session() as db:
            result = await run_ingest_all(db)
        via = "inline_fallback"
    result = {"errors": [], "changed_subsidiaries": [], **result, "via": via, "researched": []}
    try:
        async with get_db_session() as db:
            result["researched"] = await company_research.refresh_due(db)
    except Exception as exc:  # noqa: BLE001 — research failing must not fail the ingestion run
        log.warning("company_research_failed", error=str(exc))
        result["errors"].append(f"Company research: {exc}")

    async with get_db_session() as db:
        await write_audit(
            db, reviewer, "ingest_run", "raw_signal",
            detail=f"via={via} new_raw_signals={result['new_raw_signals']} clusters_updated={result['clusters_updated']} "
                   f"errors={len(result['errors'])}",
        )

    await bridge.sync()
    return result
