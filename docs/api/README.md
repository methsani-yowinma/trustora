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
| 404 | `not_found`, `sme_not_registered` |
| 409 | `conflict`, `sme_exists`, `slug_taken`, `social_exists`, `verification_pending`, `already_verified`, `already_decided`, `limit_reached` |
| 413 | `file_too_large` |
| 415 | `unsupported_file_type` |
| 422 | `validation_error`, `extension_mismatch`, `empty_file`, `document_count`, `unknown_category` |
| 429 | `rate_limited` |
| 502 | `storage_unavailable`, `storage_not_configured` |
| 503 | `auth_unavailable` |

## Endpoints

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/health` | — | `{"status": "ok"\|"degraded", "database": "ok"\|"unavailable"}` |
| GET | `/me` | any role | Current user's profile (`id, email, role, status, full_name, phone, preferred_locale, created_at`) |
| PATCH | `/me` | any role | Update `full_name`, `phone`, `preferred_locale`. Unknown fields (e.g. `role`) → 422 |

### SME (role SME)

| Method | Path | Description |
| ------ | ---- | ----------- |
| POST | `/smes` | Register the account's business: `slug`, `name`, `description_i18n?`, `contact_email?`, `contact_phone?` |
| GET / PATCH | `/smes/me` | Own store incl. product counts, social accounts (with codes) and latest verification. PATCH: `name`, `description_i18n`, `policies_i18n`, `contact_*`, `is_published` |
| POST | `/smes/me/logo` | Multipart `file` (JPG/PNG/WEBP, up to 5 MB) |
| POST / DELETE | `/smes/me/social-accounts[/{id}]` | Link (`platform`, `handle`, `url?` — must be an https link to that platform) / unlink |
| GET / POST | `/smes/me/verification` | History / submit multipart `business_reg_number`, `registered_name`, 1–5 `documents` (PDF/JPG/PNG/WEBP, up to 10 MB) |
| GET / POST | `/sme/products` | List own (excluding removed) / create |
| GET / PATCH / DELETE | `/sme/products/{id}` | Detail incl. evidence with signed URLs / update / soft-remove |
| POST / DELETE | `/sme/products/{id}/images[/{image_id}]` | Up to 8 images |
| POST | `/sme/products/{id}/evidence` | Multipart `evidence_type` (`PRODUCT_DOCUMENT`/`PRODUCT_IMAGE`), `description`, `file` — stored as a pending seller claim |

### Public (no auth; runs as Postgres role `anon`)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/categories` | Localized categories |
| GET | `/stores/{slug}` | Published store: identity, verification, contact (and whether confirmed), confirmed social accounts, policies |
| GET | `/stores/{slug}/products` | Active products (`in_stock`, never the exact stock) |

### Admin (role ADMIN)

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/admin/verifications?status=SUBMITTED` (or `APPROVED`, `REJECTED`) | Queue |
| GET | `/admin/verifications/{id}` | Detail with 5-minute signed document URLs and history |
| POST | `/admin/verifications/{id}/decision` | `{decision: "APPROVED" or "REJECTED", note (required to reject), contact_verified}` |
| GET | `/admin/social-accounts?pending=true` | Accounts awaiting ownership confirmation |
| POST | `/admin/social-accounts/{id}/decision` | `{verified: bool}` |

Uploads are limited to 30/minute per client in addition to the default limit.
