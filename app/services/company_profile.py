"""Generates the Company Profile — a qualitative, directional read on the
signal's target company, for an exec deciding where to look next. See
services/escalation_brief.py for the sibling module this mirrors.

HARD RULE, same boundary as the Escalation Brief: every string here is
templated from data already in the system (entity listing status, sector
overlap, signal-type classification). It never computes or displays a stock
price, percentage move, valuation, or confirmed deal term, and never calls
an external LLM. Unlike the Escalation Brief, a Company Profile is available
for ANY visible signal (live or under_evaluation) — there's no formal
hand-off gate on just understanding who the target is.

Pure function — no DB I/O, so it needs no async variant."""
from __future__ import annotations

from db.models import Entity, Subsidiary
from services.escalation_brief import DISTRESS_TYPES, OPPORTUNITY_TYPES, PATENT_TYPES

DISCLAIMER = (
    "Directional reading only, derived from public-signal pattern-matching and sector "
    "overlap — not a stock-price forecast, valuation, or confirmed deal term."
)


def _listing_status(entity: Entity) -> dict:
    if entity.nse_symbol:
        return {
            "status": "public",
            "label": f"Publicly listed (NSE: {entity.nse_symbol})",
            "detail": "Has its own traded price — any market reaction to a deal would show up there first, independent of RPG's own stock.",
        }
    return {
        "status": "private",
        "label": "Privately held — no public listing on record",
        "detail": "No independent market price exists for this target; a valuation would need private financial disclosure this system does not have.",
    }


def _market_reaction(distinct_types: set[str], routed_subsidiaries: list[Subsidiary]) -> str:
    overlap = bool(routed_subsidiaries)
    distressed = bool(distinct_types & DISTRESS_TYPES)
    growth = bool(distinct_types & OPPORTUNITY_TYPES)
    sub_names = ", ".join(s.name for s in routed_subsidiaries) if routed_subsidiaries else None

    if distressed and overlap:
        return (
            f"If this became public, the more likely reading is mildly favorable for {sub_names}'s own stock — "
            "a distressed, sector-overlapping target is usually seen as disciplined bargain-buying rather than overpaying. "
            "Not a prediction, just the more common pattern for this combination."
        )
    if distressed and not overlap:
        return (
            "Distress signals with no sector overlap to an RPG subsidiary are harder for the market to read favorably — "
            "likely to draw questions about strategic rationale before any reaction settles either way."
        )
    if growth and overlap:
        return (
            f"Acquiring sector-overlapping momentum can cut either way for {sub_names}'s stock — strategic logic is clear, "
            "but paying up for a growth asset usually invites scrutiny on terms and integration execution."
        )
    if growth:
        return (
            "Growth-stage signals outside RPG's current sector overlap tend to be read as diversification — "
            "more likely scrutiny on fit and price discipline than a clear positive or negative reaction."
        )
    return "Not enough signal classification yet to characterize a likely market reaction either way."


def _integration_stance(distinct_types: set[str], routed_subsidiaries: list[Subsidiary]) -> str:
    overlap = bool(routed_subsidiaries)
    distressed = bool(distinct_types & DISTRESS_TYPES)
    growth = bool(distinct_types & OPPORTUNITY_TYPES)
    sub_names = ", ".join(s.name for s in routed_subsidiaries) if routed_subsidiaries else None

    if overlap and distressed:
        return (
            f"Full integration into {sub_names} is the more typical path here — absorbing a distressed, operationally "
            "overlapping business usually only pays off once duplicate costs are cut and operations are stabilized under one roof."
        )
    if overlap and growth:
        return (
            f"Could go either way, staged more than immediate — folding a growing, overlapping business straight into "
            f"{sub_names} risks disrupting the momentum that made it attractive; a transitional period under its own "
            "brand before integration is the more common pattern."
        )
    if not overlap and growth:
        return (
            "Running it autonomously under its own brand is the more likely fit — little operational overlap with an "
            "RPG subsidiary means the value is in the standalone brand or capability, not in merging operations."
        )
    return (
        "Unclear strategic fit from the signals alone — no sector overlap and no clear growth story makes this a "
        "harder case for either an integration or a standalone-brand thesis; worth confirming the underlying rationale first."
    )


def _deal_structure_hint(distinct_types: set[str], routed_subsidiaries: list[Subsidiary]) -> str:
    overlap = bool(routed_subsidiaries)
    distressed = bool(distinct_types & DISTRESS_TYPES)
    growth = bool(distinct_types & OPPORTUNITY_TYPES)

    if distinct_types & PATENT_TYPES:
        return (
            "A technology/IP-focused signal more often points toward a narrower asset, licensing, or acqui-hire "
            "structure than a full-company acquisition — worth checking what's actually for sale before assuming a full deal."
        )
    if distressed and len(distinct_types) >= 3:
        return (
            "Majority-stake or full acquisition is the more typical structure for a distressed, multi-signal situation — "
            "a minority stake usually wouldn't give enough control to drive a turnaround."
        )
    if growth and not overlap:
        return (
            "A minority or strategic-stake structure is more common when buying into growth outside the core sector — "
            "it preserves the target's independence while RPG gains exposure and a closer look before going further."
        )
    return "No strong structural signal yet — this would depend on diligence findings not available from public signals."


def _regulatory_note(routed_subsidiaries: list[Subsidiary]) -> str:
    if routed_subsidiaries:
        names = ", ".join(s.name for s in routed_subsidiaries)
        return f"Sector overlap with {names} means a competition/anti-trust screen is worth running before any approach — not yet assessed here."
    return "No sector overlap with a routed RPG subsidiary detected — competition/anti-trust exposure looks limited, but hasn't been formally screened."


def build_company_profile(entity: Entity, distinct_types: set[str], routed_subsidiaries: list[Subsidiary]) -> dict:
    listing = _listing_status(entity)
    return {
        "listing_status": listing["status"],
        "listing_label": listing["label"],
        "listing_detail": listing["detail"],
        "market_reaction": _market_reaction(distinct_types, routed_subsidiaries),
        "integration_stance": _integration_stance(distinct_types, routed_subsidiaries),
        "deal_structure_hint": _deal_structure_hint(distinct_types, routed_subsidiaries),
        "regulatory_note": _regulatory_note(routed_subsidiaries),
        "disclaimer": DISCLAIMER,
    }
