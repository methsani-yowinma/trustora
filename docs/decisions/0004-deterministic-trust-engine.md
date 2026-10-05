# ADR 0004 — Deterministic trust engine; Gemini explains, never scores

**Status:** Accepted (Phase 1)

## Decision
Trust scores and levels are computed by versioned, pure rule functions over database facts.
Gemini may classify text, extract document fields and write explanations, but its output
never changes a score directly: only admin-accepted evidence and admin-upheld complaints do.
Every score snapshot records the `rules_version` used.

## Consequences
- Scores are reproducible, testable with fixed evidence combinations and explainable signal
  by signal (each signal has a code, provenance and evidence references).
- AI failures degrade explanations only; the platform keeps working.
