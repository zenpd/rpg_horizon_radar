"""FastAPI application entry point — RPG Horizon Radar.

Accelerator baseline: environment-scoped CORS, structured logging, Phoenix
tracing, and a session-oriented example router. Add routers under
api/routers/ and register them in the "Routers" block.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    audit,
    auth,
    digests,
    entities,
    example,
    health,
    ingest,
    reviewers,
    signals,
    subsidiaries,
)
from db.base import get_db_session
from db.seed import seed
from observability.tracing import init_tracing, instrument_fastapi
from shared.config import get_settings
from shared.logger import get_logger, setup_logging

log = get_logger("api.main")
settings = get_settings()

APP_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_tracing()
    # Schema is managed by Alembic — run `alembic upgrade head` before starting
    # (pre-deploy pipeline step or init container), not create_all() on startup.
    # Seeding is separate from schema creation: it only inserts demo rows into
    # tables Alembic already created, and is a no-op once seeded once.
    async with get_db_session() as db:
        await seed(db)
    log.info("api.startup", env=settings.app_env, version=APP_VERSION)
    yield
    log.info("api.shutdown")


app = FastAPI(
    title="RPG Horizon Radar API",
    description="M&A and competitive-intelligence signal-surfacing agent for RPG Corporate Strategy — flags public distress/opportunity signals to a named, restricted reviewer list.",
    version=APP_VERSION,
    lifespan=lifespan,
)
instrument_fastapi(app)

# ── CORS — wildcard is never used outside development ──────────────────────────
if settings.app_env == "development":
    _cors_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
else:
    _cors_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if not _cors_origins:
        raise RuntimeError(
            f"CORS_ALLOWED_ORIGINS must be set in app_env={settings.app_env!r}. "
            "Example: https://rpg-horizon-radar-fe.bravesky-d9f9eeb7.eastus2.azurecontainerapps.io"
        )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health.router, tags=["Health"])
# Kept as shipped — proves the accelerator spine (LangGraph + Redis session
# persistence) is intact. RPG Horizon Radar's own scoring is deliberately
# rule-based, not an LLM agent (see DESIGN.md §7/§14), so it doesn't use this.
app.include_router(example.router, prefix="/api/v1/example", tags=["Example"])

# ── RPG Horizon Radar routers ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(subsidiaries.router, prefix="/api/v1/subsidiaries", tags=["Subsidiaries"])
app.include_router(entities.router, prefix="/api/v1/entities", tags=["Entities"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(digests.router, prefix="/api/v1/digests", tags=["Digests"])
app.include_router(ingest.router, prefix="/api/v1/ingest", tags=["Ingest"])
app.include_router(reviewers.router, prefix="/api/v1/reviewers", tags=["Reviewers"])
app.include_router(audit.router, prefix="/api/v1/audit-log", tags=["Audit"])
