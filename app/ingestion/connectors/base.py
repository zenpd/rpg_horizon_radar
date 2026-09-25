from abc import ABC, abstractmethod
from datetime import datetime

from db.models import Entity


class Connector(ABC):
    """Abstract ingestion connector. A real news/filings/patent/hiring API
    integration is a drop-in swap of this interface — not a redesign. In this
    prototype every concrete connector (mock_news, mock_filings, mock_patents,
    mock_hiring) returns small, deterministic, hard-coded fictional records
    per known seed entity — no external HTTP calls, no non-reproducible
    randomness."""

    source_type: str = "news"

    @abstractmethod
    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        """Return a list of raw signal dicts with keys: signal_type, source_type,
        headline, source_excerpt, source_url, observed_at (datetime)."""
        raise NotImplementedError
