# Testing Trustora

Five layers. Each runs locally without Docker, without a Supabase project and without a Gemini
key. Only the opt-in live AI tests need a key.

| Layer | Tool | Where | What it proves |
| ----- | ---- | ----- | -------------- |
| Backend unit | pytest | `backend/tests/test_trust_rules.py`, `test_trust_combinations.py`, `test_ai.py` (pure parts), `test_input_security.py` | Trust rules and calculator, AI guards, redaction, image metadata removal, URL validation |
| Backend API + database | pytest + embedded PostgreSQL 16 (pgserver) with the real migrations and a Supabase shim | `backend/tests/test_*.py` | Every endpoint through HTTP, with real RLS: authentication, authorization, isolation, workflows, audit, rate limits, size limits, headers |
| Chatbot | pytest with a scripted model | `backend/tests/test_chat.py` | Role-gated tools, identity from the session only, no personal data sent to the model, drafts never written, reply guards |
| Frontend unit and component | Vitest + Testing Library (jsdom) | `frontend/src/**/*.test.ts(x)` | Redirect safety, localization, cart rules, translation completeness, AI labelling, the complaint draft card, the assistant panel |
| End to end | Playwright (desktop + phone viewport) | `frontend/e2e/*.spec.ts` | Real browser, Next.js production build and real API: public pages, signed-in customer, seller and admin journeys, the chatbot, Sinhala, CSP |
| Live AI (opt-in) | pytest `-m live` | `backend/tests/test_live_gemini.py` | Real Gemini: Sinhala in gives Sinhala out, grounding, no access to other customers' data |

## Running

```bash
# Backend (from backend/)
pytest                           # all tests except live AI
pytest --cov                     # with coverage (greenlet-aware, see pyproject.toml)
GEMINI_API_KEY=... pytest -m live  # live Gemini checks (uses API quota)
ruff check . && ruff format --check .
pip-audit -r requirements.txt

# Frontend (from frontend/)
npm test                         # Vitest unit/component tests
npm run lint && npm run typecheck && npm run check:i18n
npx playwright install chromium  # or use an installed browser: PW_CHANNEL=msedge
npm run test:e2e                 # starts the seeded e2e API and a production build
npm audit --omit=dev
```

### How end-to-end tests run
`npm run test:e2e` starts `backend/tests/e2e_server.py` and a Next.js production build.

**The e2e API server:**
- uses embedded Postgres with the real migrations and seed data;
- serves the real API;
- serves a **Supabase Auth stand-in** at `/auth/v1` (`tests/fake_supabase_auth.py`).

**Signing in:**
- Tests sign in through the real login form with seeded accounts (`frontend/e2e/helpers.ts`;
  test-only password).
- Tokens are ES256 JWTs verified by the real backend verifier and by supabase-js.

**Test-only behaviour:**
- **AI:** a deterministic stand-in model calls the real chatbot tools, so answers come from real,
  authorized data.
- **Rate limits:** off, because every request comes from one IP. Backend tests cover them.
- **Shared seed data:** state-changing tests use one account per Playwright project, so desktop
  and phone runs don't collide.

## Where the brief's test scenarios live

| Requirement | Tests |
| ----------- | ----- |
| Trust engine: different evidence combinations | `test_trust_combinations.py` checks 1,152 profiles: invariants, hard caps and monotonicity (better evidence never lowers trust; open allegations never change it). `test_trust_rules.py` has 28 targeted cases. `test_trust_api.py` covers the end-to-end evidence review. |
| Customer A cannot access Customer B's order | `test_commerce.py::test_order_isolation`, `::test_order_tables_rls`; e2e `signed-in.spec.ts` "customer A cannot open customer B's order" |
| SME A cannot access SME B's products/orders | `test_products.py::test_sme_isolation`, `test_commerce.py::test_order_isolation`, `test_rls_sme.py::test_sme_cannot_touch_other_sme_rows`; e2e "seller A cannot open seller B's products or orders" |
| Gemini cannot retrieve unauthorized information | `test_chat.py`: another customer's order, visitor personal tools, user ids in arguments, seller isolation, PII never sent; e2e "does not reveal another customer's orders"; live `test_model_cannot_reach_another_customers_order` |
| Sinhala questions return Sinhala responses | Live `test_sinhala_question_gets_a_grounded_sinhala_answer` and the Singlish order test (real model). Deterministic: the Sinhala locale reaches the model, fallbacks are Sinhala, and the Sinhala UI and assistant work (`test_chat.py`, `TrustoraAI.test.tsx`, e2e Sinhala tests). |
| Authentication | `test_auth.py`: JWKS, algorithms, expiry, audience/issuer, suspended accounts. e2e: sign in, wrong password, sign out. |
| Authorization | `test_security.py::test_every_route_has_the_expected_access_rule` (all 66 routes), the RLS suites, and direct Data API access |

## Coverage
Run `pytest --cov`; the result at the end of Phase 10 is in the README. Coverage must be
measured with `concurrency = ["greenlet", "thread"]`. Without it, code after a database call is
reported as not covered.

## Writing new tests
- **New API route:** add it to `EXPECTED_ACCESS` in `test_security.py` (the test fails until you
  do) and test its isolation.
- **New table:** it gets the `api_only` policy in its migration; `test_every_table_requires_the_api_path`
  checks this.
- **New user-facing text:** add it to both `messages/en.json` and `si.json`, with the same
  placeholders (`messages.test.ts`).
