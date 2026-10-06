from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.evidence.schemas import EvidenceFileOut


class ComplaintCategory(StrEnum):
    DELIVERY = "DELIVERY"
    WRONG_PRODUCT = "WRONG_PRODUCT"
    PRODUCT_AUTHENTICITY = "PRODUCT_AUTHENTICITY"
    REFUND = "REFUND"
    PAYMENT = "PAYMENT"
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE"
    PRODUCT_QUALITY = "PRODUCT_QUALITY"
    OTHER = "OTHER"


ComplaintStatus = Literal[
    "SUBMITTED", "SME_RESPONDED", "UNDER_REVIEW", "RESOLVED", "UPHELD", "DISMISSED"
]
OPEN_STATUSES = ("SUBMITTED", "SME_RESPONDED", "UNDER_REVIEW")

Description = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=10, max_length=2000)
]
Response = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class SmeResponseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: Response


class ComplaintDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # UPHELD = the complaint is substantiated (a verified finding against the seller);
    # DISMISSED = not substantiated; RESOLVED = settled between the parties.
    decision: Literal["UPHELD", "DISMISSED", "RESOLVED"]
    note: Note


class ComplaintOut(BaseModel):
    id: str
    order_id: str
    order_number: str
    store_name: str
    store_slug: str
    category: ComplaintCategory
    description: str
    status: ComplaintStatus
    sme_response: str | None
    sme_responded_at: datetime | None
    escalated_at: datetime | None
    resolution_note: str | None
    decided_at: datetime | None
    closed_at: datetime | None
    created_at: datetime
    evidence: list[EvidenceFileOut]
    # Actions the caller may take now: customer resolve/escalate, SME respond/add_evidence.
    allowed_actions: list[str]


class ComplaintSummaryItem(BaseModel):
    id: str
    order_number: str
    store_name: str
    category: ComplaintCategory
    status: ComplaintStatus
    created_at: datetime
    escalated_at: datetime | None


class PublicComplaintSummary(BaseModel):
    """What the public may know: categories and outcomes only — never text or identities.

    Open complaints are customer allegations; only upheld complaints are verified findings."""

    open_allegations: dict[ComplaintCategory, int]
    upheld: dict[ComplaintCategory, int]
    resolved: int
    dismissed: int
    total: int
