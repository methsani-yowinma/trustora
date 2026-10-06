# ADR 0006 — Rate limiting with a FastAPI dependency

**Status:** Accepted (Phase 2)

## Context
The Phase 1 plan named `slowapi`. With the installed FastAPI (0.142), included routers are
wrapped, so slowapi's middleware cannot resolve route handlers and silently applies no limits
(caught by `test_rate_limit_returns_429`).

## Decision
Use the `limits` library (which slowapi itself is built on) through a small dependency,
`app.core.rate_limit.rate_limit("120/minute", scope=...)`. All `/api/v1` routes get the default
limit via the router; stricter limits (e.g. AI chat, uploads) are added per route later.
`/api/v1/health` is not limited.

## Consequences
- In-memory, per-process limits: correct for a single instance. Multiple instances would need
  shared storage (e.g. Redis) — not required for the MVP.
- Behind a proxy, uvicorn must trust forwarded headers so limits apply per client, not per proxy.
- Server-side rendering calls the API from the Next.js server. Those calls forward the visitor's
  IP in `X-Forwarded-For` (`frontend/src/lib/api/server.ts`), and uvicorn is run with
  `--proxy-headers --forwarded-allow-ips=<frontend address>`. Without this, every visitor would
  share one rate-limit bucket (found by the Phase 5 end-to-end tests).
