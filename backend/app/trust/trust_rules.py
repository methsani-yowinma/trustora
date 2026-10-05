"""Deterministic trust rules: pure functions from TrustInputs to signals and dimension scores.

No database, no AI. Each dimension score is ``clamp(base + sum(signal.points))``, so every point
in a score can be traced to a signal with a code, provenance and supporting evidence.
"""

from app.trust import trust_weights as w
from app.trust.models import (
    Authenticity,
    DimensionResult,
    ProductEvidence,
    Provenance,
    Signal,
    SignalKind,
    TransactionStats,
    TrustInputs,
)


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _dimension(base: int, signals: list[Signal]) -> DimensionResult:
    return DimensionResult(
        score=clamp(base + sum(s.points for s in signals)), signals=tuple(signals)
    )


# --- Business trust ---------------------------------------------------------------------
def business_rules(inputs: TrustInputs) -> DimensionResult:
    signals: list[Signal] = []

    def add(
        kind: SignalKind,
        code: str,
        points: int,
        provenance: Provenance,
        params: dict[str, object] | None = None,
        evidence: tuple[str, ...] = (),
    ) -> None:
        signals.append(Signal("BUSINESS", kind, code, points, provenance, params or {}, evidence))

    status = inputs.verification_status
    if status == "VERIFIED":
        add(
            "POSITIVE",
            "BUSINESS_VERIFIED",
            w.BUSINESS_VERIFIED,
            "VERIFIED_FACT",
            evidence=inputs.verification_evidence_ids,
        )
    elif status == "PENDING":
        add("INFO", "VERIFICATION_PENDING", 0, "PLATFORM_STATISTIC")
    elif status == "REJECTED":
        add("RISK", "VERIFICATION_NOT_APPROVED", w.VERIFICATION_NOT_APPROVED, "VERIFIED_FACT")
    else:
        add("RISK", "BUSINESS_NOT_VERIFIED", 0, "PLATFORM_STATISTIC")

    if inputs.contact_verified:
        add("POSITIVE", "CONTACT_CONFIRMED", w.CONTACT_CONFIRMED, "VERIFIED_FACT")

    socials = inputs.confirmed_social_accounts
    if socials:
        points = w.SOCIAL_TWO_OR_MORE if socials >= 2 else w.SOCIAL_ONE
        add(
            "POSITIVE",
            "SOCIAL_ACCOUNTS_CONFIRMED",
            points,
            "VERIFIED_FACT",
            {"count": socials},
            inputs.social_evidence_ids,
        )

    if inputs.published_policies:
        policies = sorted(inputs.published_policies)
        # Policies are the seller's own statements: positive for transparency, not verified facts.
        add(
            "POSITIVE",
            "POLICIES_PUBLISHED",
            w.POLICY_EACH * len(policies),
            "SELLER_CLAIM",
            {"policies": policies},
        )
    else:
        add("RISK", "NO_POLICIES", 0, "PLATFORM_STATISTIC")

    days = inputs.account_age_days
    if days >= w.TENURE_DAYS[1]:
        add("POSITIVE", "PLATFORM_TENURE", w.TENURE_365_DAYS, "PLATFORM_STATISTIC", {"days": days})
    elif days >= w.TENURE_DAYS[0]:
        add("POSITIVE", "PLATFORM_TENURE", w.TENURE_90_DAYS, "PLATFORM_STATISTIC", {"days": days})
    else:
        add("INFO", "NEW_ON_PLATFORM", 0, "PLATFORM_STATISTIC", {"days": days})

    if inputs.has_logo and inputs.has_description:
        add("POSITIVE", "PROFILE_COMPLETE", w.PROFILE_COMPLETE, "SELLER_CLAIM")

    misleading = inputs.misleading_evidence_ids
    if misleading:
        points = max(w.MISLEADING_EVIDENCE_MAX, w.MISLEADING_EVIDENCE_EACH * len(misleading))
        add(
            "RISK",
            "MISLEADING_EVIDENCE",
            points,
            "VERIFIED_FACT",
            {"count": len(misleading)},
            misleading,
        )

    if inputs.sme_status == "SUSPENDED":
        add("RISK", "ACCOUNT_SUSPENDED", w.ACCOUNT_SUSPENDED, "VERIFIED_FACT")

    return _dimension(w.BUSINESS_BASE, signals)


# --- Product trust -------------------------------------------------------------------------
def product_authenticity(product: ProductEvidence) -> Authenticity:
    """Authenticity comes only from admin-reviewed evidence — never from AI image judgement."""
    if product.misleading_ids:
        return "CONCERN"
    if product.accepted_document_ids:
        return "VERIFIED"
    if product.accepted_image_ids:
        return "PARTIALLY_VERIFIED"
    return "UNVERIFIED"


_PRODUCT_SIGNALS: dict[Authenticity, tuple[str, str, str]] = {
    "VERIFIED": ("POSITIVE", "PRODUCTS_AUTHENTICITY_VERIFIED", "VERIFIED_FACT"),
    "PARTIALLY_VERIFIED": ("POSITIVE", "PRODUCTS_PARTIALLY_VERIFIED", "VERIFIED_FACT"),
    "UNVERIFIED": ("INFO", "PRODUCTS_WITHOUT_AUTHENTICITY_EVIDENCE", "PLATFORM_STATISTIC"),
    "CONCERN": ("RISK", "PRODUCT_AUTHENTICITY_CONCERN", "VERIFIED_FACT"),
}


def product_rules(inputs: TrustInputs) -> tuple[DimensionResult, dict[str, Authenticity]]:
    statuses = {p.product_id: product_authenticity(p) for p in inputs.products}
    active = [p for p in inputs.products if p.active]
    if not active:
        signal = Signal("PRODUCT", "INFO", "NO_ACTIVE_PRODUCTS", 0, "PLATFORM_STATISTIC")
        return DimensionResult(score=w.NEUTRAL, signals=(signal,)), statuses

    total = len(active)
    signals = []
    for status, (kind, code, provenance) in _PRODUCT_SIGNALS.items():
        group = [p for p in active if statuses[p.product_id] == status]
        if not group:
            continue
        evidence = tuple(
            eid
            for p in group
            for eid in (
                p.misleading_ids
                if status == "CONCERN"
                else p.accepted_document_ids + p.accepted_image_ids
            )
        )
        # Each group's share of the mean authenticity value, expressed relative to neutral.
        points = round(len(group) * (w.AUTHENTICITY_VALUE[status] - w.NEUTRAL) / total)
        signals.append(
            Signal(
                "PRODUCT",
                kind,  # type: ignore[arg-type]
                code,
                points,
                provenance,  # type: ignore[arg-type]
                {"count": len(group), "total": total},
                evidence,
            )
        )
    return _dimension(w.NEUTRAL, signals), statuses


# --- Transaction trust -------------------------------------------------------------------
def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def transaction_rules(stats: TransactionStats) -> DimensionResult:
    n = stats.completed_orders
    if n == 0:
        return DimensionResult(
            score=w.NEUTRAL,
            signals=(
                Signal(
                    "TRANSACTION",
                    "INFO",
                    "LIMITED_TRANSACTION_HISTORY",
                    0,
                    "PLATFORM_STATISTIC",
                    {"completed_orders": 0},
                ),
            ),
        )

    # Sample-size weight: observed performance counts more as completed orders accumulate.
    weight = n / (n + w.PRIOR_ORDERS)
    raw: list[tuple[str, str, float, str, dict[str, object]]] = [
        ("POSITIVE", "COMPLETED_ORDERS", 100 - w.NEUTRAL, "PLATFORM_STATISTIC", {"count": n}),
    ]

    failed = _rate(stats.failed_deliveries, n + stats.failed_deliveries)
    if stats.failed_deliveries:
        raw.append(
            (
                "RISK",
                "DELIVERY_FAILURES",
                -w.FAILED_DELIVERY_RATE_WEIGHT * failed,
                "PLATFORM_STATISTIC",
                {"count": stats.failed_deliveries, "rate": round(failed, 3)},
            )
        )
    late = _rate(stats.late_deliveries, n)
    if stats.late_deliveries:
        raw.append(
            (
                "RISK",
                "LATE_DELIVERIES",
                -w.LATE_DELIVERY_RATE_WEIGHT * late,
                "PLATFORM_STATISTIC",
                {"count": stats.late_deliveries, "rate": round(late, 3)},
            )
        )
    cancelled = _rate(stats.seller_cancellations, n + stats.seller_cancellations)
    if stats.seller_cancellations:
        raw.append(
            (
                "RISK",
                "SELLER_CANCELLATIONS",
                -w.SELLER_CANCELLATION_RATE_WEIGHT * cancelled,
                "PLATFORM_STATISTIC",
                {"count": stats.seller_cancellations, "rate": round(cancelled, 3)},
            )
        )
    if stats.upheld_complaints:
        raw.append(
            (
                "RISK",
                "UPHELD_COMPLAINTS",
                max(w.UPHELD_COMPLAINT_MAX, w.UPHELD_COMPLAINT_EACH * stats.upheld_complaints),
                "VERIFIED_FACT",
                {"count": stats.upheld_complaints},
            )
        )
    if stats.overdue_unresolved_complaints:
        raw.append(
            (
                "RISK",
                "UNRESOLVED_COMPLAINTS",
                max(
                    w.OVERDUE_COMPLAINT_MAX,
                    w.OVERDUE_COMPLAINT_EACH * stats.overdue_unresolved_complaints,
                ),
                "PLATFORM_STATISTIC",
                {"count": stats.overdue_unresolved_complaints},
            )
        )
    if (
        stats.verified_review_count >= w.MIN_REVIEWS_FOR_RATING
        and stats.verified_review_average is not None
    ):
        delta = (stats.verified_review_average - 3) * w.RATING_POINTS_PER_STAR
        raw.append(
            (
                "POSITIVE" if delta >= 0 else "RISK",
                "VERIFIED_REVIEW_RATING",
                delta,
                "PLATFORM_STATISTIC",
                {
                    "average": round(stats.verified_review_average, 1),
                    "count": stats.verified_review_count,
                },
            )
        )

    # Observed score is bounded to 0..100 before blending, so penalties cannot exceed it.
    observed_delta = sum(points for _, _, points, _, _ in raw)
    bounded = clamp(w.NEUTRAL + observed_delta) - w.NEUTRAL
    scale = bounded / observed_delta if observed_delta else 0.0

    signals = [
        Signal("TRANSACTION", kind, code, round(points * scale * weight), provenance, params)  # type: ignore[arg-type]
        for kind, code, points, provenance, params in raw
    ]
    if n < w.LIMITED_HISTORY_ORDERS:
        signals.append(
            Signal(
                "TRANSACTION",
                "INFO",
                "LIMITED_TRANSACTION_HISTORY",
                0,
                "PLATFORM_STATISTIC",
                {"completed_orders": n},
            )
        )
    score = clamp(w.NEUTRAL + bounded * weight)
    return DimensionResult(score=score, signals=tuple(signals))
