"""First-start setup. Seeds only what the app cannot run without:

- The six RPG subsidiaries — the internal routing targets / audience of this
  tool, never watched entities themselves.
- The first user, from FIRST_USER_EMAIL / FIRST_USER_PASSWORD (or
  FIRST_USER_PASSWORD_KV_URI), only when nobody can sign in (no users yet, or
  only the demo logins migration 0004 disabled). That user adds the others.
  With the settings blank nobody is created, so no default login ever exists.

No watched company is seeded: real companies enter through the watchlist
(discovery or a manual add) — see DESIGN.md §15. Idempotent: each part is a
no-op once done."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import hash_password
from db.models import Reviewer, Subsidiary
from shared.config import get_settings
from shared.logger import get_logger

log = get_logger("db.seed")

SUBSIDIARIES = [
    dict(
        code="CEAT",
        name="CEAT",
        sectors=["tyres", "mobility"],
        signal_focus="Distressed component suppliers, adjacent mobility/tyre-tech players, regional manufacturing consolidation.",
    ),
    dict(
        code="KEC",
        name="KEC International",
        sectors=["epc", "materials-adjacent"],
        signal_focus="Competitor project distress, adjacent EPC/materials capability gaps, overseas market entry openings.",
    ),
    dict(
        code="ZENSAR",
        name="Zensar",
        sectors=["it-services", "ai-genai", "bfsi-services"],
        signal_focus="Niche AI/GenAI capability acquisitions, smaller BFSI-focused service providers under pressure.",
    ),
    dict(
        code="RPGLS",
        name="RPG Life Sciences",
        sectors=["pharma", "api-manufacturing"],
        signal_focus="Smaller pharma/API manufacturers with regulatory or capital distress signals.",
    ),
    dict(
        code="RAYCHEM",
        name="Raychem RPG",
        sectors=["materials-engineering", "electrical-components"],
        signal_focus="Adjacent materials-engineering or electrical-components players showing consolidation potential.",
    ),
    dict(
        code="HARRISONS",
        name="Harrisons Malayalam",
        sectors=["plantations", "agri-processing"],
        signal_focus="Regional plantation or agri-processing assets showing distress or succession-driven sale signals.",
    ),
]


async def seed(db: AsyncSession) -> None:
    if not (await db.execute(select(func.count()).select_from(Subsidiary))).scalar_one():
        for row in SUBSIDIARIES:
            db.add(Subsidiary(**row))
        log.info("db_seeded_subsidiaries")

    s = get_settings()
    # Disabled hashes (migration 0004's demo logins) start with "!", so they don't count.
    usable = select(func.count()).select_from(Reviewer).where(~Reviewer.password_hash.startswith("!"))
    email = s.first_user_email.strip()
    taken = email and (await db.execute(select(func.count()).select_from(Reviewer).where(Reviewer.email == email))).scalar_one()
    if not (await db.execute(usable)).scalar_one() and not taken:
        if email and s.first_user_password:
            db.add(Reviewer(name=s.first_user_name, email=email, password_hash=hash_password(s.first_user_password),
                            created_at=datetime.utcnow()))
            log.info("db_seeded_first_user", email=email)
        else:
            log.warning("no_users", hint="Set FIRST_USER_EMAIL and FIRST_USER_PASSWORD to create the first user.")

    await db.commit()
