"""FastAPI application entry point — RPG Horizon Radar.

Accelerator baseline: environment-scoped CORS, structured logging and Phoenix
tracing. Add routers under api/routers/ and register them in the "Routers"
block.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    audit,
    auth,
    digests,
    entities,
    health,
    ingest,
    jobs,
    reviewers,
    signals,
    subsidiaries,
    watchlist,
)
from db.base import get_db_session
from db.seed import seed
from radar import api as radar_api
from radar import bridge as radar_bridge
from radar.access import radar_access
from services import scheduler
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
    # Seeding is separate from schema creation: it only inserts the six RPG
    # subsidiaries and the first user (db/seed.py), and is a no-op once done.
    async with get_db_session() as db:
        await seed(db)
    # The radar screens: agent SWOTs from swot_briefs, live signals of watched companies.
    await radar_bridge.startup()
    # Daily live ingestion + weekly watchlist discovery (SCHEDULER_ENABLED).
    scheduler.start()
    log.info("api.startup", env=settings.app_env, version=APP_VERSION)
    yield
    await scheduler.stop()
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
        "http://localhost:5174",
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

# ── RPG Horizon Radar routers ────────────────────────────────────────────────
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(subsidiaries.router, prefix="/api/v1/subsidiaries", tags=["Subsidiaries"])
app.include_router(entities.router, prefix="/api/v1/entities", tags=["Entities"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["Signals"])
app.include_router(digests.router, prefix="/api/v1/digests", tags=["Digests"])
app.include_router(ingest.router, prefix="/api/v1/ingest", tags=["Ingest"])
app.include_router(reviewers.router, prefix="/api/v1/reviewers", tags=["Reviewers"])
app.include_router(audit.router, prefix="/api/v1/audit-log", tags=["Audit"])
app.include_router(watchlist.router, prefix="/api/v1/watchlist", tags=["Watchlist"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["Jobs"])
# The radar screens (SWOT home, deep-dive book, follow-up, explore, radar settings): every
# request needs a login and is recorded in the activity history.
app.include_router(radar_api.router, prefix="/api/v1/radar", tags=["Radar"], dependencies=[Depends(radar_access)])
