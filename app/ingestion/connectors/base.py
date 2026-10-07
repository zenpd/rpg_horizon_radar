from abc import ABC, abstractmethod
from datetime import datetime

from db.models import Entity


class Connector(ABC):
    """Abstract ingestion connector. Every concrete connector is a live source
    in ingestion/connectors/live/ (news, filings, patents, hiring, prices), so
    adding a source means implementing this interface, not a redesign."""

    source_type: str = "news"

    @abstractmethod
    def fetch(self, entity: Entity, since: datetime) -> list[dict]:
        """Return a list of raw signal dicts with keys: signal_type, source_type,
        headline, source_excerpt, source_url, observed_at (datetime)."""
        raise NotImplementedError
