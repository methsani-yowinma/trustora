from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.evidence.schemas import EvidenceFileOut

Level = Literal["VERIFIED", "TRUSTED", "DEVELOPING", "CAUTION", "HIGH_RISK"]


class TrustScoreOut(BaseModel):
    overall_score: int
    level: Level
    business_score: int
    product_score: int
    transaction_score: int
    rules_version: str
    computed_at: datetime


class TrustSignalOut(BaseModel):
    dimension: Literal["BUSINESS", "PRODUCT", "TRANSACTION"]
    kind: Literal["POSITIVE", "RISK", "INFO"]
    code: str
    points: int
    provenance: str
    params: dict[str, Any]
    evidence_count: int


class EvidenceSummary(BaseModel):
    total: int = 0
    accepted: int = 0
    pending: int = 0
    rejected: int = 0
    by_provenance: dict[str, int] = Field(default_factory=dict)


class HistoryPoint(BaseModel):
    at: datetime
    overall_score: int
    level: Level


class HistoryChange(BaseModel):
    from_score: int
    to_score: int
    from_level: Level
    to_level: Level
    days: int


class HistoryOut(BaseModel):
    days: int
    # Score in effect when the window opened (null if the store has no earlier history).
    baseline: HistoryPoint | None
    points: list[HistoryPoint]
    change: HistoryChange | None


class PassportStore(BaseModel):
    id: str
    slug: str
    name: str
    logo_url: str | None
    description_i18n: dict[str, str] | None
    verification_status: Literal["UNVERIFIED", "PENDING", "VERIFIED", "REJECTED"]
    verified_at: datetime | None
    member_since: datetime


class PassportOut(BaseModel):
    """The Digital Trust Passport: identity, scores, signals (the 'why'), evidence summary."""

    store: PassportStore
    trust: TrustScoreOut
    positive_signals: list[TrustSignalOut]
    risk_signals: list[TrustSignalOut]
    info_signals: list[TrustSignalOut]
    evidence_summary: EvidenceSummary
    history: HistoryOut


class Suggestion(BaseModel):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class SmeTrustOut(PassportOut):
    suggestions: list[Suggestion]


# --- Admin evidence review --------------------------------------------------------------
class AdminEvidenceItem(EvidenceFileOut):
    sme_id: str
    sme_name: str
    sme_slug: str
    product_id: str | None
    product_name_i18n: dict[str, str] | None
    flagged_misleading: bool
    review_note: str | None


class EvidenceReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["ACCEPTED", "REJECTED"]
    # Rejected because it appears forged/mismatched (a risk finding), not merely insufficient.
    misleading: bool = False
    note: Annotated[str, StringConstraints(max_length=1000)] | None = None

    @model_validator(mode="after")
    def _rules(self) -> "EvidenceReviewIn":
        if self.decision == "ACCEPTED" and self.misleading:
            raise ValueError("Accepted evidence cannot be flagged as misleading")
        if self.decision == "REJECTED" and not self.note:
            raise ValueError("A note is required when rejecting evidence")
        return self
