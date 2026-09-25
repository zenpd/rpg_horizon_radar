"""Central visibility rule shared by the signals/digests/entities routers, so
the gate+scope check is defined in exactly one place. Pure function — no DB
I/O, so it needs no async variant.

Rule: compliance_admin bypasses both the gate check and the subsidiary-scope
check (an admin must be able to preview gated-off sector data in order to
decide whether to open that gate). A corp_strategy_reviewer must satisfy BOTH:
the subsidiary's compliance_gate must be True, AND the subsidiary code must be
in the reviewer's subsidiary_scopes.
"""
from __future__ import annotations

from db.models import Reviewer, Subsidiary


def subsidiary_visible_to(reviewer: Reviewer, subsidiary: Subsidiary) -> bool:
    if reviewer.role == "compliance_admin":
        return True
    return bool(subsidiary.compliance_gate) and subsidiary.code in (reviewer.subsidiary_scopes or [])


def subsidiary_code_visible_to(reviewer: Reviewer, subsidiary_code: str, subsidiary_by_code: dict) -> bool:
    subsidiary = subsidiary_by_code.get(subsidiary_code)
    if subsidiary is None:
        return False
    return subsidiary_visible_to(reviewer, subsidiary)
