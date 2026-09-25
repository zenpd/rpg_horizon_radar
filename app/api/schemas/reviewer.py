from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReviewerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    role: str
    subsidiary_scopes: list[str]
    created_at: datetime


class ReviewerCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    subsidiary_scopes: list[str] = []
