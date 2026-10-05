# Trustora API

Base path: `/api/v1`. Interactive docs at `/docs` (disabled when `APP_ENV=production`).

## Conventions

- **Auth:** `Authorization: Bearer <Supabase access token>`.
- **Errors:** always
  `{"error": {"code": "...", "message": "...", "details"?: [{"field", "message"}]}}`.
  Submitted values are never echoed back; stack traces are never returned.
- **Request IDs:** send `X-Request-ID` (`[A-Za-z0-9_-]{1,64}`) or one is generated; it is
  returned in the response and logged.
- **Rate limit:** 120 requests/minute per client by default → `429 rate_limited`.

| Status | Codes |
| ------ | ----- |
| 401 | `unauthorized`, `token_expired` |
| 403 | `forbidden`, `profile_missing`, `account_suspended` |
| 404 | `not_found` |
| 422 | `validation_error` |
| 429 | `rate_limited` |
| 503 | `auth_unavailable` |

## Endpoints (Phase 2)

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/health` | — | `{"status": "ok"\|"degraded", "database": "ok"\|"unavailable"}` |
| GET | `/me` | any role | Current user's profile (`id, email, role, status, full_name, phone, preferred_locale, created_at`) |
| PATCH | `/me` | any role | Update `full_name`, `phone`, `preferred_locale`. Unknown fields (e.g. `role`) → 422 |

The full planned endpoint list is in the Phase 1 architecture and is added phase by phase.
