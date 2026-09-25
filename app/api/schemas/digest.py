from datetime import datetime

from pydantic import BaseModel

from api.schemas.signal import SignalClusterSummary


class DigestSummaryOut(BaseModel):
    id: int
    period_start: datetime
    period_end: datetime
    created_at: datetime
    subsidiary_breakdown: dict[str, int]


class DigestItemOut(BaseModel):
    subsidiary_code: str
    cluster: SignalClusterSummary


class DigestDetailOut(BaseModel):
    id: int
    period_start: datetime
    period_end: datetime
    created_at: datetime
    items: list[DigestItemOut]
