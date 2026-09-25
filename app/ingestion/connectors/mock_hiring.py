from datetime import datetime

from db.models import Entity
from ingestion.connectors.base import Connector

# DEMO/SYNTHETIC DATA — see db/seed.py header. All entity names below are
# fictional and keyed by name for deterministic, reproducible fetches.
HIRING_DATA: dict[str, list[dict]] = {
    "Ashford EPC Projects Ltd": [
        dict(
            signal_type="hiring_scaledown",
            headline="Ashford EPC Projects reduces site engineering headcount",
            source_excerpt=(
                "Job-board listings from Ashford EPC Projects Ltd show a net reduction in active "
                "site-engineering postings over the past quarter."
            ),
            source_url="https://hiring.example.com/ashford-epc-headcount-reduction",
            observed_at=datetime(2026, 6, 8),
        ),
    ],
    "Northfield Cognitive Systems Inc": [
        dict(
            signal_type="hiring_scaleup",
            headline="Northfield Cognitive Systems opens 40 new GenAI engineering roles",
            source_excerpt=(
                "Job-board listings show Northfield Cognitive Systems Inc has opened roughly 40 "
                "new engineering roles concentrated in GenAI infrastructure."
            ),
            source_url="https://hiring.example.com/northfield-cognitive-hiring-surge",
            observed_at=datetime(2026, 6, 20),
        ),
    ],
    "Solstice BFSI Analytics Ltd": [
        dict(
            signal_type="hiring_scaleup",
            headline="Solstice BFSI Analytics scales up fraud-analytics team",
            source_excerpt=(
                "Job-board listings show a sustained increase in fraud-analytics and data-science "
                "postings from Solstice BFSI Analytics Ltd."
            ),
            source_url="https://hiring.example.com/solstice-bfsi-team-scaleup",
            observed_at=datetime(2026, 6, 18),
        ),
    ],
    "Palmgrove Estates Cooperative": [
        dict(
            signal_type="hiring_scaledown",
            headline="Palmgrove Estates Cooperative trims seasonal harvest workforce",
            source_excerpt=(
                "Job-board and local labor-notice records show Palmgrove Estates Cooperative "
                "reduced seasonal harvest hiring amid weaker yields."
            ),
            source_url="https://hiring.example.com/palmgrove-estates-workforce-trim",
            observed_at=datetime(2026, 6, 10),
        ),
    ],
}


class MockHiringConnector(Connector):
    """Stand-in for a real hiring-pattern/job-board API integration."""

    source_type = "hiring"

    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        records = HIRING_DATA.get(entity.name, [])
        out = []
        for rec in records:
            if rec["observed_at"] < since:
                continue
            out.append({**rec, "source_type": self.source_type})
        return out
