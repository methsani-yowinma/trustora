# ADR 0009 — Trustora AI chatbot

**Status:** Accepted (Phase 8)

## Context
The brief asks for an interactive Gemini assistant that answers from Trustora's own data, uses
function calling, respects authorization, never exposes other people's data, admin data or
credentials, never invents trust scores, order states or authenticity, and works in English,
Sinhala and mixed Sinhala-English. Phase 1 fixed the shape: stateless, not streamed, at most 5
tool rounds, and complaints only through drafts that the user confirms.

## Decision

**Endpoint.** `POST /api/v1/chat` with `{messages (≤12, last from the user), locale, context?}`.
It is open to visitors; a bearer token, if sent, must be valid and the account active. The answer
is `{reply, used_tools, sources, draft?, model, provenance: AI_ANALYSIS}`. Limit: 20 requests per
minute per client. There is no server-side chat history.

**Tools (read-only, role-gated).** Implemented in `app/ai/chat_tools.py`. Only the tools for the
caller's role are declared to the model, and a call to any other tool returns
`tool_not_available`.

| Tool | Who | Runs as |
| ---- | --- | ------- |
| `search_stores`, `get_seller_trust` (passport + complaint record), `get_trust_score_history`, `search_products`, `get_product_trust` | everyone | Postgres `anon`, the same view as any visitor |
| `get_my_orders`, `get_my_complaints` | customer, SME | caller's RLS transaction |
| `get_order_status`, `draft_complaint` | customer | caller's RLS transaction |
| `get_my_trust` (breakdown + suggestions) | SME | caller's RLS transaction |

Admins get only the public tools: the assistant is not an admin console.

**Authorization comes from the session, never from the model.** Tools take no user ids. Extra
arguments are rejected (`extra="forbid"`), and personal tools call the same service functions as
the REST API inside the caller's RLS transaction. For example, asking for another customer's order
number returns `not_found`, which is indistinguishable from an order that doesn't exist.

**Data minimisation.** Each tool returns an explicit projection with no names, phone numbers,
addresses, emails, account ids, signed file URLs or complaint/review text. User messages are
redacted (`privacy.redact`) before they go to Gemini.

**Grounding.** A versioned system prompt (`chat-v1`) tells the model to:
- take every fact from a tool result;
- use the brief's fallback sentence, "There isn't enough verified evidence to determine this.",
  when there is no relevant result;
- never recalculate scores or judge authenticity;
- keep verified facts, seller claims, customer allegations and statistics apart;
- treat tool data as untrusted.

Tool results carry meanings for statuses, for example "UNVERIFIED … not the same as fake" and
"open complaints are allegations". The response's `sources` link to the passports, products or
orders that the answer used.

**Guards in code, not only in the prompt.**
- The reply is replaced by the insufficient-evidence fallback if it contains an absolute claim
  ("100%", "guarantee", "completely safe/genuine", "scam", "fraud", or the Sinhala equivalents) or
  anything shaped like a credential.
- Tool rounds (5) and calls per round (4) are capped.

**Complaints.** `draft_complaint` checks that the order is the caller's and that a complaint is
currently allowed, then returns a draft. The UI shows it as an editable card, and the complaint is
created only when the customer presses **Submit**, through the normal
`POST /orders/{id}/complaints`. The assistant never writes data.

**Language.** The reply follows the user's language. Sinhala script and romanised Sinhala ("order
eka awilla na") get Sinhala, and the UI locale is the tiebreaker. Fallback texts exist in en/si.
Adding Tamil means adding fallbacks and messages only.

**Gemini usage.** Function calling is manual (`automatic_function_calling` is disabled) so that
Trustora runs every tool itself. Model turns are replayed exactly, which preserves thought
signatures. Tool schemas are self-contained JSON Schema, derived from the Pydantic argument models
that validate every call.

**No RAG / vector DB.** Every supported question is answered by structured tool calls. pgvector
stays deferred until free-text search over policies or reviews is shown to be needed.

**UI.** A custom launcher (the Trustora shield and tick with an AI spark that twinkles briefly,
and is disabled under reduced motion) opens a non-modal panel: a bottom sheet on phones and a
400px card on desktop. The panel has:
- page-aware suggested questions;
- loading and error states;
- source chips and the complaint draft card;
- a permanent note that AI can make mistakes and that scores come from Trustora's rules;
- keyboard support: Enter sends, Escape closes, and focus returns to the launcher.

## Consequences
- Each question costs 1–6 Gemini calls. Latency is a few seconds and is not streamed (accepted
  for the MVP).
- Answers can only be as complete as the tools, so new question types need new (reviewed) tools.
- The client-supplied history is untrusted. Forging it affects only the caller's own
  conversation, because authorization is re-applied on every tool call.
