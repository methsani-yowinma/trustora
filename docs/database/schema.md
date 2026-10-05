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

## Access matrix (enforced by grants + RLS)

| Table | anon | authenticated (self) | authenticated (admin) |
| ----- | ---- | -------------------- | --------------------- |
| profiles | — | select/update own row (`full_name`, `phone`, `preferred_locale`) | select/update all, incl. `role`, `status` |
| audit_logs | — | — | select |

No client role can insert or delete profiles or write audit logs.
These rules are covered by `backend/tests/test_rls.py`.
