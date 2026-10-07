# ADR 0001 — Modular monolith

**Status:** Accepted (Phase 1)

## Context
Trustora is an MVP built by a small team. Trust, commerce and AI features are tightly related
(e.g. an order outcome updates trust; the chatbot reads both).

## Decision
One FastAPI application with clearly separated modules (`app/<module>/{router,schemas,service}.py`)
and one Next.js application. No microservices, message brokers or separate AI service.

## Consequences
- Simple deployment, local development and transactions across modules (e.g. order status
  change + trust recalculation + audit log in one database transaction).
- Module boundaries are a code-review discipline: modules call each other's `service`
  functions, never each other's SQL.
