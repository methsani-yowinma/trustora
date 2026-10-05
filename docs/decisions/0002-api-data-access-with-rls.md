# ADR 0002 — Data access through the API, with RLS enforced on backend queries

**Status:** Accepted (Phase 1), implemented in Phase 2

## Context
Supabase lets browsers query tables directly (PostgREST). Trustora's business rules (trust
calculation, order state machines, fact-vs-allegation handling) must not be bypassable.
The requirements also call for Row Level Security.

## Decision
- The browser uses Supabase JS **only for authentication**. All domain reads and writes go
  through FastAPI with the user's access token.
- FastAPI verifies the JWT, then runs each request in a transaction where
  `request.jwt.claims` is set and `role` is `authenticated` (`Database.user_transaction`).
  RLS policies (`auth.uid()`, `public.is_admin()`) therefore apply to backend queries too.
- Backend-only writes (audit logs, trust snapshots) run privileged — either in a
  `system_transaction` or via `Database.privileged(conn)` inside the user transaction,
  so they stay atomic with the action.
- Because anything granted to `authenticated` is reachable from the browser via PostgREST,
  migrations revoke Supabase's default grants and grant only privileges that are safe for
  direct client use under RLS.

## Consequences
- Two independent layers of authorization: service-layer checks and RLS.
- The backend connection role must be allowed to `SET ROLE authenticated` (true for
  Supabase's `postgres` role).
- Integration tests run the real migrations against an embedded PostgreSQL with a small
  Supabase shim (`backend/tests/sql/supabase_shim.sql`).
