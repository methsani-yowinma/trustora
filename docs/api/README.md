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
| 409 | `review_not_allowed`, `complaint_open`, `complaint_window_closed`, `price_changed`, `cart_changed`, `invalid_transition`, `duplicate_submission`, `conflict`, `sme_exists`, `slug_taken`, `social_exists`, `verification_pending`, `already_verified`, `already_decided`, `limit_reached` |
| 413 | `file_too_large` |
| 415 | `unsupported_file_type` |
| 422 | `multiple_stores`, `cart_unavailable`, `validation_error`, `extension_mismatch`, `empty_file`, `document_count`, `unknown_category` |
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

### Trust (Phase 4)

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/stores/{slug}/passport` | public | Digital Trust Passport: store identity, scores and level, positive/risk/info signals with provenance (evidence counts, never ids), evidence summary, 30-day history |
| GET | `/stores/{slug}/trust/history?days=1..365` | public | `{days, baseline, points[], change: {from_score, to_score, from_level, to_level, days}}` |
| GET | `/sme/trust` | SME | Own passport (also when unpublished) + improvement `suggestions` |
| GET | `/admin/evidence?status=PENDING\|ACCEPTED\|REJECTED` | ADMIN | Product/authenticity evidence queue with 5-minute signed URLs |
| POST | `/admin/evidence/{id}/review` | ADMIN | `{decision: ACCEPTED\|REJECTED, misleading, note (required to reject)}` → updates authenticity + trust |
| POST | `/admin/smes/{id}/trust/recalculate` | ADMIN | Recalculate now (e.g. after a methodology change) |

`POST /admin/verifications/{id}/decision` also accepts `documents_misleading` (rejections only).

### Commerce (Phase 5)

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/products?q=&category=&verified=&store=&sort=newest\|price_asc\|price_desc\|trust&page=&page_size=` | public | Product search (names in English/Sinhala and store names); each card carries its store's trust level |
| GET | `/products/{id}` | public | Product page data incl. store trust; `max_quantity` (≤ 10) instead of exact stock |
| GET | `/stores?q=&verified=&page=` | public | Published stores, ordered by trust score |
| POST | `/checkout/quote` | public | `{items: [{product_id, quantity}], district}` → server prices, delivery fee/ETA, `issues` |
| POST | `/checkout` | CUSTOMER | `{items, shipping_address, payment_method: COD\|MOCK_CARD, idempotency_key, expected_total_lkr}` → 201 order. 409 `price_changed` / `cart_changed`; same key returns the same order. 10/min |
| GET | `/orders`, `/orders/{id}` | CUSTOMER | Own orders, with `allowed_actions` |
| POST | `/orders/{id}/cancel` | CUSTOMER | Only while `PLACED`; restocks, refunds sandbox card payments |
| POST | `/orders/{id}/confirm-receipt` | CUSTOMER | `DELIVERED` → `COMPLETED` |
| GET | `/sme/orders?status=`, `/sme/orders/{id}` | SME | Orders placed with the SME's store (incl. shipping address) |
| POST | `/sme/orders/{id}/status` | SME | `{action: confirm\|dispatch\|in_transit\|delivered\|failed\|cancel, reason (cancel/failed)}` |

Delivered orders, failed deliveries, seller cancellations and late deliveries feed transaction trust.

### Reviews and complaints (Phase 6)

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| POST | `/orders/{id}/review` | CUSTOMER | `{rating 1–5, comment?}` — delivered orders only, once, within 90 days |
| GET | `/stores/{slug}/reviews?page=&page_size=` | public | `{average, count, distribution, items}` — verified buyers, no identities |
| GET / POST | `/sme/reviews`, `/sme/reviews/{id}/response` | SME | List; one public response per review |
| POST | `/orders/{id}/complaints` | CUSTOMER | Multipart `category`, `description` (10–2000), up to 3 `files` → allegation |
| GET | `/complaints`, `/complaints/{id}` | CUSTOMER | Own complaints (incl. seller response, evidence, `allowed_actions`) |
| POST | `/complaints/{id}/resolve`, `/escalate`, `/evidence` | CUSTOMER | Close as resolved · ask Trustora to review · add evidence |
| GET | `/sme/complaints?status=`, `/sme/complaints/{id}` | SME | Complaints about the SME's orders |
| POST | `/sme/complaints/{id}/response`, `/evidence` | SME | Respond once · add counter-evidence (seller claim) |
| GET | `/admin/complaints?status=UNDER_REVIEW`, `/admin/complaints/{id}` | ADMIN | Queue / detail with both parties' evidence |
| POST | `/admin/complaints/{id}/decision` | ADMIN | `{decision: UPHELD\|DISMISSED\|RESOLVED, note}` |
| GET | `/stores/{slug}/complaints/summary` | public | Counts only: open allegations and upheld findings by category, resolved, dismissed |

Open complaints carry 0 trust points (allegations). Upheld complaints are verified findings;
upheld product-authenticity complaints mark the order's products as CONCERN.

Uploads are limited to 30/minute per client in addition to the default limit.

### AI (Phase 7)

| Method | Path | Auth | Description |
| ------ | ---- | ---- | ----------- |
| GET | `/stores/{slug}/trust/explanation?locale=en\|si` | public | `{text, source: AI\|TEMPLATE, locale, model, rules_version, generated_at}`. Plain-language summary of the passport facts; template when AI is off or its output fails the guard. 30/minute. |
| POST | `/admin/evidence/{id}/analyze` | ADMIN | Reads a business/product document or product image with Gemini → `AiAnalysis` with `output.extraction` and deterministic `output.checks`. 409 `not_analyzable` / `integrity_mismatch`, 503 `ai_unavailable`. 20/minute. |

| POST | `/chat` | public or any role | Trustora AI. `{messages: [{role: user\|assistant, text ≤1000}] (≤12, last = user), locale: en\|si, context?: {store_slug?, product_id?}}` → `{reply, used_tools, sources: [{kind: STORE\|PRODUCT\|ORDER, ref, label}], draft?: {order_id, order_number, category, description}, model, provenance}`. 503 `ai_unavailable`. 20/minute. |

The chat uses only the tools allowed for the caller's role and identity (see
[ADR 0009](../decisions/0009-trustora-ai-chatbot.md)). A `draft` is never saved: the client
submits it with `POST /orders/{id}/complaints` after the customer confirms.

Complaint and review analyses run automatically in the background after submission.
Admins see them as `ai_analysis` on `/admin/complaints/{id}` and on evidence items. SMEs see
only `ai_sentiment` on `/sme/reviews`. AI output always has `provenance: AI_ANALYSIS` and never
changes scores or decisions.
