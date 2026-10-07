"""RPG Horizon Radar's own Temporal workflow — durable signal ingestion.

This is the accelerator's Temporal durability pattern (see BOOTSTRAP_GUIDE.md
"Durability with Temporal") applied to the thing Horizon Radar actually needs
it for: the scheduled ingestion pipeline. It has no LLM step at all — RPG
Horizon Radar's scoring is deliberately rule-based and auditable (see
DESIGN.md §7/§14).
"""
from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from workflows.activities import run_ingestion_activity

_RETRY = RetryPolicy(maximum_attempts=3, backoff_coefficient=2.0)


@workflow.defn
class IngestionWorkflow:
    @workflow.run
    async def run(self) -> dict:
        return await workflow.execute_activity(
            run_ingestion_activity,
            # Live connectors are paced (one call a second for NSE, GNews,
            # Alpha Vantage), so a full run takes minutes, not seconds.
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=_RETRY,
        )
