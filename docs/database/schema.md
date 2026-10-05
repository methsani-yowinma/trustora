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

No client role can insert profiles, evidence, verifications, social accounts or images, or write audit logs.
These rules are covered by `backend/tests/test_rls.py` and `backend/tests/test_rls_sme.py`.
