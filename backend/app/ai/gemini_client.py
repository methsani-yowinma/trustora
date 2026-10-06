"""The only module that talks to Google Gemini.

Everything else uses the small `AiClient` protocol, so the SDK stays isolated, the API key never
leaves this process, and tests can substitute a fake. Outputs are always validated with Pydantic
before anyone sees them; invalid or unavailable AI is reported as an error, never guessed around.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("trustora.ai")

T = TypeVar("T", bound=BaseModel)

TIMEOUT_SECONDS = 25
MAX_ATTEMPTS = 3


class AiError(Exception):
    code = "ai_error"


class AiUnavailable(AiError):
    """Not configured, timed out, rate-limited or a provider error."""

    code = "ai_unavailable"


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


class AiClient(Protocol):
    model: str
    enabled: bool

    async def generate_json(self, *, system: str, parts: list[Part], schema: type[T]) -> T: ...

    async def generate_text(
        self, *, system: str, parts: list[Part], max_tokens: int = 400
    ) -> str: ...


class DisabledAiClient:
    """Used when GEMINI_API_KEY is not set: every call reports AI as unavailable."""

    model = "disabled"
    enabled = False

    async def generate_json(self, *, system: str, parts: list[Part], schema: type[T]) -> T:
        raise AiUnavailable("AI is not configured")

    async def generate_text(self, *, system: str, parts: list[Part], max_tokens: int = 400) -> str:
        raise AiUnavailable("AI is not configured")


class GeminiClient:
    enabled = True

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai
        from google.genai import types

        self.model = model
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
        from google.genai import errors

        cfg = self._types.GenerateContentConfig(
            system_instruction=system, temperature=0.1, **config
        )
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model=self.model, contents=self._contents(parts), config=cfg
                    ),
                    timeout=TIMEOUT_SECONDS,
                )
                text = response.text
                if not text:
                    # e.g. blocked by safety filters; never treat as an answer.
                    raise AiInvalidOutput("Empty response")
                return text
            except (TimeoutError, errors.ServerError) as exc:
                retryable = True
                failure: Exception = exc
            except errors.ClientError as exc:
                # 429 is worth retrying; other 4xx (bad key, bad request) are not.
                retryable = getattr(exc, "code", None) == 429
                failure = exc
            if not retryable or attempt == MAX_ATTEMPTS:
                # Log the class and status only — provider messages can echo the request.
                logger.warning("Gemini call failed", extra={"error": type(failure).__name__,
                                                            "status": getattr(failure, "code", None)})  # fmt: skip
                raise AiUnavailable("AI request failed") from failure
            await asyncio.sleep(0.5 * 2**attempt)
        raise AiUnavailable("AI request failed")  # pragma: no cover

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


def create_ai_client(api_key: str | None, model: str) -> AiClient:
    return GeminiClient(api_key, model) if api_key else DisabledAiClient()
