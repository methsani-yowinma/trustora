"""Deterministic explanation helpers (no AI).

The public "Why should I trust this business?" answer is the stored signal list itself. This
module adds improvement suggestions for the SME, derived from the same signals.
(Gemini-written natural-language summaries are added in Phase 7, on top of these signals.)
"""

from collections.abc import Iterable

from app.trust.schemas import Suggestion, TrustSignalOut
from app.trust.trust_inputs import POLICY_KEYS


def improvement_suggestions(signals: Iterable[TrustSignalOut]) -> list[Suggestion]:
    by_code = {s.code: s for s in signals}
    suggestions: list[Suggestion] = []

    if {"UNRESOLVED_COMPLAINTS", "OPEN_COMPLAINTS"} & by_code.keys():
        suggestions.append(Suggestion(code="RESPOND_TO_COMPLAINTS"))
    if "MISLEADING_EVIDENCE" in by_code:
        suggestions.append(Suggestion(code="RESOLVE_MISLEADING_EVIDENCE"))
    if {"BUSINESS_NOT_VERIFIED", "VERIFICATION_NOT_APPROVED"} & by_code.keys():
        suggestions.append(Suggestion(code="GET_VERIFIED"))
    if "SOCIAL_ACCOUNTS_CONFIRMED" not in by_code:
        suggestions.append(Suggestion(code="CONFIRM_SOCIAL_ACCOUNT"))

    published = by_code.get("POLICIES_PUBLISHED")
    missing = [
        k for k in POLICY_KEYS if not published or k not in published.params.get("policies", [])
    ]
    if missing:
        suggestions.append(Suggestion(code="PUBLISH_POLICIES", params={"missing": missing}))

    if "PROFILE_COMPLETE" not in by_code:
        suggestions.append(Suggestion(code="COMPLETE_PROFILE"))
    if "NO_ACTIVE_PRODUCTS" in by_code:
        suggestions.append(Suggestion(code="ADD_PRODUCTS"))
    if unverified := by_code.get("PRODUCTS_WITHOUT_AUTHENTICITY_EVIDENCE"):
        suggestions.append(
            Suggestion(
                code="ADD_PRODUCT_EVIDENCE", params={"count": unverified.params.get("count", 0)}
            )
        )
    if "LIMITED_TRANSACTION_HISTORY" in by_code:
        suggestions.append(Suggestion(code="BUILD_TRANSACTION_HISTORY"))
    return suggestions
