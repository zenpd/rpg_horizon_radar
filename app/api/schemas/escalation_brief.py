from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DirectionalConsideration(BaseModel):
    label: str
    value: str


class RippleEffect(BaseModel):
    subsidiary_code: str
    counterparty_name: str
    counterparty_kind: str
    counterparty_subsidiary_code: str | None = None
    dependency_type: str
    relevance: str
    rationale: str


class EscalationBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cluster_id: int
    generated_at: datetime
    escalated_by: str | None = None
    pros: list[str]
    cons: list[str]
    directional_considerations: list[DirectionalConsideration]
    deal_complexity: str
    disclaimer: str
    ripple_effects: list[RippleEffect] = []
