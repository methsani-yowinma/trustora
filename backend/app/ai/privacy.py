"""Data minimisation before text leaves Trustora for Gemini.

Only the text needed for the task is sent (never customer names, addresses or account ids), and
obvious personal data inside free text is masked first.
"""

import re

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Card-like digit runs (13–19 digits, optionally separated) — checked before phone numbers.
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
# Sri Lankan and international phone numbers: +94 77 123 4567, 0771234567, 011-2345678 …
_PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[ -]?)?(?:\(?0?\d{2,3}\)?[ -]?)\d{3}[ -]?\d{3,4}(?!\w)")


def redact(text: str) -> str:
    text = _EMAIL.sub("[email]", text)
    text = _CARD.sub("[number]", text)
    return _PHONE.sub("[phone]", text)


def as_untrusted(label: str, text: str) -> str:
    """Wraps user-written text so the model treats it as data, not instructions."""
    cleaned = redact(text).replace("<<<", "").replace(">>>", "")
    return f"{label} (untrusted user text, between the markers):\n<<<\n{cleaned}\n>>>"
