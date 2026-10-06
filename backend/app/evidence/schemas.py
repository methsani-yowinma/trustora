from datetime import datetime

from pydantic import BaseModel

from app.ai.output import AiAnalysisOut


class EvidenceFileOut(BaseModel):
    id: str
    type: str
    provenance: str
    description: str | None
    mime_type: str | None
    size_bytes: int | None
    sha256: str | None
    review_status: str
    created_at: datetime
    download_url: str | None = None
    # Admin views only.
    ai_analysis: AiAnalysisOut | None = None
