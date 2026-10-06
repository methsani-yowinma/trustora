"""Trust engine across evidence combinations (brief: "test different evidence combinations").

Every combination of verification state, social proof, product evidence, transaction history,
verified findings and open allegations (6 × 2 × 4 × 4 × 3 × 2 = 1,152 profiles) is scored, and
the invariants Trustora promises users are checked on every one.
"""

import itertools
from dataclasses import replace

import pytest

from app.trust.models import ProductEvidence, TransactionStats, TrustInputs, TrustResult
from app.trust.trust_calculator import calculate

SEVERITY = {"VERIFIED": 0, "TRUSTED": 1, "DEVELOPING": 2, "CAUTION": 3, "HIGH_RISK": 4}

VERIFICATION = {
    "unverified": dict(verification_status="UNVERIFIED"),
    "pending": dict(verification_status="PENDING"),
    "verified": dict(verification_status="VERIFIED", verification_evidence_ids=("v1",), contact_verified=True),
    "rejected": dict(verification_status="REJECTED"),
    "misleading_doc": dict(verification_status="REJECTED", misleading_evidence_ids=("m1",)),
    "suspended": dict(verification_status="VERIFIED", verification_evidence_ids=("v1",), sme_status="SUSPENDED"),
}  # fmt: skip
SOCIAL = {"none": 0, "two_confirmed": 2}
PRODUCTS = {
    "none": (),
    "documented": (ProductEvidence("p1", accepted_document_ids=("d1",)),),
    "unverified": (ProductEvidence("p1"),),
    "concern": (ProductEvidence("p1", upheld_authenticity_complaints=1),),
}
HISTORY = {
    "new": TransactionStats(),
    "good": TransactionStats(completed_orders=40, verified_review_count=12, verified_review_average=4.6),
    "few": TransactionStats(completed_orders=3),
    "poor": TransactionStats(completed_orders=20, failed_deliveries=6, late_deliveries=5, seller_cancellations=4),
}  # fmt: skip
UPHELD = {"none": 0, "one": 1, "three_recent": 3}
OPEN_ALLEGATIONS = {"none": 0, "five": 5}

GRID = list(itertools.product(VERIFICATION, SOCIAL, PRODUCTS, HISTORY, UPHELD, OPEN_ALLEGATIONS))


def build(
    verification: str, social: str, products: str, history: str, upheld: str, open_: str
) -> TrustInputs:
    stats = replace(
        HISTORY[history],
        upheld_complaints=UPHELD[upheld],
        upheld_complaints_90d=UPHELD[upheld],
        open_complaints=OPEN_ALLEGATIONS[open_],
    )
    return TrustInputs(
        **VERIFICATION[verification],
        confirmed_social_accounts=SOCIAL[social],
        social_evidence_ids=tuple(f"s{i}" for i in range(SOCIAL[social])),
        published_policies=("returns", "delivery"),
        has_logo=True,
        has_description=True,
        account_age_days=200,
        products=PRODUCTS[products],
        transactions=stats,
    )


def signals(result: TrustResult):
    return result.business.signals + result.product.signals + result.transaction.signals


@pytest.fixture(scope="module")
def results() -> dict[tuple[str, ...], TrustResult]:
    return {combo: calculate(build(*combo)) for combo in GRID}


def test_grid_size() -> None:
    assert len(GRID) == 1152


def test_scores_stay_in_range_and_are_deterministic(results: dict) -> None:
    for combo, result in results.items():
        for score in (
            result.overall,
            result.business.score,
            result.product.score,
            result.transaction.score,
        ):
            assert 0 <= score <= 100, combo
        assert calculate(build(*combo)) == result, combo


def test_verified_level_requires_a_verified_business_and_clean_record(results: dict) -> None:
    for (verification, _, products, _, upheld, _), result in results.items():
        if result.level == "VERIFIED":
            assert verification == "verified", verification
            assert upheld != "three_recent" and products != "concern"


def test_high_risk_is_only_shown_for_negative_findings(results: dict) -> None:
    """Missing evidence alone is CAUTION at worst; HIGH_RISK needs a real negative finding."""
    for combo, result in results.items():
        if result.level == "HIGH_RISK":
            assert any(s.points < 0 for s in signals(result)) or combo[0] == "suspended", combo


def test_hard_caps(results: dict) -> None:
    for (verification, *_rest), result in results.items():
        upheld = _rest[3]
        if verification == "suspended" or upheld == "three_recent":
            assert result.level == "HIGH_RISK", (verification, upheld)
        elif verification == "misleading_doc":
            assert SEVERITY[result.level] >= SEVERITY["CAUTION"]


def test_open_allegations_never_change_score_or_level(results: dict) -> None:
    for combo, result in results.items():
        if combo[-1] == "five":
            baseline = results[(*combo[:-1], "none")]
            assert (result.overall, result.level) == (baseline.overall, baseline.level), combo
            allegation = [s for s in signals(result) if s.code == "OPEN_COMPLAINTS"]
            assert allegation and allegation[0].points == 0
            assert allegation[0].provenance == "CUSTOMER_ALLEGATION"


@pytest.mark.parametrize(
    ("position", "worse", "better"),
    [
        (0, "unverified", "verified"),
        (0, "rejected", "verified"),
        (1, "none", "two_confirmed"),
        (2, "unverified", "documented"),
        (2, "concern", "unverified"),
        (3, "poor", "good"),
        (4, "one", "none"),
        (4, "three_recent", "one"),
    ],
)
def test_better_evidence_never_lowers_trust(
    results: dict, position: int, worse: str, better: str
) -> None:
    """Monotonicity: improving one kind of evidence, all else equal, never lowers score or level."""
    for combo, result in results.items():
        if combo[position] != worse or combo[0] == "suspended":
            continue
        improved = results[(*combo[:position], better, *combo[position + 1 :])]
        assert improved.overall >= result.overall, (combo, better)
        assert SEVERITY[improved.level] <= SEVERITY[result.level], (combo, better)


def test_product_authenticity_comes_only_from_reviewed_evidence(results: dict) -> None:
    expected = {
        "none": None,
        "documented": "VERIFIED",
        "unverified": "UNVERIFIED",
        "concern": "CONCERN",
    }
    for combo, result in results.items():
        want = expected[combo[2]]
        if want is not None:
            assert result.product_authenticity["p1"] == want, combo


def test_every_signal_is_labelled_with_its_source(results: dict) -> None:
    allowed = {
        "VERIFIED_FACT",
        "SELLER_CLAIM",
        "CUSTOMER_ALLEGATION",
        "PUBLIC_EVIDENCE",
        "PLATFORM_STATISTIC",
    }
    for combo, result in results.items():
        for signal in signals(result):
            assert signal.provenance in allowed, (combo, signal.code)
            assert signal.provenance != "AI_ANALYSIS"  # AI never contributes to the score
