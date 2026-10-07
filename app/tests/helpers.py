"""Logins for the test world conftest.py sets up. Kept apart from conftest.py, which must only be
imported by pytest itself (importing it again would set up a second database)."""
from __future__ import annotations

FIRST = "first.user@test.local"
FIRST_PASSWORD = "test-first-password"
PASSWORD = "test-user-password"
SECOND = "second.user@test.local"


def login(c, email: str) -> dict:
    r = c.post("/api/v1/auth/login", json={"email": email, "password": FIRST_PASSWORD if email == FIRST else PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}
