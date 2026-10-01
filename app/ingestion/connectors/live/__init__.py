"""Live connectors for real watched companies. The mock connectors
(ingestion/connectors/mock_*.py) keep serving the fictional seed entities;
services/ingest.py picks the set by ``Entity.is_fictional``."""
from __future__ import annotations

import httpx

from ingestion.connectors.live.common import LiveConnector, SourceError
from ingestion.connectors.live.filings import NSE, AlphaVantage, Fincrux, resolve_nse_symbol
from ingestion.connectors.live.news import GNews, NewsData, Tavily, YouTube
from ingestion.connectors.live.trends import Adzuna, EPOPatents

__all__ = ["LiveConnector", "SourceError", "live_connectors", "resolve_nse_symbol"]


def live_connectors(state: dict, transport: httpx.BaseTransport | None = None) -> list[LiveConnector]:
    return [GNews(state, transport), NewsData(state, transport), Tavily(state, transport), YouTube(state, transport),
            NSE(state, transport), Fincrux(state, transport), AlphaVantage(state, transport),
            Adzuna(state, transport), EPOPatents(state, transport)]
