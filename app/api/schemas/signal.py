from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RawSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    signal_type: str
    source_type: str
    headline: str
    source_excerpt: str
    source_url: str
    provider: str = "mock"
    observed_at: datetime


class SignalClusterSummary(BaseModel):
    id: int
    entity_name: str
    entity_sectors: list[str]
    subsidiaries: list[str]
    score: float
    rationale: str
    signal_types: list[str]
    status: str
    updated_at: datetime


class SignalClusterDetail(SignalClusterSummary):
    entity_id: int
    entity_category: str
    window_start: datetime
    window_end: datetime
    raw_signals: list[RawSignalOut]
    evaluated_by: str | None = None
    evaluated_at: datetime | None = None
