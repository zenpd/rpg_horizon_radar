from datetime import datetime

from db.models import Entity
from ingestion.connectors.base import Connector

# DEMO/SYNTHETIC DATA — see db/seed.py header. All entity names below are
# fictional and keyed by name for deterministic, reproducible fetches.
NEWS_DATA: dict[str, list[dict]] = {
    "Meridian Treadworks Pvt Ltd": [
        dict(
            signal_type="leadership_churn",
            headline="Meridian Treadworks loses CFO and VP Operations within the same quarter",
            source_excerpt=(
                "Two senior executives at Meridian Treadworks Pvt Ltd have departed in quick "
                "succession, with the company citing 'personal reasons' in both exit filings."
            ),
            source_url="https://news.example.com/meridian-treadworks-leadership-exit",
            observed_at=datetime(2026, 6, 5),
        ),
    ],
    "Ashford EPC Projects Ltd": [
        dict(
            signal_type="press_distress",
            headline="Ashford EPC Projects flags delays on two highway contracts",
            source_excerpt=(
                "Local trade press reports Ashford EPC Projects Ltd has requested extensions on "
                "two state highway contracts, citing subcontractor payment disputes."
            ),
            source_url="https://news.example.com/ashford-epc-contract-delays",
            observed_at=datetime(2026, 5, 10),
        ),
    ],
    "Veltrix Biopharma Ltd": [
        dict(
            signal_type="press_distress",
            headline="Veltrix Biopharma faces regulatory query over API plant compliance",
            source_excerpt=(
                "A regional regulator has issued a compliance query to Veltrix Biopharma Ltd "
                "regarding its active pharmaceutical ingredient manufacturing plant."
            ),
            source_url="https://news.example.com/veltrix-biopharma-regulatory-query",
            observed_at=datetime(2026, 6, 1),
        ),
    ],
    "Northfield Cognitive Systems Inc": [
        dict(
            signal_type="press_opportunity",
            headline="Northfield Cognitive Systems wins marquee GenAI platform contract",
            source_excerpt=(
                "Northfield Cognitive Systems Inc has been selected as the platform vendor for a "
                "large enterprise GenAI rollout, per a trade-press announcement."
            ),
            source_url="https://news.example.com/northfield-cognitive-platform-win",
            observed_at=datetime(2026, 6, 1),
        ),
    ],
    "Solstice BFSI Analytics Ltd": [
        dict(
            signal_type="press_opportunity",
            headline="Solstice BFSI Analytics named to industry fraud-analytics watchlist",
            source_excerpt=(
                "Solstice BFSI Analytics Ltd was named a 'company to watch' in a fraud-analytics "
                "industry roundup, citing strong early enterprise traction."
            ),
            source_url="https://news.example.com/solstice-bfsi-watchlist",
            observed_at=datetime(2026, 6, 5),
        ),
    ],
}


class MockNewsConnector(Connector):
    """Stand-in for a real news/press API integration."""

    source_type = "news"

    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        records = NEWS_DATA.get(entity.name, [])
        out = []
        for rec in records:
            if rec["observed_at"] < since:
                continue
            out.append({**rec, "source_type": self.source_type})
        return out
