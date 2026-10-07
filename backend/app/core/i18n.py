"""Localized content stored as JSONB: {"en": "...", "si": "..."}.

Mirrors ``public.is_localized_text`` in the database. Blank values are dropped, and at least
one supported locale is required. Adding Tamil = add "ta" to SUPPORTED_LOCALES (and the DB check).
"""

from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BeforeValidator, StringConstraints

SUPPORTED_LOCALES = ("en", "si")
Locale = Literal["en", "si"]


def _drop_blank(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: text.strip() if isinstance(text, str) else text
            for key, text in value.items()
            if not (isinstance(text, str) and not text.strip())
        }
    return value


def _require_one(value: dict[str, str]) -> dict[str, str]:
    if not value:
        raise ValueError("Provide the text in at least one language")
    return value


def localized_text(max_length: int) -> Any:
    """Pydantic type for a localized text field with a per-language length limit."""
    return Annotated[
        dict[Locale, Annotated[str, StringConstraints(min_length=1, max_length=max_length)]],
        BeforeValidator(_drop_blank),
        AfterValidator(_require_one),
    ]


LocalizedName = localized_text(160)
LocalizedDescription = localized_text(5000)
LocalizedStoreDescription = localized_text(2000)
LocalizedPolicy = localized_text(2000)
