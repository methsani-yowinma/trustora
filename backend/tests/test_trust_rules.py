"""Trust engine rules and calculation: pure functions, many evidence combinations."""

from datetime import UTC, datetime, timedelta

import pytest

from app.trust import trust_weights as w
from app.trust.models import ProductEvidence, TransactionStats, TrustInputs
from app.trust.schemas import TrustSignalOut
from app.trust.trust_calculator import calculate
from app.trust.trust_explanation import improvement_suggestions
from app.trust.trust_history import summarize
from app.trust.trust_rules import (
    business_rules,
    product_authenticity,
    product_rules,
    transaction_rules,
)

STRONG_PROFILE = dict(
    verification_status="VERIFIED",
    verification_evidence_ids=("v1",),
    contact_verified=True,
    confirmed_social_accounts=2,
    published_policies=("returns", "refunds", "delivery"),
    has_logo=True,
    has_description=True,
    account_age_days=400,
    products=(ProductEvidence("p1", accepted_document_ids=("d1",)),),
)
GOOD_ORDERS = TransactionStats(
    completed_orders=60, verified_review_count=20, verified_review_average=4.7
)


def codes(result_signals) -> set[str]:
    return {s.code for s in result_signals}


# --- Basic properties ----------------------------------------------------------------
def test_weights_sum_to_one() -> None:
    assert sum(w.DIMENSION_WEIGHTS.values()) == pytest.approx(1.0)


def test_calculation_is_deterministic() -> None:
    inputs = TrustInputs(**STRONG_PROFILE, transactions=GOOD_ORDERS)
    assert calculate(inputs) == calculate(inputs)


def test_every_business_and_product_point_is_explained_by_a_signal() -> None:
    inputs = TrustInputs(**STRONG_PROFILE)
    business = business_rules(inputs)
    assert business.score == min(100, w.BUSINESS_BASE + sum(s.points for s in business.signals))
    product, _ = product_rules(inputs)
    assert product.score == w.NEUTRAL + sum(s.points for s in product.signals)


# --- New / empty stores --------------------------------------------------------------
def test_new_store_without_evidence_is_caution_not_high_risk() -> None:
    result = calculate(TrustInputs())
    assert (result.business.score, result.product.score, result.transaction.score) == (10, 50, 50)
    assert result.overall == 34
    # Missing evidence is not negative evidence: never labelled HIGH_RISK on that basis alone.
    assert result.level == "CAUTION"
    assert {"BUSINESS_NOT_VERIFIED", "NO_POLICIES", "NEW_ON_PLATFORM", "NO_ACTIVE_PRODUCTS",
            "LIMITED_TRANSACTION_HISTORY"} <= codes(result.signals)  # fmt: skip


def test_verified_store_without_orders_is_developing() -> None:
    result = calculate(TrustInputs(**STRONG_PROFILE))
    assert result.business.score == 100
    assert result.overall >= w.DEVELOPING_BELOW  # high score...
    assert result.level == "DEVELOPING"  # ...but "trusted" must be earned through transactions


def test_unverified_store_with_good_orders_is_trusted_not_verified() -> None:
    profile = {**STRONG_PROFILE, "verification_status": "UNVERIFIED", "contact_verified": False}
    result = calculate(TrustInputs(**profile, transactions=GOOD_ORDERS))
    assert result.level == "TRUSTED"


def test_verified_store_with_strong_history_reaches_verified_level() -> None:
    result = calculate(TrustInputs(**STRONG_PROFILE, transactions=GOOD_ORDERS))
    assert result.overall >= w.VERIFIED_LEVEL_MIN_SCORE
    assert result.level == "VERIFIED"


@pytest.mark.parametrize("orders", [5, 9])
def test_verified_level_needs_enough_orders(orders: int) -> None:
    stats = TransactionStats(
        completed_orders=orders, verified_review_count=5, verified_review_average=5.0
    )
    result = calculate(TrustInputs(**STRONG_PROFILE, transactions=stats))
    assert result.level in ("TRUSTED", "DEVELOPING")


# --- Business rules --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("status", "code", "kind"),
    [
        ("VERIFIED", "BUSINESS_VERIFIED", "POSITIVE"),
        ("PENDING", "VERIFICATION_PENDING", "INFO"),
        ("REJECTED", "VERIFICATION_NOT_APPROVED", "RISK"),
        ("UNVERIFIED", "BUSINESS_NOT_VERIFIED", "RISK"),
    ],
)
def test_verification_signals(status: str, code: str, kind: str) -> None:
    signal = next(
        s for s in business_rules(TrustInputs(verification_status=status)).signals if s.code == code
    )
    assert signal.kind == kind


def test_provenance_separates_facts_from_seller_claims() -> None:
    by_code = {s.code: s for s in business_rules(TrustInputs(**STRONG_PROFILE)).signals}
    assert by_code["BUSINESS_VERIFIED"].provenance == "VERIFIED_FACT"
    assert by_code["BUSINESS_VERIFIED"].evidence_ids == ("v1",)
    assert by_code["CONTACT_CONFIRMED"].provenance == "VERIFIED_FACT"
    # Policies and profile text are the seller's own statements.
    assert by_code["POLICIES_PUBLISHED"].provenance == "SELLER_CLAIM"
    assert by_code["PROFILE_COMPLETE"].provenance == "SELLER_CLAIM"
    assert by_code["PLATFORM_TENURE"].provenance == "PLATFORM_STATISTIC"


@pytest.mark.parametrize(
    ("count", "points"), [(1, w.SOCIAL_ONE), (2, w.SOCIAL_TWO_OR_MORE), (5, w.SOCIAL_TWO_OR_MORE)]
)
def test_social_accounts_points(count: int, points: int) -> None:
    signal = next(
        s
        for s in business_rules(TrustInputs(confirmed_social_accounts=count)).signals
        if s.code == "SOCIAL_ACCOUNTS_CONFIRMED"
    )
    assert signal.points == points and signal.params == {"count": count}


@pytest.mark.parametrize(
    ("days", "code", "points"),
    [(10, "NEW_ON_PLATFORM", 0), (120, "PLATFORM_TENURE", 5), (500, "PLATFORM_TENURE", 10)],
)
def test_tenure(days: int, code: str, points: int) -> None:
    signal = next(
        s for s in business_rules(TrustInputs(account_age_days=days)).signals if s.code == code
    )
    assert signal.points == points


def test_misleading_evidence_caps_level_regardless_of_score() -> None:
    one = calculate(
        TrustInputs(
            **{**STRONG_PROFILE, "misleading_evidence_ids": ("m1",)}, transactions=GOOD_ORDERS
        )
    )
    assert one.level == "CAUTION"
    assert "MISLEADING_EVIDENCE" in codes(one.signals)
    two = calculate(
        TrustInputs(
            **{**STRONG_PROFILE, "misleading_evidence_ids": ("m1", "m2")}, transactions=GOOD_ORDERS
        )
    )
    assert two.level == "HIGH_RISK"
    penalty = next(s for s in two.business.signals if s.code == "MISLEADING_EVIDENCE")
    assert penalty.points == w.MISLEADING_EVIDENCE_MAX


def test_suspended_store_is_always_high_risk() -> None:
    result = calculate(
        TrustInputs(**{**STRONG_PROFILE, "sme_status": "SUSPENDED"}, transactions=GOOD_ORDERS)
    )
    assert result.level == "HIGH_RISK"


# --- Product rules --------------------------------------------------------------------
@pytest.mark.parametrize(
    ("product", "expected"),
    [
        (ProductEvidence("p"), "UNVERIFIED"),
        (ProductEvidence("p", accepted_image_ids=("i",)), "PARTIALLY_VERIFIED"),
        (ProductEvidence("p", accepted_document_ids=("d",)), "VERIFIED"),
        (ProductEvidence("p", accepted_document_ids=("d",), accepted_image_ids=("i",)), "VERIFIED"),
        # A misleading finding outweighs any accepted evidence.
        (ProductEvidence("p", accepted_document_ids=("d",), misleading_ids=("m",)), "CONCERN"),
    ],
)
def test_product_authenticity(product: ProductEvidence, expected: str) -> None:
    assert product_authenticity(product) == expected


def test_product_score_is_mean_of_active_products() -> None:
    inputs = TrustInputs(
        products=(
            ProductEvidence("verified", accepted_document_ids=("d",)),
            ProductEvidence("concern", misleading_ids=("m",)),
            ProductEvidence("hidden", accepted_document_ids=("x",), active=False),
        )
    )
    result, statuses = product_rules(inputs)
    assert result.score == 50  # (100 + 0) / 2; the hidden product is not counted
    assert statuses == {"verified": "VERIFIED", "concern": "CONCERN", "hidden": "VERIFIED"}
    assert {"PRODUCTS_AUTHENTICITY_VERIFIED", "PRODUCT_AUTHENTICITY_CONCERN"} == codes(
        result.signals
    )


# --- Transaction rules -----------------------------------------------------------------
def test_few_orders_stay_close_to_neutral() -> None:
    one = transaction_rules(TransactionStats(completed_orders=1))
    assert one.score == 55  # 50 + 50 * 1/11
    assert "LIMITED_TRANSACTION_HISTORY" in codes(one.signals)
    many = transaction_rules(TransactionStats(completed_orders=190))
    assert many.score == 98


def test_delivery_problems_lower_transaction_trust() -> None:
    clean = transaction_rules(TransactionStats(completed_orders=50))
    troubled = transaction_rules(
        TransactionStats(
            completed_orders=50, failed_deliveries=10, late_deliveries=20, seller_cancellations=5
        )
    )
    assert troubled.score < clean.score
    assert {"DELIVERY_FAILURES", "LATE_DELIVERIES", "SELLER_CANCELLATIONS"} <= codes(
        troubled.signals
    )


def test_transaction_score_never_leaves_range() -> None:
    worst = transaction_rules(
        TransactionStats(
            completed_orders=1000,
            failed_deliveries=1000,
            late_deliveries=1000,
            seller_cancellations=1000,
            upheld_complaints=50,
            overdue_unresolved_complaints=50,
            verified_review_count=100,
            verified_review_average=1.0,
        )
    )
    assert 0 <= worst.score < w.NEUTRAL


def test_upheld_complaints_cap_level() -> None:
    stats = TransactionStats(completed_orders=60, upheld_complaints=2, upheld_complaints_90d=2)
    assert calculate(TrustInputs(**STRONG_PROFILE, transactions=stats)).level == "CAUTION"
    stats = TransactionStats(completed_orders=60, upheld_complaints=3, upheld_complaints_90d=3)
    assert calculate(TrustInputs(**STRONG_PROFILE, transactions=stats)).level == "HIGH_RISK"


def test_reviews_need_minimum_count() -> None:
    few = transaction_rules(
        TransactionStats(completed_orders=20, verified_review_count=2, verified_review_average=1.0)
    )
    assert "VERIFIED_REVIEW_RATING" not in codes(few.signals)
    bad = transaction_rules(
        TransactionStats(completed_orders=20, verified_review_count=10, verified_review_average=1.5)
    )
    rating = next(s for s in bad.signals if s.code == "VERIFIED_REVIEW_RATING")
    assert rating.kind == "RISK" and rating.points < 0


# --- Explanations & history ---------------------------------------------------------------
def _out(signals) -> list[TrustSignalOut]:
    return [
        TrustSignalOut(dimension=s.dimension, kind=s.kind, code=s.code, points=s.points,
                       provenance=s.provenance, params=s.params, evidence_count=len(s.evidence_ids))
        for s in signals
    ]  # fmt: skip


def test_improvement_suggestions() -> None:
    new_store = {s.code for s in improvement_suggestions(_out(calculate(TrustInputs()).signals))}
    assert {"GET_VERIFIED", "CONFIRM_SOCIAL_ACCOUNT", "PUBLISH_POLICIES", "COMPLETE_PROFILE",
            "ADD_PRODUCTS", "BUILD_TRANSACTION_HISTORY"} == new_store  # fmt: skip

    partial = TrustInputs(published_policies=("returns",), products=(ProductEvidence("p"),))
    suggestions = {s.code: s for s in improvement_suggestions(_out(calculate(partial).signals))}
    assert suggestions["PUBLISH_POLICIES"].params == {"missing": ["refunds", "delivery"]}
    assert suggestions["ADD_PRODUCT_EVIDENCE"].params == {"count": 1}

    strong = {
        s.code
        for s in improvement_suggestions(
            _out(calculate(TrustInputs(**STRONG_PROFILE, transactions=GOOD_ORDERS)).signals)
        )
    }
    assert strong == set()


def test_history_summary() -> None:
    now = datetime.now(UTC)
    rows = [
        {"overall_score": 82, "level": "TRUSTED", "created_at": now - timedelta(days=10)},
        {"overall_score": 72, "level": "DEVELOPING", "created_at": now - timedelta(days=2)},
    ]
    baseline = {"overall_score": 91, "level": "VERIFIED", "created_at": now - timedelta(days=60)}
    out = summarize(rows, baseline, 30)
    assert (out.change.from_score, out.change.to_score) == (91, 72)
    assert (out.change.from_level, out.change.to_level) == ("VERIFIED", "DEVELOPING")
    assert [p.overall_score for p in out.points] == [82, 72]

    unchanged = summarize([], baseline, 30)
    assert (unchanged.change.from_score, unchanged.change.to_score) == (91, 91)
    assert summarize([], None, 30).change is None
