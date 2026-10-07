"""OpenTelemetry + Arize Phoenix tracing initialisation.

Cloud Phoenix (ACA-hosted):
- Collector endpoint via PHOENIX_COLLECTOR_ENDPOINT
  (e.g. https://zaf-phoenix.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io/v1/traces)
- Auth: Bearer token from ARIZE_PHOENIX_API_KEY

Local fallback: http://<phoenix_host>:<phoenix_port>/v1/traces (no auth).

Uses the OTLP/HTTP exporter + openinference instrumentors so LangChain /
LangGraph / OpenAI calls appear as proper spans in Phoenix. All imports are
lazy so a missing observability package never blocks app startup.
"""
from __future__ import annotations

import logging
import socket
from urllib.parse import urlparse

from shared.config import get_settings

log = logging.getLogger("tracing")

_INITIALISED = False
_PROBE_TIMEOUT = 0.3  # seconds — local/LAN only; a real ACA collector is checked over TLS anyway


def _collector_reachable(endpoint: str) -> bool:
    """A quick TCP probe so a missing local Phoenix (common in dev and every test run) skips
    exporter setup entirely, instead of configuring a BatchSpanProcessor that retries forever in
    the background and logs a connection failure on every export interval."""
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if not host:
            return False
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def init_tracing(service_name: str = "rpg-horizon-radar-backend") -> None:
    """Configure the OTel TracerProvider and instrument FastAPI + LangChain + OpenAI.

    ``service_name`` identifies which process emitted a span (the FastAPI API
    vs. the Temporal worker) — both write to the same Phoenix project, but this
    lets you tell the two execution paths apart in a trace.
    """
    global _INITIALISED
    if _INITIALISED:
        return

    settings = get_settings()
    if not settings.tracing_enabled:
        log.info("tracing disabled (TRACING_ENABLED=false)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        if settings.phoenix_collector_endpoint:
            endpoint = settings.phoenix_collector_endpoint.rstrip("/")
            if not endpoint.endswith("/v1/traces"):
                endpoint = f"{endpoint}/v1/traces"
        else:
            endpoint = f"http://{settings.phoenix_host}:{settings.phoenix_port}/v1/traces"

        if not _collector_reachable(endpoint):
            log.info("tracing collector unreachable at %s — skipping (no retries, no noisy export errors)", endpoint)
            return

        headers = {}
        if settings.arize_phoenix_api_key:
            headers["Authorization"] = f"Bearer {settings.arize_phoenix_api_key}"

        provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "openinference.project.name": settings.phoenix_project_name,
                }
            )
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers))
        )
        trace.set_tracer_provider(provider)

        # ── Instrumentors (each optional) ──────────────────────────────────────
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor

            OpenAIInstrumentor().instrument(tracer_provider=provider)
            log.info("OpenAI instrumented (openinference)")
        except Exception as exc:  # noqa: BLE001
            log.warning("openai instrumentation skipped: %s", exc)

        log.info("OTel TracerProvider initialised -> %s (project: %s)",
                 endpoint, settings.phoenix_project_name)
        _INITIALISED = True
    except Exception as exc:  # noqa: BLE001
        log.warning("init_tracing failed (continuing without tracing): %s", exc)


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI app instance (call after app creation)."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        log.info("FastAPI instrumented")
    except Exception as exc:  # noqa: BLE001
        log.warning("fastapi instrumentation skipped: %s", exc)
