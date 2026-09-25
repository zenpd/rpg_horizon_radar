from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reviewer_id: int | None
    reviewer_name_snapshot: str
    action: str
    resource_type: str
    resource_id: str | None
    detail: str | None
    created_at: datetime
