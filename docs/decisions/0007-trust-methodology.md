# ADR 0007 — Trust methodology (rules version 2026.10-3)

**Status:** Accepted (Phase 4). Parameters live in `backend/app/trust/trust_weights.py`.

## Pipeline

```text
collect_inputs (DB) → trust_rules (pure) → trust_calculator → trust_scores + trust_signals
                                                            → trust_score_history (if changed) + audit
```

Recalculation runs inside the transaction of every change that affects trust (verification and
social-account decisions, evidence review, storefront edits, product changes) and is serialized
per SME with a row lock. No AI is involved.

## Dimensions

Every dimension score is `clamp(base + Σ signal.points)`, so each point is traceable to a signal
with a code, a provenance (verified fact, seller claim, platform statistic, …) and evidence.

| Dimension | Base | Main signals |
| --------- | ---- | ------------ |
| Business | 10 | verified business +40 · contact confirmed +15 · confirmed social 1→+10, 2+→+15 · each policy +5 (seller claim) · tenure ≥90d +5, ≥365d +10 · complete profile +5 · misleading evidence −25 each (max −50) · suspended −50 |
| Product | 50 | mean over **active** products of VERIFIED 100 · PARTIALLY_VERIFIED 75 · UNVERIFIED 50 · CONCERN 0 |
| Transaction | 50 | observed performance = success rate over seller-attributable outcomes (completed, failed deliveries, seller cancellations) × 100, minus late-delivery penalty, ± verified rating (≥ 3 reviews); blended toward 50 by `n / (n + 10)` outcomes. **Plus, in full:** upheld complaints −10 each (max −40, verified facts) and complaints without a seller response for 14 days −5 each (max −20). Open complaints: 0 points (customer allegations, shown as INFO) |

Overall = 0.40 · Business + 0.25 · Product + 0.35 · Transaction.

**Product authenticity** is derived from admin-reviewed evidence only: an accepted document
(invoice, certificate) → VERIFIED; only an accepted photo → PARTIALLY_VERIFIED; any evidence
rejected as *misleading*, or an upheld product-authenticity complaint → CONCERN; otherwise UNVERIFIED.

## Levels

| Level | Rule |
| ----- | ---- |
| HIGH_RISK | score < 40 **and** at least one negative finding (a signal with negative points); or suspended; or ≥ 2 misleading findings; or ≥ 3 upheld complaints in 90 days |
| CAUTION | score 40–54; or score < 40 with no negative findings (missing evidence ≠ negative evidence); capped here by 1 misleading finding or 2 upheld complaints in 90 days |
| DEVELOPING | score 55–69; or ≥ 70 with fewer than 5 completed orders |
| TRUSTED | score ≥ 70 and ≥ 5 completed orders |
| VERIFIED | TRUSTED + verified business + score ≥ 85 + ≥ 10 completed orders |

Changes from the Phase 1 sketch, made while implementing:
- A brand-new store with no evidence lands on CAUTION, not HIGH_RISK.
- A rejected verification carries 0 points (it may only mean an illegible scan); forged documents
  are flagged as misleading by the admin, which is a verified negative finding.
- 2026.10-2 (Phase 5): the transaction sample counts every seller-attributable outcome, not only
  completed orders, so failed deliveries and seller cancellations are visible (and lower the score)
  even before a seller's first completed order.
- 2026.10-3 (Phase 6): complaint findings are no longer scaled by order volume (a verified finding
  weighs the same for a small seller); open complaints are displayed as allegations but never
  scored; upheld authenticity complaints mark products as CONCERN. Passports older than one hour
  are recalculated on view so time-based inputs (tenure, 14-day response window) stay current.

## Consequences

- Until commerce data exists (Phases 5–6), every store has "limited transaction history" and
  can reach at most DEVELOPING.
- Changing any weight requires bumping `RULES_VERSION`; each score and history row records it.
