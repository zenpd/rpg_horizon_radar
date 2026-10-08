"""Live connectors for the approved, watched companies (services/ingest.py)."""
from __future__ import annotations

import httpx

from ingestion.connectors.live.common import LiveConnector, SourceError
from ingestion.connectors.live.filings import NSE, AlphaVantage, Fincrux, resolve_nse_symbol
from ingestion.connectors.live.news import GDELT, DuckDuckGo, GNews, NewsData, Tavily, YouTube
from ingestion.connectors.live.trends import Adzuna, EPOPatents

__all__ = ["LiveConnector", "SourceError", "live_connectors", "resolve_nse_symbol"]


def live_connectors(state: dict, transport: httpx.BaseTransport | None = None) -> list[LiveConnector]:
    return [GNews(state, transport), GDELT(state, transport), NewsData(state, transport), Tavily(state, transport), DuckDuckGo(state, transport), YouTube(state, transport),
            NSE(state, transport), Fincrux(state, transport), AlphaVantage(state, transport),
            Adzuna(state, transport), EPOPatents(state, transport)]
