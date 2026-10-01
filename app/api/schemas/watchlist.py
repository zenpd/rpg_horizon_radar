from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WatchlistEntity(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sectors: list[str]
    category: str
    is_fictional: bool
    origin: str
    status: str
    query_name: str
    nse_symbol: str | None = None
    discovery: dict | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    raw_signal_count: int = 0
    score: float | None = None


class WatchlistUpdate(BaseModel):
    status: Literal["watching", "dismissed"] | None = None
    nse_symbol: str | None = Field(default=None, max_length=32)
    query_name: str | None = Field(default=None, max_length=255)


class WatchlistCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    sectors: list[str] = Field(min_length=1)
    category: str = ""
    nse_symbol: str | None = Field(default=None, max_length=32)
    query_name: str = Field(default="", max_length=255)


class ConnectorStatus(BaseModel):
    name: str
    source_type: str
    configured: bool
    min_days: int
    entities_pulled: int
    last_pull: str | None = None
    budget: dict | None = None


class SourcesStatus(BaseModel):
    connectors: list[ConnectorStatus]
    llm_routes: list[str]
    last_run: dict | None = None
    scheduler: dict
