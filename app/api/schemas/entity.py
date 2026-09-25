from pydantic import BaseModel, ConfigDict


class EntityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sectors: list[str]
    category: str
