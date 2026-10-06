"""Trustora AI: a grounded, role-aware assistant built on Gemini function calling.

Flow per request (stateless; the client sends the recent conversation):
  redact user text → Gemini with the tools this user may use → run requested tools (authorized,
  read-only) → feed results back → … at most MAX_ROUNDS times → guard the final reply.

The model never writes data and never sees credentials. Complaint drafts are returned to the UI,
where the customer confirms them through the normal complaints endpoint.
"""

import logging
import re

from app.ai import prompts
from app.ai.chat_tools import ToolContext, run_tool, specs, tools_for
from app.ai.gemini_client import AiClient, AiError, ChatItem, ChatMessage, ModelTurn, ToolResults
from app.ai.privacy import redact
from app.ai.schemas import ChatRequest, ChatResponse, ChatSource, ComplaintDraft
from app.core.errors import AppError

logger = logging.getLogger("trustora.ai.chat")

MAX_ROUNDS = 5
MAX_CALLS_PER_ROUND = 4

INSUFFICIENT = {
    "en": "There isn't enough verified evidence to determine this. You can check the seller's Trust "
    "Passport for the evidence Trustora has reviewed.",
    "si": "මෙය තීරණය කිරීමට ප්‍රමාණවත් තහවුරු කළ සාක්ෂි නොමැත. Trustora සමාලෝචනය කළ සාක්ෂි සඳහා "
    "විකුණුම්කරුගේ Trust Passport බලන්න.",
}
INCOMPLETE = {
    "en": "Sorry, I couldn't complete that. Please try asking in a simpler way.",
    "si": "සමාවන්න, මට එය සම්පූර්ණ කළ නොහැකි විය. කරුණාකර සරලව නැවත අසන්න.",
}

# Absolute safety claims the brief forbids; checked on every reply, whatever the prompt says.
_UNSAFE_CLAIM = re.compile(
    r"100\s*%|guarantee|\b(?:completely|totally|fully|absolutely)\s+(?:safe|genuine|authentic|"
    r"legit|trustworthy)|risk[- ]free|\bscam|\bfraud|සම්පූර්ණයෙන්ම\s*(?:ආරක්ෂිත|විශ්වාස)|වංචා",
    re.IGNORECASE,
)
# Credentials must never appear in a reply (none are given to the model; this is defence in depth).
_SECRET = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.|AIza[0-9A-Za-z_-]{20,}|sb_secret_|service_role")


def _system(ctx: ToolContext, request: ChatRequest) -> str:
    who = (
        f"The user is signed in as a {ctx.user.role.value.lower()}."
        if ctx.user
        else "The user is not signed in: for their own orders or complaints, ask them to sign in."
    )
    page = []
    if request.context and request.context.store_slug:
        page.append(f'store_slug "{request.context.store_slug}"')
    if request.context and request.context.product_id:
        page.append(f'product_id "{request.context.product_id}"')
    viewing = (
        f'The user is viewing {" and ".join(page)}; "this seller/store/product" refers to it.'
        if page
        else "The user is not viewing a specific store or product."
    )
    language = "Sinhala (si)" if request.locale == "si" else "English (en)"
    return f"{prompts.CHAT_SYSTEM}\n\n{who}\n{viewing}\nInterface language: {language}."


def _history(request: ChatRequest) -> list[ChatItem]:
    return [
        # User text is redacted: personal data the user types is not forwarded to Gemini.
        ChatMessage(role="user", text=redact(m.text)) if m.role == "user"
        else ChatMessage(role="model", text=m.text)
        for m in request.messages
    ]  # fmt: skip


def guard(reply: str, locale: str) -> str:
    if _UNSAFE_CLAIM.search(reply) or _SECRET.search(reply):
        return INSUFFICIENT[locale]
    return reply


async def chat(ai: AiClient, ctx: ToolContext, request: ChatRequest) -> ChatResponse:
    if not ai.enabled:
        raise AppError("Trustora AI is not available", code="ai_unavailable", status_code=503)

    tools = tools_for(ctx.user)
    tool_specs = specs(tools)
    system = _system(ctx, request)
    history = _history(request)
    used: list[str] = []
    reply: str | None = None

    try:
        for _ in range(MAX_ROUNDS):
            turn = await ai.chat(system=system, history=history, tools=tool_specs)
            if not turn.calls:
                reply = turn.text
                break
            calls = turn.calls[:MAX_CALLS_PER_ROUND]
            # The raw turn can only be replayed when every call in it gets a response.
            raw = turn.raw if len(calls) == len(turn.calls) else None
            history.append(ModelTurn(text=None, calls=calls, raw=raw))
            results = [(c, await run_tool(ctx, tools, c.name, c.args)) for c in calls]
            used.extend(c.name for c in calls)
            history.append(ToolResults(results))
    except AiError as exc:
        raise AppError(
            "Trustora AI is not available right now", code="ai_unavailable", status_code=503
        ) from exc

    final = guard(reply, request.locale) if reply else INCOMPLETE[request.locale]
    logger.info("Chat answered", extra={"tools": used})
    return ChatResponse(
        reply=final,
        used_tools=list(dict.fromkeys(used)),
        sources=[ChatSource(**s) for s in ctx.sources.values()],
        draft=ComplaintDraft(**ctx.draft) if ctx.draft else None,
        model=ai.model,
    )
