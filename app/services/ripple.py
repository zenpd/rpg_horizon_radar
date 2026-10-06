"""Computes the "ripple effect" section of the Escalation Brief — see
DESIGN.md §14 and services/escalation_brief.py.

HARD RULE, same discipline as escalation_brief.py: every rationale this
module produces is templated from a literal SubsidiaryDependency row (see
db/models.py, seeded in db/seed.py) plus the candidate entity's own
name/category/sectors. It never calls an external LLM and never invents a
counterparty or a relationship that isn't already a row in that table — only
which of the acquirer's EXISTING, hand-curated dependencies look newly
relevant to THIS candidate. Pure function — no DB I/O, so it needs no async
variant."""
from __future__ import annotations

from db.models import Entity, Subsidiary, SubsidiaryDependency


def _haystack(entity: Entity) -> str:
    return " ".join([entity.name or "", entity.category or "", *(entity.sectors or [])]).lower()


def _rationale(acquirer: Subsidiary, entity: Entity, row: SubsidiaryDependency) -> str:
    category = entity.category or "unspecified sector"
    return (
        f"Acquiring {entity.name} ({category}) would extend {acquirer.name}'s demand on "
        f"{row.counterparty_name} — {row.description}"
    )


def compute_ripple_effects(dep_rows: list[SubsidiaryDependency], acquirer: Subsidiary, entity: Entity) -> list[dict]:
    """Every one of the acquirer's known dependency rows is a candidate ripple
    — any acquisition by a subsidiary is a candidate load on all of its
    existing supply/support fabric, not only the rows whose keywords match.
    Rows whose keywords DO match the candidate's name/category/sectors are
    tagged "direct"; the rest are "routine" context. Direct rows sort first."""
    haystack = _haystack(entity)
    out = []
    for row in dep_rows:
        relevance = "direct" if any(kw.lower() in haystack for kw in (row.keywords or [])) else "routine"
        out.append({
            "subsidiary_code": acquirer.code,
            "counterparty_name": row.counterparty_name,
            "counterparty_kind": row.counterparty_kind,
            "counterparty_subsidiary_code": row.counterparty_subsidiary_code,
            "dependency_type": row.dependency_type,
            "relevance": relevance,
            "rationale": _rationale(acquirer, entity, row),
        })
    out.sort(key=lambda r: r["relevance"] != "direct")
    return out


def compute_ripple_effects_for_subsidiaries(
    dep_rows_by_code: dict[str, list[SubsidiaryDependency]],
    routed_subsidiaries: list[Subsidiary],
    entity: Entity,
) -> list[dict]:
    """Convenience wrapper: ripple effects across every subsidiary a signal
    routed to, not just one."""
    out: list[dict] = []
    for sub in routed_subsidiaries:
        out.extend(compute_ripple_effects(dep_rows_by_code.get(sub.code, []), sub, entity))
    return out
