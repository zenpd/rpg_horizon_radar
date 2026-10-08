"""Rule-based distress/opportunity scoring. Deliberately auditable — every
number in the output can be traced back to this file's constants. No external
LLM call is made; the rationale string is built with a plain template so the
scoring path needs no API key and no model to run. (RPG Horizon Radar's
scoring is intentionally NOT an LLM agent — see DESIGN.md §7/§14. The app's
LLM agents live in agents/ and never produce a score.)"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

WINDOW_DAYS = 90

BASE_WEIGHTS: dict[str, int] = {
    "leadership_churn": 20,
    "delayed_filing": 25,
    "credit_downgrade": 30,
    "patent_shift": 15,
    "hiring_scaledown": 15,
    "hiring_scaleup": 10,
    "press_distress": 20,
    "press_opportunity": 15,
    # Added with the live connectors (ingestion/connectors/live/); each is
    # emitted only past the threshold its connector documents.
    "promoter_pledge": 25,     # NSE: >= 5% of promoter shares pledged
    "auditor_change": 25,      # NSE: auditor resignation/change
    "legal_action": 20,        # NSE/news: insolvency, default, litigation, regulator orders
    "earnings_decline": 20,    # Fincrux: net profit <= -15% or sales <= -10% YoY
    "stake_selldown": 15,      # Fincrux: promoters -0.5pt or FIIs -1.5pt in a quarter
    "share_price_slump": 15,   # Alpha Vantage: -20% over 30 trading days
    "deal_activity": 15,       # NSE/news: acquisition, merger, divestment
    "fund_raise": 10,          # NSE: allotment, QIP, NCDs, rights issue
    "balance_sheet_stress": 25,  # Fincrux: Altman Z below 1.81, debt over 2x equity, or interest cover under 1.5x
}

# Co-occurrence multiplier keyed by count of DISTINCT signal types present.
CO_OCCURRENCE_MULTIPLIER: dict[int, float] = {
    1: 1.0,
    2: 1.3,
    3: 1.6,
}
CO_OCCURRENCE_MULTIPLIER_4_PLUS = 2.0

MAX_SCORE = 100.0


def _multiplier_for(distinct_type_count: int) -> float:
    if distinct_type_count >= 4:
        return CO_OCCURRENCE_MULTIPLIER_4_PLUS
    return CO_OCCURRENCE_MULTIPLIER.get(distinct_type_count, 1.0)


def cluster_window(signals: Sequence) -> tuple[datetime, datetime]:
    """Rolling 90-day window ending at the newest observed_at across the given
    signals, so a score depends only on the signals, not on when it is computed."""
    now = max(s.observed_at for s in signals)
    return now - timedelta(days=WINDOW_DAYS), now


def signals_in_window(signals: Sequence, window_start: datetime, window_end: datetime) -> list:
    return [s for s in signals if window_start <= s.observed_at <= window_end]


def _humanize(signal_type: str) -> str:
    return signal_type.replace("_", " ")


def compute_score(
    signals: Sequence,
    entity_name: str,
    subsidiary_names: Sequence[str],
    sector_hint: str,
) -> tuple[float, str, list[str]]:
    """Given the RawSignal-like rows already narrowed to one 90-day window for
    one entity, return (score, rationale, contributing_types_sorted).

    `subsidiary_names` and `sector_hint` are used only to phrase the rationale
    string — they do not affect the numeric score.
    """
    distinct_types = sorted({s.signal_type for s in signals})
    base_sum = sum(BASE_WEIGHTS.get(t, 0) for t in distinct_types)
    multiplier = _multiplier_for(len(distinct_types))
    raw_score = base_sum * multiplier
    score = min(MAX_SCORE, raw_score)

    type_count = len(distinct_types)
    type_list_text = ", ".join(_humanize(t) for t in distinct_types) if distinct_types else "no signals"
    plural = "signal" if type_count == 1 else "signals"

    if subsidiary_names:
        routed_text = f" — routed to {', '.join(subsidiary_names)} ({sector_hint} relevance)."
    else:
        routed_text = " — no subsidiary currently matches this entity's sectors."

    rationale = (
        f"{entity_name} shows {type_count} concurrent {plural}: {type_list_text}. "
        f"Combined score {round(score)}/100{routed_text}"
    )

    return score, rationale, distinct_types
