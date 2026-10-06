from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Comment = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    comment: Comment | None = None


class ReviewResponseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: Comment


class ReviewOut(BaseModel):
    """Public shape: a verified purchase, never the reviewer's identity."""

    id: str
    rating: int
    comment: str | None
    sme_response: str | None
    sme_responded_at: datetime | None
    created_at: datetime


class SmeReviewOut(ReviewOut):
    order_number: str


class ReviewPage(BaseModel):
    average: float | None
    count: int
    distribution: dict[int, int]
    items: list[ReviewOut]
