"""The scheduler's digest job: due()/next_runs() pacing, and an end-to-end
run that lands a real DigestIssue the Digest archive screen can read."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from services import scheduler

PASSWORD = "ChangeMe123!"


def login(client, email: str) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_due_includes_digest_on_first_run():
    now = datetime(2026, 10, 6, 12, 0)
    assert "digest" in scheduler.due(now, state={})


def test_due_skips_digest_before_interval_elapses():
    now = datetime(2026, 10, 6, 12, 0)
    state = {"digest": (now - timedelta(days=2)).isoformat(timespec="seconds")}
    assert "digest" not in scheduler.due(now, state)


def test_due_includes_digest_after_interval_elapses():
    now = datetime(2026, 10, 6, 12, 0)
    state = {"digest": (now - timedelta(days=8)).isoformat(timespec="seconds")}
    assert "digest" in scheduler.due(now, state)


def test_next_runs_reports_a_digest_slot():
    now = datetime(2026, 10, 6, 12, 0)
    out = scheduler.next_runs(now, state={})
    assert "digest" in out


def test_run_due_digest_creates_a_readable_issue(seeded):
    ran = asyncio.run(scheduler.run_due(now=datetime.now()))
    assert "digest" in ran

    headers = login(seeded, "compliance.admin@rpg-demo.local")
    r = seeded.get("/api/v1/digests", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) >= 1
