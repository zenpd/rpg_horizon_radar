from datetime import datetime

from db.models import Entity
from ingestion.connectors.base import Connector

# DEMO/SYNTHETIC DATA — see db/seed.py header. All entity names below are
# fictional and keyed by name for deterministic, reproducible fetches.
PATENTS_DATA: dict[str, list[dict]] = {
    "Corvane Materials Systems Ltd": [
        dict(
            signal_type="patent_shift",
            headline="Corvane Materials Systems patent filings drop sharply year-on-year",
            source_excerpt=(
                "Patent-office records show Corvane Materials Systems Ltd filed 70% fewer new "
                "applications this year versus the prior year, concentrated in its core product line."
            ),
            source_url="https://patents.example.com/corvane-materials-filing-decline",
            observed_at=datetime(2026, 6, 2),
        ),
    ],
    "Northfield Cognitive Systems Inc": [
        dict(
            signal_type="patent_shift",
            headline="Northfield Cognitive Systems files cluster of new GenAI-inference patents",
            source_excerpt=(
                "Patent-office records show a burst of new filings from Northfield Cognitive "
                "Systems Inc concentrated in inference-optimization techniques."
            ),
            source_url="https://patents.example.com/northfield-cognitive-patent-cluster",
            observed_at=datetime(2026, 6, 12),
        ),
    ],
}


class MockPatentsConnector(Connector):
    """Stand-in for a real patent-activity API integration."""

    source_type = "patent"

    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        records = PATENTS_DATA.get(entity.name, [])
        out = []
        for rec in records:
            if rec["observed_at"] < since:
                continue
            out.append({**rec, "source_type": self.source_type})
        return out
