# ADR 0003 — Verifying Supabase access tokens in FastAPI

**Status:** Accepted (Phase 2)

## Decision
- Tokens signed with Supabase JWT signing keys (ES256/RS256) are verified against
  `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` (keys cached for 10 minutes).
- Legacy HS256 tokens are accepted **only** if `SUPABASE_JWT_SECRET` is configured.
- Required claims: `exp`, `iat`, `sub`, `aud = authenticated`, `iss = {SUPABASE_URL}/auth/v1`,
  and `role = authenticated`. `alg: none` and unknown algorithms are rejected.
- The user's role and account status are read from `public.profiles` on every request —
  never from token metadata, which users can edit. Suspended accounts receive 403.

## Consequences
- One optional environment variable (`SUPABASE_JWT_SECRET`) beyond the Phase 1 list, needed
  only by projects that have not migrated to signing keys.
- An unreachable JWKS endpoint returns 503 (not 401), so outages are not mistaken for logouts.
