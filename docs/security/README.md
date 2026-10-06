# Trustora security review (Phase 9)

This document covers the Phase 9 review: what was checked, what was found and fixed, the controls
now in place, and the settings an operator must configure in Supabase and hosting. Every fix has a
regression test (`backend/tests/test_security.py`, `backend/tests/test_input_security.py`,
`frontend/e2e/security.spec.ts`).

## Findings and fixes

| # | Severity | Finding | Fix |
| - | -------- | ------- | --- |
| 1 | High | **Direct Data API access leaked private columns.** The backend runs queries as Supabase's `anon`/`authenticated` roles, and so does Supabase's auto-generated REST/GraphQL API. Column grants apply per role, not per row, so any signed-in user could call the REST API directly and read `reviews.customer_id`/`order_id` (reviewer identity), `sme_social_accounts.verification_code`/`verified_by` (admin ids) and `smes.owner_id` for every public store. This was verified with a test. | A restrictive RLS policy `api_only` on every table requires the transaction setting `trustora.api = 'on'`. Only the backend sets it. Direct Data API requests now see no rows and cannot write; all existing policies still apply to API requests. A test fails if a new table lacks the policy. [ADR 0010](../decisions/0010-api-only-database-access.md) |
| 2 | Medium | **RLS helper functions were callable as RPC endpoints** (`/rest/v1/rpc/is_admin`, `owns_sme`, `product_sme`, …), revealing for example the store behind any product id. | Moved to a non-exposed `private` schema. Policies keep working because they reference functions by OID. A test asserts that `public` holds only trigger functions and that every `SECURITY DEFINER` function pins `search_path`. |
| 3 | Medium | **Open redirect after sign-in.** `?next=/%09/evil.example` passed the check; browsers strip the tab and navigate to `//evil.example`. | `safeNextPath` rejects control characters and backslashes, then resolves the path and requires the same origin. |
| 4 | Medium | **Phishing link through a URL parser differential.** A social link `https://evil.example\@facebook.com` passed the host allowlist: Python sees host `facebook.com`, browsers go to `evil.example`. Admins click these links during review, and verified links are public. | Backslashes, control characters, credentials and ports are rejected, and the stored URL is rebuilt from the checked parts. |
| 5 | Medium | **Location metadata in uploaded photos.** EXIF GPS data in product photos and logos (public) and complaint photos (shown to the other party) could reveal a home location. | Metadata (EXIF, XMP, IPTC, comments, PNG text chunks) is removed from JPEG, PNG and WebP before storage and hashing, without re-encoding. Malformed images are rejected. |
| 6 | Medium | **No request body limit.** Bodies were fully received and parsed before the per-file checks ran, so large or endless (chunked) bodies cost memory and disk. | ASGI middleware rejects bodies over 1 MB (multipart: 52 MB) using `Content-Length` and a count of streamed bytes, returning 413. |
| 7 | Low | **No Content-Security-Policy on the web app; no CSP/HSTS on the API.** | Web: CSP with `default-src 'self'`, no plugins, no framing, `connect-src` limited to the API and Supabase, plus HSTS and COOP. API: `default-src 'none'; frame-ancestors 'none'`, CORP, and HSTS in production. |
| 8 | Low | **Personal data could reach logs.** SQLAlchemy error messages include bound parameters (addresses, phone numbers, JWT-claims email). | `hide_parameters=True` on the engine. |
| 9 | Low | **Denied requests weren't easy to monitor.** | 401/403/429 responses are logged as `trustora.security` events with code, path, client IP and request id (never tokens). |
| 10 | Low | **Audit gaps.** Profile changes, and admin trust recalculations that left the score unchanged, weren't recorded. | `profile.updated` (field names only, no values) and `trust.recalculated`. |
| 11 | Low | `.gitignore` covered `.env` but not, e.g., `.env.production`. | Ignores `.env.*` and `*.env`, except `.env.example`. |

## Checks with no issues found

- **Authentication.** JWTs are verified with JWKS (ES256/RS256), with HS256 only when its secret
  is configured and `none` rejected. `aud`, `iss`, `exp`, `iat` and `sub` are required and the
  role must be `authenticated`. Suspended accounts get 403 on every request.
- **Authorization.** All 66 API routes were inventoried (`test_every_route_has_the_expected_access_rule`):
  - admin routes require ADMIN, seller routes SME, and customer routes CUSTOMER;
  - public routes are read-only (plus the checkout quote and the chat) and always run as `anon`;
  - a new route fails the test until its access rule is added.
- **Object-level access (IDOR).** This is enforced twice, in the service layer and by RLS. Existing
  tests cover cross-customer, cross-seller and role-escalation attempts, as do the chatbot tool
  tests.
- **Input validation.**
  - Every request body model rejects unknown fields; a test checks all of them, which prevents mass
    assignment.
  - Lengths and patterns are enforced.
  - The SQL that varies is built only from whitelisted column names.
  - Validation errors echo field names, never the submitted values.
- **Injection and XSS.** All SQL is parameterized. React escapes all output, and the codebase has
  no `dangerouslySetInnerHTML` or `eval`. Chat replies render as plain text.
- **CSRF.** The API authenticates with bearer tokens, not cookies. There are no Next.js server
  actions, and the only route handler is the GET auth callback.
- **SSRF.** The server only calls fixed URLs (Supabase Storage, JWKS, Gemini) and never fetches
  user-supplied URLs.
- **Files.**
  - The type comes from the file content (magic bytes), and the extension must match.
  - Size limits apply per file, and storage names are generated by the server.
  - SVG is rejected, as are PDFs with JavaScript, actions or embedded files.
  - Evidence is kept in a private bucket and opened only through 5-minute signed URLs.
  - SHA-256 integrity hashes are re-checked before AI analysis.
- **Rate limiting.** The default is 120 requests per minute per client. Uploads are limited to
  30/min, AI analysis to 30 or 20/min, and the chat to 20/min. Limits are per IP and in memory
  (single instance, see ADR 0006).
- **Secrets.**
  - A scan of the full git history found no secrets.
  - Only the `.env.example` files are tracked.
  - The Gemini key and the Supabase service key are server-side only; the browser receives only
    `NEXT_PUBLIC_*` values.
  - Logs never include tokens, prompts or AI outputs.
- **AI.** The relevant controls are covered in ADR 0008 and ADR 0009:
  - redaction of personal data;
  - untrusted-input markers;
  - output guards;
  - role-gated tools that take identity from the session;
  - no writes by the model.
- **Dependencies.** `npm audit --omit=dev` and `pip-audit -r requirements.txt` both report 0 known
  vulnerabilities (2026-10-06).

## Required production settings (Supabase and hosting)

The code can't enforce these; set them when deploying.

1. **Data API.** Trustora doesn't use it. Either remove `public` from *Exposed schemas* (Project
   Settings → Data API) or leave it: the `api_only` policy already blocks it. Never expose the
   `private` schema.
2. **Auth.**
   - Require email confirmation.
   - Enable leaked-password protection.
   - Set a minimum password length of at least 8.
   - Keep refresh-token rotation on, with an access-token lifetime of 1 hour or less.
   - Turn on MFA for admin accounts.
3. **Admin accounts.** Create them only by SQL or seed, never through signup (the app never allows
   it), and keep the list short.
4. **Keys.** The service-role key and the Gemini key go in the backend environment only. Use a
   paid-tier Gemini key before processing real data, and rotate keys if they are exposed.
5. **Database connection.** Use the session pooler over TLS. The backend's database user must not
   be exposed elsewhere.
6. **Proxy and TLS.**
   - Serve both apps over HTTPS only.
   - Run uvicorn with `--proxy-headers --forwarded-allow-ips=<frontend/LB>` so rate limits apply
     per client.
   - Set `APP_ENV=production`, which disables `/docs` and enables HSTS.
7. **Monitoring.** Alert on spikes of `trustora.security` events (401/403/429) and on
   `Unhandled error` logs. Supabase Auth logs cover sign-in failures.

## Accepted risks and follow-ups

- **CSP allows inline scripts.** Next.js needs them to start up unless a nonce is generated per
  request. A nonce-based CSP means wiring nonces through the locale proxy and is a possible later
  step; the current policy still blocks foreign scripts, plugins, framing and exfiltration to
  other hosts.
- **The Supabase session lives in a cookie readable by JavaScript.** This is how `@supabase/ssr`
  works. XSS is mitigated by React's escaping and the CSP.
- **Rate limits are in memory and per IP.** Running several instances needs shared storage
  (e.g. Redis); see ADR 0006.
- **Image metadata removal is container-level.** Pixel data is untouched, so faces or visible
  addresses inside photos aren't, and can't be, detected.
- **Dev-only npm advisory.** `npm audit` (including dev dependencies) reports `braces` (ReDoS,
  GHSA-vfj7-8cjw-p6xm) through `eslint-config-next`. It only runs in local linting, never in the
  built app, and npm's suggested fix downgrades to eslint-config-next 14, a breaking change.
  Revisit when eslint-config-next updates its dependency. Production dependencies have 0 known
  vulnerabilities.
