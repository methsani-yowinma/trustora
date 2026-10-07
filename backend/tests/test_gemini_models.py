"""Model fallback: Gemini models get retired (404) or overloaded (503); Trustora AI keeps working."""

from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.ai import chatbot, gemini_client
from app.ai.gemini_client import AiBusy, AiUnavailable, GeminiClient, TextPart
from app.core.config import Settings

BUSY = errors.ServerError(
    503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}
)
RETIRED = errors.ClientError(
    404, {"error": {"code": 404, "message": "no longer available", "status": "NOT_FOUND"}}
)
BAD_KEY = errors.ClientError(
    403, {"error": {"code": 403, "message": "bad key", "status": "PERMISSION_DENIED"}}
)


def _client(
    behaviour: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> tuple[GeminiClient, list[str]]:
    """Each model answers from its own queue; returns the client and the models called, in order."""
    client = GeminiClient("k", "primary", ("fallback-a", "fallback-b"))
    called: list[str] = []

    async def generate_content(*, model: str, **_: Any) -> Any:
        called.append(model)
        item = behaviour[model].pop(0) if behaviour[model] else BUSY
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item)

    client._client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )  # type: ignore[assignment]

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(gemini_client.asyncio, "sleep", no_sleep)
    return client, called


async def _ask(client: GeminiClient) -> str:
    return await client.generate_text(system="s", parts=[TextPart("x")])


async def test_busy_primary_falls_back_and_then_prefers_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, called = _client(
        {"primary": [BUSY, BUSY], "fallback-a": ["first", "second"], "fallback-b": []}, monkeypatch
    )
    assert await _ask(client) == "first"
    assert await _ask(client) == "second"
    assert called == ["primary", "fallback-a", "fallback-a"]  # no repeated wait on the busy model


async def test_preference_expires_and_the_primary_is_tried_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, called = _client(
        {"primary": [BUSY, "back"], "fallback-a": ["first"], "fallback-b": []}, monkeypatch
    )
    await _ask(client)
    monkeypatch.setattr(gemini_client, "PREFER_FALLBACK_SECONDS", -1)
    assert await _ask(client) == "back"
    assert called == ["primary", "fallback-a", "primary"]


async def test_retired_model_is_skipped_from_then_on(monkeypatch: pytest.MonkeyPatch) -> None:
    client, called = _client(
        {"primary": [RETIRED], "fallback-a": ["ok", BUSY, "again"], "fallback-b": [BUSY]},
        monkeypatch,
    )
    assert await _ask(client) == "ok"
    assert await _ask(client) == "again"
    assert "primary" not in called[1:]


async def test_all_models_busy_is_reported_as_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    client, called = _client({"primary": [], "fallback-a": [], "fallback-b": []}, monkeypatch)
    with pytest.raises(AiBusy) as raised:
        await _ask(client)
    assert raised.value.code == "ai_busy"
    assert len(called) == 3 * gemini_client.MAX_ATTEMPTS


async def test_all_models_retired_is_a_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(
        {"primary": [RETIRED], "fallback-a": [RETIRED], "fallback-b": [RETIRED]}, monkeypatch
    )
    with pytest.raises(AiUnavailable) as raised:
        await _ask(client)
    assert raised.value.code == "ai_unavailable"


async def test_bad_key_stops_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    client, called = _client(
        {"primary": [BAD_KEY], "fallback-a": ["never"], "fallback-b": []}, monkeypatch
    )
    with pytest.raises(AiUnavailable):
        await _ask(client)
    assert called == ["primary"]


def test_default_models_are_current() -> None:
    settings = Settings(_env_file=None, supabase_url="https://x.supabase.co", database_url="postgresql://u:p@h/db",
                        gemini_model="", gemini_fallback_models="")  # fmt: skip
    assert not settings.gemini_model.startswith("gemini-2.5")  # retired for new keys
    assert (
        settings.gemini_fallback_list and settings.gemini_model not in settings.gemini_fallback_list
    )
    disabled = settings.model_copy(update={"gemini_fallback_models": "none"})
    assert disabled.gemini_fallback_list == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "The store **ceylon-crafts** has a score of **62**.",
            "The store ceylon-crafts has a score of 62.",
        ),
        (
            "## Summary\n* verified business\n* 2 social accounts",
            "Summary\n- verified business\n- 2 social accounts",
        ),
        ("මෙම වෙළඳසැල __විශ්වාසනීය__ මට්ටමේ ඇත.", "මෙම වෙළඳසැල විශ්වාසනීය මට්ටමේ ඇත."),
        ("Plain answer.", "Plain answer."),
    ],
)
def test_replies_are_plain_text(raw: str, expected: str) -> None:
    assert chatbot.guard(raw, "en") == expected
