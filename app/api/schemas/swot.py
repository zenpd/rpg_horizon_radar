from datetime import datetime

from pydantic import BaseModel, Field


class SwotBriefOut(BaseModel):
    id: int
    subsidiary_code: str
    generated_at: datetime
    generated_by: str  # a reviewer's name, or "scheduler"
    model: str
    rounds: int
    content: dict
    evidence: list[dict]


class TeamNotes(BaseModel):
    strengths: list[str] = Field(default_factory=list, max_length=10)
    weaknesses: list[str] = Field(default_factory=list, max_length=10)
