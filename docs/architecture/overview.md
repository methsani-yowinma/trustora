# Trustora — Architecture Overview

Approved in Phase 1 (2026-10-05). This is the reference for all later phases.

## Product principle

Trustora is digital trust infrastructure for social commerce, not "a marketplace with a chatbot".

```text
Social business → Verification → Evidence → AI analysis → Trust Engine → Trust Passport
→ Customer decision → Purchase → Transaction outcome → Reviews / Complaints → Trust updated
```

Trust is evidence-based and dynamic. The platform always distinguishes **verified facts**,
**seller claims**, **customer allegations**, **public evidence**, **AI analysis** and
**platform statistics**, and never claims certainty.

## System shape — modular monolith

```text
Browser (Next.js, /en /si)
  │  Supabase JS: authentication only (session cookies)
  │  All domain data: HTTPS + Bearer JWT → FastAPI
  ▼
FastAPI  /api/v1
  core · auth · users · smes · products · orders · deliveries · reviews · complaints
  evidence · trust (deterministic) · ai (only Gemini caller) · audit
  ▼
Supabase: Postgres (+RLS) · Auth · Storage (public-media, private-evidence)
```

- **Two kinds of DB transaction** ([ADR 0002](../decisions/0002-api-data-access-with-rls.md)):
  user transactions run as `authenticated` with the caller's JWT claims (RLS applies);
  system transactions (trust recalculation, storage bookkeeping) run privileged.
- **Gemini never produces scores or makes authorization decisions** ([ADR 0004](../decisions/0004-deterministic-trust-engine.md)).
- Modules follow `router.py` (HTTP) → `service.py` (rules + SQL) → `schemas.py` (Pydantic contracts).

## Roles

`CUSTOMER`, `SME`, `ADMIN` only. Stored in `public.profiles.role` (never in user-editable JWT
metadata). Signup may request CUSTOMER or SME; ADMIN is assigned manually in the database.

## Planned data model (built incrementally, one phase at a time)

| Phase | Tables |
| ----- | ------ |
| 2 ✅ | `profiles`, `audit_logs` |
| 3 ✅ | `smes` (incl. storefront fields), `sme_social_accounts`, `business_verifications`, `evidence`, `categories`, `products`, `product_images` |
| 4 ✅ | `trust_scores`, `trust_score_history`, `trust_signals` |
| 5 ✅ | `orders`, `order_items`, `payments`, `deliveries` |
| 6 ✅ | `reviews`, `complaints` (+ `evidence.complaint_id`) |

The Trust Passport is a composed view (`smes` + `trust_scores` + `trust_signals`), not a table.

`evidence` moved from Phase 4 to Phase 3: verification documents and product authenticity
files are evidence from the moment they are uploaded.

## Phase 3 product decisions

- A store is public once the SME publishes it, verified or not; unverified stores show a clear
  "Not verified by Trustora" notice.
- Contact details are confirmed by the admin during verification (no SMS/OTP in the MVP);
  editing them afterwards clears the confirmation automatically (database trigger).
- Removing a product is a soft delete so future orders keep their history.
- Store addresses (slugs) are immutable after registration.
- Uploaded product evidence is a pending *seller claim* and never changes authenticity status
  by itself; admin review arrives with the Trust Engine in Phase 4.

## Trust Engine (Phase 4)

```text
collect_inputs → trust_rules (pure functions) → trust_calculator → persist + history + audit
                                                                  → optional Gemini explanation
```

Implemented as specified in [ADR 0007](../decisions/0007-trust-methodology.md) (rules, weights,
levels and the two refinements made during implementation).

Starting weights: Business 0.40 · Product 0.25 · Transaction 0.35, versioned in `trust_weights.py`.
New sellers are pulled toward a neutral 50 on transaction trust until they have enough history.
Levels: VERIFIED (admin-verified business, ≥85 and ≥10 completed orders) · TRUSTED ≥70 ·
DEVELOPING 55–69 or limited history · CAUTION 40–54 · HIGH_RISK <40. Two or more upheld
complaints in 90 days cap the level at CAUTION.

## Gemini (Phase 7)

```text
complaint / review created ──► background task ──► redact ──► Gemini (JSON schema) ──► ai_analyses
admin "Analyze with AI"   ──► SHA-256 check ──► Gemini ──► deterministic checks ──► ai_analyses
passport view              ──► facts ──► cache? ──► Gemini text ──► guard ──► (or template)
```

All calls go through `app/ai/gemini_client.py`. The key stays on the server, and results are
advisory and labelled `AI_ANALYSIS`. See [ADR 0008](../decisions/0008-gemini-integration.md).

## Trustora AI (Phase 8)

```text
browser ──POST /chat {recent turns, locale, page context}──► chatbot.py
   redact user text → Gemini (tools for this role only) ⇄ chat_tools.py (≤5 rounds)
        public tools: anon transaction · personal tools: caller's RLS transaction
   → guard reply (no absolute claims / credentials) → {reply, sources, draft?}
draft → customer confirms in the UI → POST /orders/{id}/complaints (normal endpoint)
```

See [ADR 0009](../decisions/0009-trustora-ai-chatbot.md).

## Approved MVP decisions

1. Frontend reads and writes domain data only through FastAPI; RLS still enforced per request.
2. Hosted Supabase project for development (no Docker requirement).
3. One SME per checkout (one order per store).
4. Payments: Cash on Delivery + mock card. Delivery providers simulated behind an interface.
5. Reviews and complaints require a Trustora order.
6. Social accounts: no scraping or API integration; ownership confirmed by a code in the bio,
   checked by an admin. Disappeared content is shown as "previously observed".
7. AI classifications never move trust scores; only admin-upheld complaints and
   admin-accepted evidence do.
8. Gemini: paid-tier key before real customer data; personal data never sent to Gemini.
9. Localized SME content stored as JSONB (`{"en": …, "si": …}`); no automatic translation.
10. Chatbot: stateless, non-streaming; complaints only via user-confirmed drafts.
11. LKR, Sri Lanka only.
12. No vector database until semantic search is shown to be needed (then pgvector).
