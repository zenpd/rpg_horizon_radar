"""One entry point for an ingestion run, shared by the ingest router and the
scheduler. Primary path: IngestionWorkflow on Temporal (durable, retried on
transient failure). Fallback: if Temporal or the worker isn't reachable —
e.g. the API running alone without ``docker compose up`` — run the same
services.ingest code inline. Afterwards, SWOT briefs are rebuilt for the
subsidiaries whose signals changed (AUTO_SWOT)."""
from __future__ import annotations

from temporalio.client import Client

from db.base import get_db_session
from services import swot
from services.audit import write_audit
from services.ingest import run_ingest_for_open_subsidiaries
from shared.config import get_settings
from shared.llm_chat import LLMError
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


async def run_ingest(reviewer=None, rebuild_swots: bool | None = None) -> dict:
    result = await _run_via_temporal()
    via = "temporal"
    if result is None:
        async with get_db_session() as db:
            result = await run_ingest_for_open_subsidiaries(db)
        via = "inline_fallback"
    result = {"errors": [], "changed_subsidiaries": [], **result, "via": via, "swot_rebuilt": [], "swot_errors": []}

    async with get_db_session() as db:
        await write_audit(
            db, reviewer, "ingest_run", "raw_signal",
            detail=f"via={via} new_raw_signals={result['new_raw_signals']} clusters_updated={result['clusters_updated']} "
                   f"errors={len(result['errors'])}",
        )

    if rebuild_swots if rebuild_swots is not None else get_settings().auto_swot:
        for code in result["changed_subsidiaries"]:
            try:
                async with get_db_session() as db:
                    await swot.build(db, code, reviewer)
                result["swot_rebuilt"].append(code)
            except (swot.SwotError, LLMError) as e:
                result["swot_errors"].append(f"{code}: {e}")
    return result
