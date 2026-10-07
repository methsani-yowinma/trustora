"""The only module that talks to Google Gemini.

Everything else uses the small `AiClient` protocol, so the SDK stays isolated, the API key never
leaves this process, and tests can substitute a fake. Outputs are always validated with Pydantic
before anyone sees them; invalid or unavailable AI is reported as an error, never guessed around.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("trustora.ai")

T = TypeVar("T", bound=BaseModel)

TIMEOUT_SECONDS = 20
MAX_ATTEMPTS = 3
# After a fallback model answers, keep using it this long before trying the primary again.
PREFER_FALLBACK_SECONDS = 300


class AiError(Exception):
    code = "ai_error"


class AiUnavailable(AiError):
    """Not configured, timed out, rate-limited or a provider error."""

    code = "ai_unavailable"


class AiBusy(AiUnavailable):
    """Every configured model is overloaded or rate-limited right now; worth retrying later."""

    code = "ai_busy"


class AiInvalidOutput(AiError):
    """The model answered, but not in the required structure."""

    code = "ai_invalid_output"


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class FilePart:
    data: bytes
    mime_type: str


Part = TextPart | FilePart


# --- Function calling (chat) -------------------------------------------------------------
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema of the arguments


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["user", "model"]
    text: str


@dataclass(frozen=True)
class ModelTurn:
    """One model step: either a final text answer or tool calls to run first."""

    text: str | None
    calls: list[ToolCall] = field(default_factory=list)
    # SDK content for replaying this turn exactly (keeps thought signatures); opaque to callers.
    raw: object | None = None


@dataclass(frozen=True)
class ToolResults:
    results: list[tuple[ToolCall, dict[str, Any]]]


ChatItem = ChatMessage | ModelTurn | ToolResults


class AiClient(Protocol):
    model: str
    enabled: bool

    async def generate_json(self, *, system: str, parts: list[Part], schema: type[T]) -> T: ...

    async def generate_text(
        self, *, system: str, parts: list[Part], max_tokens: int = 400
    ) -> str: ...

    async def chat(
        self, *, system: str, history: list[ChatItem], tools: list[ToolSpec], max_tokens: int = 800
    ) -> ModelTurn: ...


class DisabledAiClient:
    """Used when GEMINI_API_KEY is not set: every call reports AI as unavailable."""

    model = "disabled"
    enabled = False

    async def generate_json(self, *, system: str, parts: list[Part], schema: type[T]) -> T:
        raise AiUnavailable("AI is not configured")

    async def generate_text(self, *, system: str, parts: list[Part], max_tokens: int = 400) -> str:
        raise AiUnavailable("AI is not configured")

    async def chat(
        self, *, system: str, history: list[ChatItem], tools: list[ToolSpec], max_tokens: int = 800
    ) -> ModelTurn:
        raise AiUnavailable("AI is not configured")


class GeminiClient:
    enabled = True

    def __init__(self, api_key: str, model: str, fallback_models: tuple[str, ...] = ()) -> None:
        from google import genai
        from google.genai import types

        # Recorded with stored analyses. The model that actually answered may be a fallback.
        self.model = model
        self._models = tuple(dict.fromkeys((model, *fallback_models)))
        self._retired: set[str] = set()
        self._preferred: tuple[str, float] | None = None
        self.last_model: str | None = None  # the model that answered most recently
        self._types = types
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000)
        )

    def _contents(self, parts: list[Part]) -> list[object]:
        types = self._types
        return [
            types.Part.from_text(text=p.text) if isinstance(p, TextPart)
            else types.Part.from_bytes(data=p.data, mime_type=p.mime_type)
            for p in parts
        ]  # fmt: skip

    async def _generate(self, *, system: str, parts: list[Part], **config: object) -> str:
        response = await self._call(system=system, contents=self._contents(parts), **config)
        text = response.text
        if not text:
            # e.g. blocked by safety filters; never treat as an answer.
            raise AiInvalidOutput("Empty response")
        return text

    async def _call(self, *, system: str, contents: list[Any], **config: object) -> Any:
        from google.genai import errors

        cfg = self._types.GenerateContentConfig(
            system_instruction=system, temperature=0.1, **config
        )
        failure: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            for model in self._order():
                try:
                    response = await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model=model, contents=contents, config=cfg
                        ),
                        timeout=TIMEOUT_SECONDS,
                    )
                except (TimeoutError, errors.ServerError) as exc:
                    failure = exc  # overloaded or slow: try the next model
                except errors.ClientError as exc:
                    failure = exc
                    status = getattr(exc, "code", None)
                    if status == 404:
                        # Retired or unknown model name: a configuration problem, not a blip.
                        self._retired.add(model)
                        logger.error("Gemini model not available; check GEMINI_MODEL / GEMINI_FALLBACK_MODELS",
                                     extra={"model": model, "status": status})  # fmt: skip
                    elif status != 429:
                        # Bad key or bad request: retrying or switching models will not help.
                        self._log_failure(model, exc)
                        raise AiUnavailable("AI request failed") from exc
                else:
                    self._remember(model)
                    return response
                self._log_failure(model, failure)
            if not self._order():
                raise AiUnavailable("No configured Gemini model is available") from failure
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(0.5 * 2**attempt)
        raise AiBusy("AI is busy") from failure

    def _order(self) -> list[str]:
        """Models to try, the recently successful fallback first; retired names are skipped."""
        available = [m for m in self._models if m not in self._retired]
        if self._preferred and time.monotonic() - self._preferred[1] < PREFER_FALLBACK_SECONDS:
            preferred = self._preferred[0]
            if preferred in available:
                available.remove(preferred)
                available.insert(0, preferred)
        return available

    def _remember(self, model: str) -> None:
        self.last_model = model
        self._preferred = None if model == self._models[0] else (model, time.monotonic())

    @staticmethod
    def _log_failure(model: str, failure: Exception | None) -> None:
        # The class and status only: provider messages can echo the request.
        logger.warning("Gemini call failed", extra={"model": model, "error": type(failure).__name__,
                                                    "status": getattr(failure, "code", None)})  # fmt: skip

    async def generate_json(self, *, system: str, parts: list[Part], schema: type[T]) -> T:
        text = await self._generate(
            system=system,
            parts=parts,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
            max_output_tokens=1024,
        )
        try:
            return schema.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AiInvalidOutput("Response did not match the required structure") from exc

    async def generate_text(self, *, system: str, parts: list[Part], max_tokens: int = 400) -> str:
        return (
            await self._generate(system=system, parts=parts, max_output_tokens=max_tokens)
        ).strip()

    def _chat_contents(self, history: list[ChatItem]) -> list[Any]:
        types = self._types
        contents: list[Any] = []
        for item in history:
            if isinstance(item, ChatMessage):
                contents.append(
                    types.Content(role=item.role, parts=[types.Part.from_text(text=item.text)])
                )
            elif isinstance(item, ModelTurn):
                contents.append(item.raw or types.Content(role="model", parts=[
                    types.Part.from_function_call(name=c.name, args=c.args) for c in item.calls
                ]))  # fmt: skip
            else:
                contents.append(types.Content(role="user", parts=[
                    types.Part.from_function_response(name=call.name, response=response)
                    for call, response in item.results
                ]))  # fmt: skip
        return contents

    async def chat(
        self, *, system: str, history: list[ChatItem], tools: list[ToolSpec], max_tokens: int = 800
    ) -> ModelTurn:
        types = self._types
        declarations = [
            types.FunctionDeclaration(
                name=t.name, description=t.description, parameters_json_schema=t.parameters
            )
            for t in tools
        ]
        response = await self._call(
            system=system,
            contents=self._chat_contents(history),
            max_output_tokens=max_tokens,
            # Trustora runs every tool itself, after its own authorization checks.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            **({"tools": [types.Tool(function_declarations=declarations)]} if declarations else {}),
        )
        candidates = response.candidates or []
        content = candidates[0].content if candidates else None
        parts = (content.parts if content else None) or []
        calls = [
            ToolCall(name=p.function_call.name or "", args=dict(p.function_call.args or {}),
                     id=p.function_call.id)
            for p in parts if p.function_call
        ]  # fmt: skip
        if calls:
            return ModelTurn(text=None, calls=calls, raw=content)
        text = "".join(p.text for p in parts if p.text and not p.thought).strip()
        if not text:
            raise AiInvalidOutput("Empty response")
        return ModelTurn(text=text, raw=content)


def create_ai_client(
    api_key: str | None, model: str, fallback_models: tuple[str, ...] = ()
) -> AiClient:
    return GeminiClient(api_key, model, fallback_models) if api_key else DisabledAiClient()
