# ADR 0008 — Gemini integration

**Status:** Accepted (Phase 7)

## Context
Phase 7 adds Google Gemini for five tasks: complaint classification, review sentiment, document
reading, product-evidence reading, and plain-language trust explanations. The brief sets firm
limits: Gemini never produces the Trust Score, AI output is never presented as fact, the API key
stays on the server, and personal data must be protected.

## Decision

**One adapter, one SDK.** `app/ai/gemini_client.py` wraps `google-genai` behind a small `AiClient`
protocol (`generate_json`, `generate_text`). Domain code depends on the protocol, so tests use a
fake. With no `GEMINI_API_KEY` set, a `DisabledAiClient` is used and every feature still works
without AI (as SKIPPED records or the template explanation). Default model: `gemini-2.5-flash`
(`GEMINI_MODEL`). Transient errors (5xx, 429, timeouts) get up to 3 attempts with backoff. Logs
record only the error class and status, never prompts, outputs or keys.

**Structured, validated output.** Classification and extraction calls use a JSON schema and are
validated with Pydantic. Invalid output is recorded as `FAILED / ai_invalid_output`.

**AI is advisory and labelled.**
- Every result is stored in `ai_analyses` with model, prompt version, input hash, status and
  provenance `AI_ANALYSIS`. Only admins can read the table (RLS).
- Complaint analyses always carry `claim_type = CUSTOMER_ALLEGATION`; review analyses
  `CUSTOMER_OPINION`. The server sets these values, whatever the model returns.
- No AI result changes a trust score, a complaint status, an evidence decision or product
  authenticity. Admins decide; the trust engine reads only admin decisions.
- Document checks (name / registration number / product mentioned) are deterministic comparisons
  between the extracted text and the seller's records (MATCH / PARTIAL / MISMATCH / NOT_FOUND),
  not a judgement by the model. Product images are only described, never judged as authentic.
- Before analysis the file's SHA-256 is checked against the stored hash.

**Privacy.** Complaint and review text has emails, phone numbers and long digit runs redacted, and
is wrapped in markers that the system prompt marks as untrusted data (to reduce prompt injection).
Customer names, addresses and order details are never sent. Documents (seller-submitted business
records) are sent only on an explicit admin action. A paid-tier key is required before real
customer data is processed, because free-tier data may be used by Google for training.

**Trust explanations.** Gemini rewrites the passport's existing facts (score, level, signals) in
plain English or Sinhala. A guard rejects text that contains banned claims (such as "100%",
"guarantee", "completely safe", "scam" and Sinhala equivalents), contains any number not present
in the facts, or is too long. On rejection, an error or a missing key, a deterministic template
is shown instead. Results are cached per store, locale and fact hash, so Gemini is called again
only when the facts change.

**Background work.** Complaint and review analysis runs as a FastAPI background task after the
response, in its own transaction. AI failures never affect the customer's submission.

## Related change: dependency scope
The installed FastAPI (0.142) runs `yield` dependencies with `scope="request"` by default, finishing them only
after the response is sent. Database transactions therefore committed after background tasks had
started, so those tasks could not see the new rows, and commit errors never reached the client.
All database dependencies now use `Depends(..., scope="function")`, which commits before the
response is sent.

## Consequences
- Without a key, the product works fully; AI features show as unavailable or use templates.
- Extra latency only on the passport's first view after its facts change (then served from cache)
  and on explicit admin document analysis.
- Prompt changes require bumping the prompt version, which invalidates cached explanations.
