"""Combines dimension results into the overall score and trust level."""

from app.trust import trust_weights as w
from app.trust.models import Level, Signal, TrustInputs, TrustResult
from app.trust.trust_rules import business_rules, clamp, product_rules, transaction_rules

_SEVERITY: dict[Level, int] = {
    "VERIFIED": 0,
    "TRUSTED": 1,
    "DEVELOPING": 2,
    "CAUTION": 3,
    "HIGH_RISK": 4,
}


def _worse(a: Level, b: Level) -> Level:
    return a if _SEVERITY[a] >= _SEVERITY[b] else b


def determine_level(overall: int, inputs: TrustInputs, signals: tuple[Signal, ...] = ()) -> Level:
    tx = inputs.transactions
    misleading = len(inputs.misleading_evidence_ids)

    # HIGH_RISK describes negative evidence. A low score caused only by *missing* evidence
    # (e.g. a brand-new, unverified store) is shown as CAUTION instead.
    has_negative_findings = any(s.points < 0 for s in signals)
    if overall < w.HIGH_RISK_BELOW:
        level: Level = "HIGH_RISK" if has_negative_findings else "CAUTION"
    elif overall < w.CAUTION_BELOW:
        level = "CAUTION"
    elif overall < w.DEVELOPING_BELOW:
        level = "DEVELOPING"
    else:
        level = "TRUSTED"

    # "Trusted" must be earned through real transactions, not profile completeness alone.
    if level == "TRUSTED" and tx.completed_orders < w.LIMITED_HISTORY_ORDERS:
        level = "DEVELOPING"
    if (
        level == "TRUSTED"
        and inputs.verification_status == "VERIFIED"
        and overall >= w.VERIFIED_LEVEL_MIN_SCORE
        and tx.completed_orders >= w.VERIFIED_LEVEL_MIN_ORDERS
    ):
        level = "VERIFIED"

    # Hard caps: serious verified findings override a high score.
    if inputs.sme_status == "SUSPENDED":
        return "HIGH_RISK"
    if (
        misleading >= w.HIGH_RISK_CAP_MISLEADING
        or tx.upheld_complaints_90d >= w.HIGH_RISK_CAP_UPHELD_90D
    ):
        return _worse(level, "HIGH_RISK")
    if (
        misleading >= w.CAUTION_CAP_MISLEADING
        or tx.upheld_complaints_90d >= w.CAUTION_CAP_UPHELD_90D
    ):
        return _worse(level, "CAUTION")
    return level


def calculate(inputs: TrustInputs) -> TrustResult:
    business = business_rules(inputs)
    product, authenticity = product_rules(inputs)
    transaction = transaction_rules(inputs.transactions)

    overall = clamp(
        business.score * w.DIMENSION_WEIGHTS["BUSINESS"]
        + product.score * w.DIMENSION_WEIGHTS["PRODUCT"]
        + transaction.score * w.DIMENSION_WEIGHTS["TRANSACTION"]
    )
    return TrustResult(
        overall=overall,
        level=determine_level(
            overall, inputs, business.signals + product.signals + transaction.signals
        ),
        business=business,
        product=product,
        transaction=transaction,
        product_authenticity=authenticity,
        rules_version=w.RULES_VERSION,
    )
