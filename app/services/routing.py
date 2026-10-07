"""Relevance-routing: sector/category overlap between a watched Entity and a
Subsidiary. Table-driven and explicit, not inferred per-request, so it stays
auditable and correctable without touching the scoring logic. Pure function —
no DB I/O, so it needs no async variant."""
from __future__ import annotations

from db.models import Entity, Subsidiary


def matching_subsidiaries(entity: Entity, subsidiaries: list[Subsidiary]) -> list[Subsidiary]:
    """Any sector overlap between entity.sectors and subsidiary.sectors = route."""
    entity_sectors = set(entity.sectors or [])
    if not entity_sectors:
        return []
    return [s for s in subsidiaries if entity_sectors & set(s.sectors or [])]
