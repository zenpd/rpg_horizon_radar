"""Pytest fixtures.

Settings are read once, at import, so the test environment is fixed here
before anything from the app is imported: a throwaway SQLite database, the
scheduler off, and every external key blank (pydantic-settings lets real env
vars win over app/.env), so no test can reach a live API or spend a quota.
Tests that exercise a connector set its key on the settings object and pass an
``httpx.MockTransport``.

The app seeds no watched companies and only the first user, from
FIRST_USER_EMAIL / FIRST_USER_PASSWORD; ``seeded`` has that user add a second
one, the way a team would."""
from __future__ import annotations

import os
import pathlib
import tempfile

from tests.helpers import FIRST, FIRST_PASSWORD, PASSWORD, SECOND, login

_DB = pathlib.Path(tempfile.mkdtemp()) / "test.db"
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_DB.as_posix()}",
    "APP_ENV": "development",
    "SCHEDULER_ENABLED": "false",
    "TRACING_ENABLED": "false",
    "TEMPORAL_HOST": "127.0.0.1:1",  # unreachable: ingestion takes the inline path at once
    "FIRST_USER_EMAIL": FIRST,
    "FIRST_USER_PASSWORD": FIRST_PASSWORD,
})
for _key in ("GNEWS_API_KEY", "NEWSDATA_API_KEY", "TAVILY_API_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "FETCHLAYER_API_KEY",
             "YOUTUBE_API_KEY", "ALPHA_VANTAGE_API_KEY", "EPO_OPS_CONSUMER_KEY", "EPO_OPS_CONSUMER_SECRET", "FINCRUX_API_KEY",
             "GROQ_API_KEY", "NVIDIA_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY"):
    os.environ[_key] = ""
os.environ["NSE_ENABLED"] = "false"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_APP_DIR = pathlib.Path(__file__).resolve().parents[1]


def _migrate() -> None:
    cfg = Config(str(_APP_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_APP_DIR / "alembic"))
    command.upgrade(cfg, "head")


_migrate()

import db.base  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

# No pooled connections: tests run the app's event loop (TestClient) and their
# own (asyncio.run) side by side, and a pooled aiosqlite connection is tied to
# the loop that opened it.
db.base.engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
db.base.AsyncSessionLocal = async_sessionmaker(db.base.engine, expire_on_commit=False, class_=AsyncSession)

from api.main import app  # noqa: E402
from shared.config import get_settings  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def seeded() -> TestClient:
    """A client whose lifespan has run (subsidiaries and the first user seeded), with a second user
    added by the first."""
    with TestClient(app) as c:
        r = c.post("/api/v1/reviewers", headers=login(c, FIRST), json={"name": "Second User", "email": SECOND, "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
def settings(monkeypatch):
    """The live settings object; setattr through monkeypatch so each test's keys are undone."""
    s = get_settings()

    class _Set:
        def __setattr__(self, name, value):
            monkeypatch.setattr(s, name, value)

        def __getattr__(self, name):
            return getattr(s, name)

    return _Set()
