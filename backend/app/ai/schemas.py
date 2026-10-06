"""Structured outputs requested from Gemini (also used as the JSON schema sent to the model)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ai.output import AiAnalysisOut
from app.complaints.schemas import ComplaintCategory

__all__ = ["AiAnalysisOut"]

Sentiment = Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
Severity = Literal["LOW", "MEDIUM", "HIGH"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComplaintAnalysis(_Strict):
    category: ComplaintCategory
    sentiment: Sentiment
    severity: Severity
    # A complaint is always a customer allegation; the service enforces this regardless of output.
    claim_type: Literal["CUSTOMER_ALLEGATION"]
    summary: str = Field(
        max_length=300, description="One neutral sentence; no conclusions about guilt."
    )


class ReviewAnalysis(_Strict):
    sentiment: Sentiment
    topics: list[Literal["DELIVERY", "PRODUCT_QUALITY", "PRODUCT_AUTHENTICITY", "CUSTOMER_SERVICE",
                         "PRICE", "PACKAGING", "OTHER"]] = Field(max_length=4)  # fmt: skip
    claim_type: Literal["CUSTOMER_OPINION"]
    mentions_problem: bool


class DocumentExtraction(_Strict):
    document_type: Literal["BUSINESS_REGISTRATION", "INVOICE", "SUPPLIER_LETTER", "CERTIFICATE",
                           "UTILITY_BILL", "OTHER", "UNREADABLE"]  # fmt: skip
    business_name: str | None = Field(default=None, max_length=200)
    registration_number: str | None = Field(default=None, max_length=60)
    issue_date: str | None = Field(default=None, max_length=20, description="YYYY-MM-DD if visible")
    issuer: str | None = Field(default=None, max_length=200)
    product_names: list[str] = Field(default_factory=list, max_length=10)
    legibility: Literal["CLEAR", "PARTIAL", "POOR"]
    notes: str = Field(default="", max_length=400, description="Observations only, no verdicts.")


class TrustExplanationOut(BaseModel):
    text: str
    # AI = Gemini summary of the signals; TEMPLATE = deterministic fallback.
    source: Literal["AI", "TEMPLATE"]
    locale: Literal["en", "si"]
    model: str | None
    rules_version: str
    generated_at: datetime
