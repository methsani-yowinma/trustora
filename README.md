# Trustora

**Trust. Verify. Shop.** — Digital trust infrastructure for Sri Lankan social commerce.

Trustora helps customers answer *"Can I trust this business, this product, and this transaction?"*
with evidence, and helps legitimate SMEs build a verified digital identity, store and reputation.
Trust levels are always evidence-based and never claim a seller is "100% safe".

| Layer    | Stack                                                       |
| -------- | ----------------------------------------------------------- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind v4, next-intl (`/en`, `/si`) |
| Backend  | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy Core (asyncpg) |
| Data     | Supabase — PostgreSQL + Row Level Security, Auth, Storage    |
| AI       | Google Gemini (server-side only, from Phase 7)              |

Architecture: a **modular monolith** — see [docs/architecture/overview.md](docs/architecture/overview.md)
and the decision records in [docs/decisions/](docs/decisions/).

```text
trustora/
├── backend/            FastAPI app (app/<module>/{router,schemas,service}.py) + pytest suite
├── frontend/           Next.js app (src/app/[locale]/…, messages/{en,si}.json) + Playwright
├── supabase/migrations SQL migrations — the single source of truth for schema, RLS, triggers
├── docs/               architecture, database, api, decisions (ADRs)
└── postman/            API collection
```

## Development status

| Phase | Scope | Status |
| ----- | ----- | ------ |
| 1 | Architecture | ✅ Approved |
| 2 | Foundation: setup, DB, Supabase config, auth, roles, base UI, env | ✅ Approved |
| 3 | SME registration, verification, store, product management | ✅ Approved |
| 4 | Trust Engine: evidence review, rules, calculation, Trust Passport, history | ✅ Approved |
| 5 | Commerce: browsing, cart, checkout, orders, delivery status | ✅ Approved |
| 6 | Customer Trust: reviews, complaints, evidence workflows, trust explanations | ✅ Approved |
| 7 | Gemini: complaint/review analysis, document reading, trust explanations | ✅ Approved |
| 8 | Trustora AI: grounded, role-aware chatbot with function calling (en/si) | ✅ Approved |
| 9–10 | Security · Testing | Pending |

## Prerequisites

- Python 3.12, Node.js 20+ (tested with Node 24)
- A Supabase project (free tier is fine)

## 1. Supabase setup

1. Create a project at <https://supabase.com>.
2. **Apply the migrations** — either:
   - SQL Editor → paste and run each file in `supabase/migrations/` in filename order, or
   - `npx supabase login && npx supabase link --project-ref <ref> && npx supabase db push`
3. **Auth → URL Configuration**
   - Site URL: `http://localhost:3000`
   - Redirect URLs: `http://localhost:3000/en/auth/callback`, `http://localhost:3000/si/auth/callback`
4. **Bootstrap an admin.** Admin can never be chosen at signup. Sign up normally, then run
   in the SQL Editor:

   ```sql
   update public.profiles set role = 'ADMIN'
   where id = (select id from auth.users where email = 'you@example.com');
   ```

## 2. Backend

```bash
cd backend
py -3.12 -m venv .venv            # macOS/Linux: python3.12 -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then fill in the values
uvicorn app.main:create_app --factory --reload --port 8000
```

- `DATABASE_URL`: Supabase → **Connect** → *Session pooler* connection string.
- `SUPABASE_SERVICE_ROLE_KEY`: required for uploads (logos, product images, verification documents).
  The migration creates the `public-media` and `private-evidence` Storage buckets.
- `SUPABASE_JWT_SECRET`: only for projects still signing tokens with the legacy HS256 secret.
  Projects using JWT signing keys are verified automatically through JWKS.
- API docs (development only): <http://localhost:8000/docs>. Health: `GET /api/v1/health`.
- **Behind the Next.js server / a load balancer**, run uvicorn with
  `--proxy-headers --forwarded-allow-ips=<frontend/LB address>`. Server-rendered pages forward the
  visitor's IP (`X-Forwarded-For`), so per-client rate limits apply per visitor rather than to the
  frontend server as a whole.
- `GEMINI_API_KEY` (optional): enables AI analysis and AI-written trust summaries. Without it,
  everything works and summaries use a rules-based template. Use a **paid-tier** key before
  processing real customer data. `GEMINI_MODEL` defaults to `gemini-2.5-flash`.
  See [ADR 0008](docs/decisions/0008-gemini-integration.md). The same key powers the Trustora AI
  assistant ([ADR 0009](docs/decisions/0009-trustora-ai-chatbot.md)); without it the assistant
  reports that it is unavailable.

## 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local        # fill in Supabase URL + anon key; API URL defaults to :8000
npm run dev                       # http://localhost:3000 → redirects to /en
```

## Testing

```bash
# Backend: 323 tests incl. real-Postgres RLS tests (embedded PostgreSQL via pgserver; no Docker)
cd backend && pytest
ruff check . && ruff format --check .

# Frontend
cd frontend
npm run lint && npm run typecheck && npm run check:i18n
npx playwright install chromium   # or use an installed browser: PW_CHANNEL=msedge
npm run test:e2e                  # seeded API (backend/tests/e2e_server.py) + app; desktop + mobile
```

A Postman collection is in [postman/](postman/).

## Security notes

- Secrets live only in `backend/.env` (never committed). The browser only ever receives
  `NEXT_PUBLIC_*` values (Supabase URL, anon key, API URL).
- Every API request is authorized in the service layer **and** runs inside a Postgres
  transaction as role `authenticated` with the caller's JWT claims, so RLS also applies.
- Anything granted to `authenticated` is reachable from the browser via Supabase's REST API;
  migrations therefore revoke default grants and add only safe, RLS-protected privileges.
