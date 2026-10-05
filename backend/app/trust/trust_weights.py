"""Trust methodology parameters. Change values here (and bump RULES_VERSION) to re-weight.

Every stored score records the RULES_VERSION that produced it, so history stays interpretable.
"""

RULES_VERSION = "2026.10-2"

# Overall score = weighted mean of the three dimensions.
DIMENSION_WEIGHTS = {"BUSINESS": 0.40, "PRODUCT": 0.25, "TRANSACTION": 0.35}

NEUTRAL = 50  # "no evidence either way"

# --- Business trust (base + points, clamped to 0..100) -----------------------------
BUSINESS_BASE = 10
BUSINESS_VERIFIED = 40
# A rejection may just mean an illegible document; forged documents are flagged as misleading.
VERIFICATION_NOT_APPROVED = 0
CONTACT_CONFIRMED = 15
SOCIAL_ONE = 10
SOCIAL_TWO_OR_MORE = 15
POLICY_EACH = 5
TENURE_90_DAYS = 5
TENURE_365_DAYS = 10
PROFILE_COMPLETE = 5
MISLEADING_EVIDENCE_EACH = -25
MISLEADING_EVIDENCE_MAX = -50
ACCOUNT_SUSPENDED = -50

# --- Product trust (mean of per-product authenticity values) ------------------------
AUTHENTICITY_VALUE = {
    "VERIFIED": 100,
    "PARTIALLY_VERIFIED": 75,
    "UNVERIFIED": NEUTRAL,
    "CONCERN": 0,
}

# --- Transaction trust ---------------------------------------------------------------
# Observed performance is the success rate over seller-attributable outcomes (completed, failed,
# seller-cancelled), adjusted for late deliveries, complaints and ratings; it is then blended with
# NEUTRAL by sample size so a handful of orders cannot dominate: n / (n + PRIOR_ORDERS).
PRIOR_ORDERS = 10
# A failed delivery or seller cancellation removes its full share of the success rate.
FAILED_DELIVERY_RATE_WEIGHT = 100
LATE_DELIVERY_RATE_WEIGHT = 20
SELLER_CANCELLATION_RATE_WEIGHT = 100
UPHELD_COMPLAINT_EACH = -10
UPHELD_COMPLAINT_MAX = -40
OVERDUE_COMPLAINT_EACH = -5
OVERDUE_COMPLAINT_MAX = -20
MIN_REVIEWS_FOR_RATING = 3
RATING_POINTS_PER_STAR = 10  # relative to a 3-star midpoint: range -20..+20

# --- Levels ---------------------------------------------------------------------------
HIGH_RISK_BELOW = 40
CAUTION_BELOW = 55
DEVELOPING_BELOW = 70
VERIFIED_LEVEL_MIN_SCORE = 85
VERIFIED_LEVEL_MIN_ORDERS = 10
LIMITED_HISTORY_ORDERS = 5
CAUTION_CAP_MISLEADING = 1
HIGH_RISK_CAP_MISLEADING = 2
CAUTION_CAP_UPHELD_90D = 2
HIGH_RISK_CAP_UPHELD_90D = 3

TENURE_DAYS = (90, 365)
