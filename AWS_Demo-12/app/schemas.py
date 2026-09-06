from typing import Any, Optional

from pydantic import BaseModel, Field


class JobRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Agent query to process")


class JobSubmittedResponse(BaseModel):
    job_id: str
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[dict[str, Any]] = None
    result: Optional[dict[str, Any]] = None
