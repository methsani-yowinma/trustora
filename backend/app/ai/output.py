"""Public shape of a stored AI analysis (dependency-free so any module can embed it)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AiAnalysisOut(BaseModel):
    """An AI analysis as shown to admins (and SMEs for their own reviews). Always labelled as
    analysis — never as a verified fact — and never used to change scores or decisions."""

    id: str
    kind: Literal["COMPLAINT", "REVIEW", "DOCUMENT", "TRUST_EXPLANATION"]
    status: Literal["DONE", "FAILED", "SKIPPED"]
    model: str
    output: dict[str, Any] | None
    # Deterministic checks computed by Trustora code (not the model), e.g. name/number matches.
    checks: dict[str, Any] | None = None
    error_code: str | None
    created_at: datetime
    provenance: Literal["AI_ANALYSIS"] = "AI_ANALYSIS"
