"""Plain data passed through the trust engine. No I/O here."""

from dataclasses import dataclass, field
from typing import Any, Literal

Dimension = Literal["BUSINESS", "PRODUCT", "TRANSACTION"]
SignalKind = Literal["POSITIVE", "RISK", "INFO"]
Provenance = Literal[
    "VERIFIED_FACT", "SELLER_CLAIM", "CUSTOMER_ALLEGATION", "PUBLIC_EVIDENCE",
    "AI_ANALYSIS", "PLATFORM_STATISTIC",
]  # fmt: skip
Level = Literal["VERIFIED", "TRUSTED", "DEVELOPING", "CAUTION", "HIGH_RISK"]
Authenticity = Literal["VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "CONCERN"]


@dataclass(frozen=True)
class ProductEvidence:
    """Admin-reviewed authenticity evidence for one active product."""

    product_id: str
    accepted_document_ids: tuple[str, ...] = ()
    accepted_image_ids: tuple[str, ...] = ()
    misleading_ids: tuple[str, ...] = ()
    # Complaints about this product's authenticity that an admin upheld (verified findings).
    upheld_authenticity_complaints: int = 0
    # Hidden products still get an authenticity status but do not count toward the public score.
    active: bool = True


@dataclass(frozen=True)
class TransactionStats:
    """Order/review/complaint outcomes. All zero until commerce (Phase 5/6) supplies data."""

    completed_orders: int = 0
    failed_deliveries: int = 0
    late_deliveries: int = 0
    seller_cancellations: int = 0
    upheld_complaints: int = 0
    upheld_complaints_90d: int = 0
    overdue_unresolved_complaints: int = 0
    verified_review_count: int = 0
    verified_review_average: float | None = None
    # Open complaints: customer allegations, shown but not scored.
    open_complaints: int = 0


@dataclass(frozen=True)
class TrustInputs:
    sme_status: Literal["ACTIVE", "SUSPENDED"] = "ACTIVE"
    verification_status: Literal["UNVERIFIED", "PENDING", "VERIFIED", "REJECTED"] = "UNVERIFIED"
    verification_evidence_ids: tuple[str, ...] = ()
    contact_verified: bool = False
    confirmed_social_accounts: int = 0
    social_evidence_ids: tuple[str, ...] = ()
    published_policies: tuple[str, ...] = ()
    has_logo: bool = False
    has_description: bool = False
    account_age_days: int = 0
    misleading_evidence_ids: tuple[str, ...] = ()
    products: tuple[ProductEvidence, ...] = ()
    transactions: TransactionStats = field(default_factory=TransactionStats)


@dataclass(frozen=True)
class Signal:
    dimension: Dimension
    kind: SignalKind
    code: str
    points: int
    provenance: Provenance
    params: dict[str, Any] = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DimensionResult:
    score: int
    signals: tuple[Signal, ...]


@dataclass(frozen=True)
class TrustResult:
    overall: int
    level: Level
    business: DimensionResult
    product: DimensionResult
    transaction: DimensionResult
    product_authenticity: dict[str, Authenticity]
    rules_version: str

    @property
    def signals(self) -> tuple[Signal, ...]:
        return self.business.signals + self.product.signals + self.transaction.signals
