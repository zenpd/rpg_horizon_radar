from pydantic import BaseModel, ConfigDict


class SubsidiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    sectors: list[str]
    compliance_gate: bool
    signal_focus: str


class GateUpdateRequest(BaseModel):
    compliance_gate: bool
