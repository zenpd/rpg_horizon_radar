"""Generates the Escalation Brief — see DESIGN.md §14.

HARD RULE: every string this module produces is templated from data already in
the system (signal types, sector overlap, entity metadata). It never computes
or displays a valuation, price, multiple, or synergy dollar figure, and it
never calls an external LLM. That is a deliberate boundary, not an
implementation shortcut — public-signal data (even the quarterly figures the
Fincrux connector reads) is no basis for a valuation, and fabricating numbers
here would be actively misleading to whoever reads it. Pure function — no DB
I/O, so it needs no async variant."""
from __future__ import annotations

from datetime import datetime

from db.models import Entity, EscalationBrief, OpportunityScore, Reviewer, SignalCluster, Subsidiary

DISCLAIMER = (
    "Generated from public-signal pattern-matching only. Contains no financial "
    "valuation and no confirmed non-public information. Not a recommendation to "
    "proceed — a set of directional prompts for the formal M&A process."
)

DISTRESS_TYPES = {
    "leadership_churn", "delayed_filing", "credit_downgrade", "press_distress", "hiring_scaledown",
    "promoter_pledge", "auditor_change", "legal_action", "earnings_decline", "stake_selldown", "share_price_slump",
}
OPPORTUNITY_TYPES = {"press_opportunity", "hiring_scaleup", "deal_activity", "fund_raise"}
PATENT_TYPES = {"patent_shift"}


def _deal_complexity(entity: Entity, distinct_type_count: int) -> str:
    sector_count = len(entity.sectors or [])
    if distinct_type_count >= 4 or sector_count >= 3:
        return "High"
    if distinct_type_count >= 2 or sector_count >= 2:
        return "Medium"
    return "Low"


def _build_pros(distinct_types: set[str], routed_subsidiaries: list[Subsidiary]) -> list[str]:
    pros: list[str] = []
    if distinct_types & DISTRESS_TYPES:
        pros.append(
            "Possible distress-driven opening — the target may be more receptive to acquisition "
            "or partnership conversations than under normal conditions."
        )
    if distinct_types & PATENT_TYPES:
        pros.append(
            "Patent-activity shift suggests a capability gap or strategic pivot at the target — "
            "worth understanding before a competitor moves first."
        )
    if distinct_types & OPPORTUNITY_TYPES:
        pros.append(
            "Signals point to genuine momentum (hiring/press), not distress — this may be a "
            "growth-stage capability worth engaging with early, on partnership or acquisition terms."
        )
    if routed_subsidiaries:
        names = ", ".join(s.name for s in routed_subsidiaries)
        pros.append(
            f"Sector overlap with {names} suggests a plausible strategic fit without requiring a "
            "new capability build from scratch."
        )
    pros.append(
        "Surfaced via public sources ahead of broad market awareness — a head start versus "
        "waiting for an external advisor to bring the opportunity in."
    )
    return pros


def _build_cons(distinct_types: set[str], routed_subsidiaries: list[Subsidiary]) -> list[str]:
    cons: list[str] = [
        "Unconfirmed by primary diligence — these are public-pattern signals, not verified "
        "financials or management commentary.",
        "No confirmed intent to sell or partner — premature outreach risks signaling interest to "
        "the market before a formal process is ready.",
    ]
    if len(distinct_types) <= 2:
        cons.append(
            f"Only {len(distinct_types)} concurrent signal type(s) detected — single/dual-signal "
            "flags carry a materially higher false-positive rate than multi-signal ones; treat as "
            "an early lead, not a validated finding."
        )
    if routed_subsidiaries:
        names = ", ".join(s.name for s in routed_subsidiaries)
        cons.append(
            f"Sector overlap with {names} means regulatory/anti-trust exposure should be checked "
            "before any approach."
        )
    return cons


def _build_directional_considerations(
    entity: Entity, distinct_types: set[str], routed_subsidiaries: list[Subsidiary], complexity: str
) -> list[dict]:
    has_overlap = bool(routed_subsidiaries)
    synergy_value = (
        "Heuristic yes — sector tags overlap with the routed subsidiary(ies); not a quantified estimate."
        if has_overlap
        else "Not assessed — no routed subsidiary sector overlap yet confirmed."
    )
    return [
        {"label": "Deal complexity (heuristic)", "value": complexity},
        {"label": "Revenue-synergy potential (heuristic)", "value": synergy_value},
        {"label": "Cost-synergy potential (heuristic)", "value": synergy_value},
        {
            "label": "Suggested first formal-process step",
            "value": "Route to Corporate Development's standard preliminary diligence intake before any external contact.",
        },
    ]


def generate_escalation_brief(
    cluster: SignalCluster,
    score_row: OpportunityScore,
    entity: Entity,
    routed_subsidiaries: list[Subsidiary],
    escalated_by: Reviewer,
) -> EscalationBrief:
    distinct_types = set(score_row.signal_types_json or [])
    complexity = _deal_complexity(entity, len(distinct_types))

    return EscalationBrief(
        cluster_id=cluster.id,
        generated_at=datetime.utcnow(),
        escalated_by_id=escalated_by.id if escalated_by else None,
        pros=_build_pros(distinct_types, routed_subsidiaries),
        cons=_build_cons(distinct_types, routed_subsidiaries),
        directional_considerations=_build_directional_considerations(
            entity, distinct_types, routed_subsidiaries, complexity
        ),
        deal_complexity=complexity,
        disclaimer=DISCLAIMER,
    )
