from pydantic import BaseModel, ConfigDict


class SubsidiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    sectors: list[str]
    signal_focus: str
