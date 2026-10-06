"""Structured outputs requested from Gemini (also used as the JSON schema sent to the model)."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


# --- Trustora AI chat -----------------------------------------------------------------------
class ChatTurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ChatContextIn(BaseModel):
    """What the user is looking at, so "this seller" / "this product" can be resolved."""

    model_config = ConfigDict(extra="forbid")

    store_slug: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{3,40}$")] | None = None
    product_id: UUID | None = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Stateless: the client sends the recent conversation (oldest first, last turn = user).
    messages: list[ChatTurnIn] = Field(min_length=1, max_length=12)
    locale: Literal["en", "si"] = "en"
    context: ChatContextIn | None = None

    @model_validator(mode="after")
    def _last_is_user(self) -> "ChatRequest":
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be from the user")
        return self


class ChatSource(BaseModel):
    kind: Literal["STORE", "PRODUCT", "ORDER"]
    ref: str
    label: str


class ComplaintDraft(BaseModel):
    """Prepared by the assistant, submitted only if the customer confirms it in the UI."""

    order_id: str
    order_number: str
    category: str
    description: str


class ChatResponse(BaseModel):
    reply: str
    used_tools: list[str]
    sources: list[ChatSource]
    draft: ComplaintDraft | None = None
    model: str
    provenance: Literal["AI_ANALYSIS"] = "AI_ANALYSIS"
