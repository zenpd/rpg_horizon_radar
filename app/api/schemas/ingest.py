from pydantic import BaseModel


class IngestRunResult(BaseModel):
    new_raw_signals: int
    clusters_updated: int
    errors: list[str] = []
    changed_subsidiaries: list[str] = []
    via: str = "inline_fallback"
    swot_rebuilt: list[str] = []
    swot_errors: list[str] = []


class JobOut(BaseModel):
    """A background job (ingest, discovery, swot). ``result`` is the job's own
    result dict once completed — an IngestRunResult for kind=ingest."""
    id: str
    kind: str
    status: str  # running | completed | failed
    result: dict | None = None
    error: str | None = None
    started_by: str
    started_at: str
    finished_at: str | None = None
