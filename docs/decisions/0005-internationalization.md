# ADR 0005 — Internationalization (English + Sinhala, Tamil-ready)

**Status:** Accepted (Phase 1), implemented in Phase 2

## Decision
- UI strings: `next-intl` with locale-prefixed routes (`/en`, `/si`) and
  `frontend/messages/{locale}.json`. No user-facing text is hard-coded in components.
- `en.json` is the source of truth: TypeScript checks keys at compile time
  (`src/global.d.ts`) and `npm run check:i18n` fails if another locale has missing/extra keys.
- Fonts: Inter + Noto Sans Sinhala via `next/font`; Sinhala pages get extra line height.
- The API returns codes (roles, statuses, signal codes), which the UI translates.
- SME-authored content will be stored as JSONB per locale (from Phase 3).

## Adding Tamil
Add `"ta"` to `src/i18n/routing.ts`, create `messages/ta.json`, add a Tamil font, and extend the
`preferred_locale` check constraint in a new migration.
