"""Post-acquisition SWOT projection — a qualitative, evidence-grounded DELTA
over a subsidiary's current baseline SWOT for one specific deal case, built
the moment a reviewer approves that case (radar/api.py:decide()).

HARD RULE, same discipline as services/escalation_brief.py: this module
never computes a new score, a valuation, or a synergy figure. Every item in
the projection is already-evidence-grounded content lifted straight out of
the baseline SWOT (swot_agent.py already tagged which O/T items and which
move are specifically about this case_id) — this is pure reclassification,
never new synthesis, so it needs no LLM call. The only new numbers it
produces are plain counts (how many items moved), never a percentage or a
fabricated index."""
from __future__ import annotations

from .store import STORE
from .views import swot_view


def project(co: str, case_id: str) -> dict | None:
    base = swot_view(co)

    secured = [item for item in base["O"] if item.get("case_id") == case_id]
    resolved = [item for item in base["T"] if item.get("case_id") == case_id]

    addressed = []
    move = STORE.rec_for_case(case_id)
    if move and move["co"] == co:
        for u in move["uses"]:
            if u.startswith("W"):
                idx = int(u[1:]) - 1
                if idx < len(base["W"]):
                    w_item = dict(base["W"][idx])
                    w_item["reasoning"] = move["why"]  # the move's own evidence-grounded rationale
                    addressed.append(w_item)

    if not secured and not resolved and not addressed:
        return None

    baseline_counts = {q: len(base[q]) for q in ("S", "W", "O", "T")}
    projected_counts = {
        "S": baseline_counts["S"],
        "W": baseline_counts["W"] - len(addressed),
        "O": baseline_counts["O"] - len(secured),
        "T": baseline_counts["T"] - len(resolved),
    }
    return {
        "company": co,
        "case_id": case_id,
        "secured": secured,
        "resolved": resolved,
        "addressed": addressed,
        "delta": {
            "secured_o": len(secured),
            "resolved_t": len(resolved),
            "addressed_w": len(addressed),
            "baseline": baseline_counts,
            "projected": projected_counts,
        },
    }
