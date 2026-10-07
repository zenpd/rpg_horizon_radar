from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReviewerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    created_at: datetime


class ReviewerCreate(BaseModel):
    name: str
    email: str
    password: str
