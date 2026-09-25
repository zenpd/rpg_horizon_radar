from pydantic import BaseModel


class IngestRunResult(BaseModel):
    new_raw_signals: int
    clusters_updated: int
