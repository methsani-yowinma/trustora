# Database schema

Source of truth: `supabase/migrations/*.sql`. This page summarises what exists so far.

## Phase 2 — foundation (`20261005000000_foundation.sql`)

### `public.profiles` (1:1 with `auth.users`)

| Column | Type | Notes |
| ------ | ---- | ----- |
| `id` | uuid PK | FK → `auth.users.id`, cascade delete |
| `role` | `user_role` | `CUSTOMER` \| `SME` \| `ADMIN`, default CUSTOMER |
| `status` | `account_status` | `ACTIVE` \| `SUSPENDED` |
| `full_name` | text | 1–120 chars |
| `phone` | text | `^\+?[0-9 ]{7,20}$` |
| `preferred_locale` | text | `en` \| `si` |
| `created_at`, `updated_at` | timestamptz | `updated_at` maintained by trigger |

Triggers:
- `on_auth_user_created` (on `auth.users`): creates the profile. Signup metadata may request
  `SME`; anything else (including `ADMIN`) becomes `CUSTOMER`.
- `profiles_protect_privileges`: `role`/`status` changes by `anon`/`authenticated` require an
  active admin.

### `public.audit_logs` (append-only)

`id`, `actor_id` → profiles, `actor_role`, `action` (`module.verb`, e.g. `sme.verified`),
`target_type`, `target_id`, `metadata` jsonb, `created_at`. Update/delete raise an error for
every role. Written only by the backend (`app/audit/service.py`).

### Helper

`public.is_admin()` — security definer; true when the caller is an ACTIVE admin.

## Phase 3 — SMEs, stores, verification, evidence, products (`20261006000000_sme_store_products.sql`)

| Table | Purpose / key rules |
| ----- | ------------------- |
| `smes` | One per SME account (`owner_id` unique). Storefront fields, `slug` (immutable), localized `description_i18n` / `policies_i18n`, `verification_status`, `contact_verified`, `is_published`, `status`. Trigger `protect_sme_fields`: owners cannot change slug, logo path, verification, status, or set contact-verified; changing contact details always clears `contact_verified`. |
| `sme_social_accounts` | Linked Instagram/Facebook/TikTok/WhatsApp accounts with a `TRUSTORA-XXXXXX` code placed in the bio; `ownership_verified` set only by admins. |
| `business_verifications` | Verification applications (`SUBMITTED` → `APPROVED`/`REJECTED`); at most one open per SME (partial unique index). |
| `evidence` | Integrity-hashed (SHA-256) evidence with `type`, `provenance` (verified fact / seller claim / customer allegation / …), `review_status`, `availability` (`AVAILABLE` / `PREVIOUSLY_OBSERVED`). Written only by the backend. |
| `categories` | Seeded reference data with English and Sinhala names. |
| `products` | `name_i18n`, `description_i18n`, `price_lkr numeric(12,2) > 0`, `stock >= 0`, `status` (`ACTIVE`/`HIDDEN`/`REMOVED` — removal is soft), `authenticity_status` (default `UNVERIFIED`; owners cannot set it). |
| `product_images` | Public images (path + SHA-256), written only by the backend. |

Helpers: `is_localized_text(jsonb, max)` (keys within {en, si}, non-empty strings), `has_active_role`, `owns_sme`, `is_public_sme`, `product_sme`.

Storage buckets (created by the migration; no client policies on `storage.objects`):
`public-media` (public URLs; images up to 5 MB) and `private-evidence` (signed URLs only; images/PDF up to 10 MB).

## Phase 4 — Trust engine (`20261007000000_trust_engine.sql`)

| Table | Purpose / key rules |
| ----- | ------------------- |
| `trust_scores` | Current score per SME: overall, level, three dimension scores, `rules_version`, aggregate `evidence_summary` (counts only), `computed_at`. |
| `trust_signals` | The explanation behind the current score: dimension, kind (`POSITIVE`/`RISK`/`INFO`), code, points, provenance, params, evidence ids. Replaced on each recalculation. |
| `trust_score_history` | Append-only: one row per change of score or level, with the `trigger` that caused it. Rows are only removed with their SME. |
| `evidence.flagged_misleading` | Admin finding that rejected evidence is forged or mismatched (a verified risk finding). |

All three trust tables are readable for public stores (anon), by the owning SME and by admins.
No client role has any write grant: only the backend trust engine writes them.

## Phase 5 — Commerce (`20261008000000_commerce.sql`)

| Table | Purpose / key rules |
| ----- | ------------------- |
| `orders` | One SME per order. `order_number` (`TR-XXXXXXXX`), status (`PLACED` → `CONFIRMED` → `DISPATCHED` → `DELIVERED` → `COMPLETED`, or `CANCELLED` / `DELIVERY_FAILED`), money totals with `total = subtotal + delivery fee`, shipping-address snapshot, payment method, per-customer unique `idempotency_key`, timestamps per step, `cancelled_by`. |
| `order_items` | Name and price snapshots, quantity 1–10, `line_total = unit_price × quantity`. |
| `payments` | Sandbox: `COD` (paid on delivery) or `MOCK_CARD` (paid at checkout, refunded on cancellation/failure). No card data. |
| `deliveries` | Provider abstraction (`SIMULATED`), district, fee, ETA days, tracking reference, estimated date and per-step timestamps, failure reason. |

Clients can only **read** orders they are a party to (customer, the SME, admins); every write goes
through the backend state machine.

## Phase 6 — Reviews and complaints (`20261009000000_reviews_complaints.sql`)

| Table | Purpose / key rules |
| ----- | ------------------- |
| `reviews` | One per delivered order (`order_id` unique), rating 1–5, optional comment, one public SME response. Public readers never get `customer_id` (column grant). |
| `complaints` | Order-bound customer allegation: category, description, status `SUBMITTED` → `SME_RESPONDED` → (`UNDER_REVIEW`) → `RESOLVED` / `UPHELD` / `DISMISSED`; at most one open per order (partial unique index). Private to the customer, the SME and admins. |
| `evidence.complaint_id` | Complaint evidence: customer uploads are `CUSTOMER_ALLEGATION`, seller uploads `SELLER_CLAIM`; both parties can see it (`can_view_complaint`). |

The public complaint record (`GET /stores/{slug}/complaints/summary`) exposes only counts by
category and outcome — never complaint text or identities.

## Phase 7 — AI analyses (`20261010000000_ai_analyses.sql`)

| Table | Purpose / key rules |
| ----- | ------------------- |
| `ai_analyses` | Every Gemini result: `kind` (`COMPLAINT`, `REVIEW`, `DOCUMENT`, `TRUST_EXPLANATION`), `target_id`, `sme_id`, `locale`, `input_hash`, `model`, `prompt_version`, `status` (`DONE` / `FAILED` / `SKIPPED`), `output` (present only when `DONE`), `error_code`. Written by the backend only. Explanations are cached by a partial unique index on (`target_id`, `locale`, `input_hash`). |

AI results are advisory: no trigger, rule or query in the trust engine reads this table.

## Access matrix (enforced by grants + RLS)

| Table | anon | authenticated (self) | authenticated (admin) |
| ----- | ---- | -------------------- | --------------------- |
| profiles | — | select/update own row (`full_name`, `phone`, `preferred_locale`) | select/update all, incl. `role`, `status` |
| audit_logs | — | — | select |
| smes | safe columns of published, active stores | select own; insert own (SME role); update storefront fields | select/update all incl. verification |
| sme_social_accounts | verified accounts of public stores (no code) | select/delete own | update ownership |
| business_verifications | — | select own | select/update decision |
| evidence | — | select own | select/update review |
| products | active products of public stores | select/insert/update own (not authenticity) | all |
| product_images | images of public products | select own | select |
| categories | select | select | select |
| trust_scores / trust_signals / trust_score_history | public stores | public stores + own | all (read only) |
| reviews | public-store reviews without reviewer id | own (customer) / own store (SME) | all |
| complaints | — | own (customer) / own store (SME) — read only | all (read only) |
| ai_analyses | — | — | select |
| orders / order_items / payments / deliveries | — | own orders (customer) or orders placed with own store (SME) — read only | all (read only) |

No client role can insert profiles, evidence, verifications, social accounts or images, or write audit logs.
These rules are covered by `backend/tests/test_rls.py` and `backend/tests/test_rls_sme.py`.
