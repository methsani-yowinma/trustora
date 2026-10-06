# ADR 0010 — Domain tables are reachable only through the Trustora API

**Status:** Accepted (Phase 9)

## Context
ADR 0002 runs every API request inside a transaction as the Supabase role `authenticated` (or
`anon` for public reads) so that RLS also guards the backend's own queries. Supabase's Data API
(PostgREST, GraphQL, Realtime) uses the same roles, so every grant made for the backend is also
available to any browser holding a session.

Column privileges apply per role, not per row. `authenticated` needs, for example,
`reviews.customer_id` to find a customer's own reviews, but RLS also lets it read reviews of
public stores. The result: a signed-in user could read reviewer ids, verification codes and owner
ids directly. The Phase 9 review found this and verified it with a test.

## Options considered
1. **Narrower column grants.** This breaks backend queries that legitimately need those columns.
2. **A separate database role for the backend** with all policies rewritten. That is safe but a
   large migration that changes ADR 0002.
3. **Disable the Data API in the Supabase dashboard.** This is effective, but it is a manual
   setting and invisible in code and tests.
4. **A restrictive policy keyed to a backend-only transaction setting.** Chosen.

## Decision
- Every table in `public` gets
  `create policy api_only … as restrictive for all to anon, authenticated using/with check
  (current_setting('trustora.api', true) = 'on')`.
- `Database.user_transaction` and `anon_transaction` set `trustora.api = 'on'` (transaction-local).
- Restrictive policies are AND-ed with the existing permissive ones, so nothing about API
  authorization changes. Direct Data API requests see no rows and cannot insert, update or
  delete.
- Clients cannot set `trustora.api`. PostgREST only sets `role` and `request.*` settings, and no
  exposed function calls `set_config`.
- RLS helper functions move to a `private` schema that the Data API doesn't expose, which removes
  them as RPC endpoints.
- `test_every_table_requires_the_api_path` fails if a future table lacks the policy.
- Disabling the Data API in the dashboard (option 3) is still recommended as an extra layer.

## Consequences
- The browser can no longer read domain tables through Supabase JS. This was already the rule
  (ADR 0002), so nothing breaks.
- Backend code that needs privileged access keeps using `Database.privileged` or
  `system_transaction` (table owner, which bypasses RLS).
- Tests that simulate requests set the flag (`as_role(..., via_api=True)`). `via_api=False`
  simulates a direct Data API client.
