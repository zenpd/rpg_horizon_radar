from datetime import datetime

from db.models import Entity
from ingestion.connectors.base import Connector

# DEMO/SYNTHETIC DATA — see db/seed.py header. All entity names below are
# fictional and keyed by name for deterministic, reproducible fetches.
FILINGS_DATA: dict[str, list[dict]] = {
    "Meridian Treadworks Pvt Ltd": [
        dict(
            signal_type="delayed_filing",
            headline="Meridian Treadworks delays quarterly filing beyond statutory deadline",
            source_excerpt=(
                "Meridian Treadworks Pvt Ltd has not filed its quarterly financial statements by "
                "the statutory deadline, citing 'ongoing internal review'."
            ),
            source_url="https://filings.example.com/meridian-treadworks-delayed-q-filing",
            observed_at=datetime(2026, 6, 20),
        ),
        dict(
            signal_type="credit_downgrade",
            headline="Rating agency downgrades Meridian Treadworks to BBB- on liquidity concerns",
            source_excerpt=(
                "A domestic credit rating agency has downgraded Meridian Treadworks Pvt Ltd's "
                "long-term rating to BBB- citing tightening liquidity and working-capital strain."
            ),
            source_url="https://filings.example.com/meridian-treadworks-rating-downgrade",
            observed_at=datetime(2026, 7, 1),
        ),
    ],
    "Ashford EPC Projects Ltd": [
        dict(
            signal_type="delayed_filing",
            headline="Ashford EPC Projects seeks extension for annual filing",
            source_excerpt=(
                "Ashford EPC Projects Ltd has filed for a statutory extension on its annual "
                "return, the second such extension in two years."
            ),
            source_url="https://filings.example.com/ashford-epc-filing-extension",
            observed_at=datetime(2026, 5, 25),
        ),
    ],
    "Veltrix Biopharma Ltd": [
        dict(
            signal_type="delayed_filing",
            headline="Veltrix Biopharma delays half-year filing pending audit review",
            source_excerpt=(
                "Veltrix Biopharma Ltd has pushed back its half-year filing while an internal "
                "audit review is completed."
            ),
            source_url="https://filings.example.com/veltrix-biopharma-delayed-filing",
            observed_at=datetime(2026, 6, 15),
        ),
    ],
    "Corvane Materials Systems Ltd": [
        dict(
            signal_type="credit_downgrade",
            headline="Corvane Materials Systems placed on negative rating watch",
            source_excerpt=(
                "Corvane Materials Systems Ltd has been placed on negative watch by a domestic "
                "rating agency amid softening order volumes."
            ),
            source_url="https://filings.example.com/corvane-materials-negative-watch",
            observed_at=datetime(2026, 5, 20),
        ),
    ],
}


class MockFilingsConnector(Connector):
    """Stand-in for a real regulatory-filings/annual-report API integration."""

    source_type = "filing"

    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        records = FILINGS_DATA.get(entity.name, [])
        out = []
        for rec in records:
            if rec["observed_at"] < since:
                continue
            out.append({**rec, "source_type": self.source_type})
        return out
