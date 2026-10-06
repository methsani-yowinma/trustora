"""Plain-language trust summaries ("AI summary") on top of the deterministic signals.

The score is never produced or changed here. Gemini only rephrases the stored signals for
shoppers, in English or Sinhala. Its output is guarded: any number not present in the input, or
certainty language ("100% safe", "guaranteed", "scam"), rejects the text and the deterministic
template is used instead. Accepted outputs are cached per score snapshot and language.
"""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ai import prompts, store
from app.ai.gemini_client import AiClient, AiError, TextPart
from app.ai.schemas import TrustExplanationOut
from app.core.db import Database
from app.core.storage import StorageClient
from app.trust import service as trust_service
from app.trust.schemas import PassportOut

logger = logging.getLogger("trustora.ai")

Locale = Literal["en", "si"]

# English glossary of signal codes, given to the model so it can describe them (in either language).
GLOSSARY = {
    "BUSINESS_VERIFIED": "business registration verified by Trustora (verified fact)",
    "VERIFICATION_PENDING": "business verification in progress",
    "VERIFICATION_NOT_APPROVED": "business verification was not approved",
    "BUSINESS_NOT_VERIFIED": "business not verified by Trustora",
    "CONTACT_CONFIRMED": "contact details confirmed by Trustora (verified fact)",
    "SOCIAL_ACCOUNTS_CONFIRMED": "social media accounts confirmed as owned by the business (verified fact)",
    "POLICIES_PUBLISHED": "returns/refunds/delivery policies published by the seller (seller-provided)",
    "NO_POLICIES": "no store policies published",
    "PLATFORM_TENURE": "time on Trustora",
    "NEW_ON_PLATFORM": "new on Trustora",
    "PROFILE_COMPLETE": "complete store profile (seller-provided)",
    "MISLEADING_EVIDENCE": "evidence found misleading by Trustora (verified finding)",
    "ACCOUNT_SUSPENDED": "account suspended",
    "PRODUCTS_AUTHENTICITY_VERIFIED": "products with authenticity documents verified by Trustora",
    "PRODUCTS_PARTIALLY_VERIFIED": "products with partially verified authenticity evidence",
    "PRODUCTS_WITHOUT_AUTHENTICITY_EVIDENCE": "products without verified authenticity evidence",
    "PRODUCT_AUTHENTICITY_CONCERN": "products with an authenticity concern (verified finding)",
    "NO_ACTIVE_PRODUCTS": "no products listed",
    "LIMITED_TRANSACTION_HISTORY": "limited order history on Trustora",
    "COMPLETED_ORDERS": "completed orders on Trustora",
    "DELIVERY_FAILURES": "failed deliveries",
    "LATE_DELIVERIES": "late deliveries",
    "SELLER_CANCELLATIONS": "orders cancelled by the seller",
    "UPHELD_COMPLAINTS": "customer complaints upheld after Trustora review (verified finding)",
    "UNRESOLVED_COMPLAINTS": "complaints without a seller response for over 14 days",
    "OPEN_COMPLAINTS": "open customer complaints (allegations, not yet reviewed)",
    "VERIFIED_REVIEW_RATING": "average rating from verified buyers",
}

LEVEL_NAMES = {
    "en": {"VERIFIED": "Verified & trusted", "TRUSTED": "Trusted", "DEVELOPING": "Developing",
           "CAUTION": "Caution", "HIGH_RISK": "High risk"},
    "si": {"VERIFIED": "තහවුරු කළ සහ විශ්වාසනීය", "TRUSTED": "විශ්වාසනීය", "DEVELOPING": "වර්ධනය වෙමින්",
           "CAUTION": "ප්‍රවේශම් වන්න", "HIGH_RISK": "ඉහළ අවදානම"},
}  # fmt: skip

BANNED = re.compile(
    r"100\s*%|guarantee|completely safe|fully safe|totally safe|risk[- ]free|\bscam|\bfraud|"
    r"සම්පූර්ණයෙන්ම ආරක්ෂිත|වංචා",
    re.IGNORECASE,
)


def passport_facts(passport: PassportOut) -> dict[str, Any]:
    signals = passport.positive_signals + passport.risk_signals + passport.info_signals
    return {
        "store_name": passport.store.name,
        "trust_level": passport.trust.level,
        "overall_score": passport.trust.overall_score,
        "dimension_scores": {
            "business": passport.trust.business_score,
            "product": passport.trust.product_score,
            "transaction": passport.trust.transaction_score,
        },
        "signals": [
            {
                "kind": s.kind,
                "meaning": GLOSSARY.get(s.code, s.code),
                "source": s.provenance,
                "details": s.params,
            }
            for s in signals
        ],
    }


def _allowed_numbers(facts: dict[str, Any]) -> set[str]:
    found = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(facts, ensure_ascii=False)))
    return found | {"100", "5", "14"}  # "out of 100", "out of 5", "14 days"


def passes_guard(output: str, facts: dict[str, Any]) -> bool:
    if not output or len(output) > 1200 or BANNED.search(output):
        return False
    return set(re.findall(r"\d+(?:\.\d+)?", output)) <= _allowed_numbers(facts)


def template(passport: PassportOut, locale: Locale) -> str:
    trust = passport.trust
    level = LEVEL_NAMES[locale][trust.level]
    positive, risks = len(passport.positive_signals), len(passport.risk_signals)
    if locale == "si":
        return (
            f"පවතින සාක්ෂි මත පදනම්ව {passport.store.name} හි විශ්වාස මට්ටම “{level}” "
            f"(ලකුණු {trust.overall_score}/100) වේ. ධනාත්මක සංඥා {positive}ක් සහ අවදානම් සංඥා {risks}ක් හමු විය. "
            "නව සාක්ෂි ලැබෙන විට විශ්වාස මට්ටම වෙනස් විය හැක."
        )
    return (
        f"Based on the available evidence, {passport.store.name} currently has a trust level of “{level}” "
        f"({trust.overall_score}/100). Trustora found {positive} positive and {risks} risk signals. "
        "Trust levels can change as new evidence arrives."
    )


async def explain(
    conn: AsyncConnection, storage: StorageClient, ai: AiClient, slug: str, locale: Locale
) -> TrustExplanationOut:
    """Runs in the public (anon) transaction; the passport read applies public RLS."""
    passport = await trust_service.public_passport(conn, storage, slug)
    facts = passport_facts(passport)
    input_hash = hashlib.sha256(
        json.dumps(
            {"facts": facts, "locale": locale, "v": prompts.EXPLANATION_VERSION},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()  # fmt: skip
    ).hexdigest()
    base = {"locale": locale, "rules_version": passport.trust.rules_version}

    cached = await _cached(conn, passport.store.id, locale, input_hash)
    if cached is not None:
        return TrustExplanationOut(text=cached["output"]["text"], source="AI", model=cached["model"],
                                   generated_at=cached["created_at"], **base)  # fmt: skip

    fallback = TrustExplanationOut(text=template(passport, locale), source="TEMPLATE", model=None,
                                   generated_at=datetime.now(UTC), **base)  # fmt: skip
    if not ai.enabled:
        return fallback

    meta = {"kind": "TRUST_EXPLANATION", "target_id": passport.store.id, "sme_id": passport.store.id,
            "locale": locale, "input_hash": input_hash, "model": ai.model,
            "prompt_version": prompts.EXPLANATION_VERSION}  # fmt: skip
    try:
        output = await ai.generate_text(
            system=prompts.EXPLANATION_SYSTEM,
            parts=[
                TextPart(f"Language: {locale}"),
                TextPart("Facts (JSON):\n" + json.dumps(facts, ensure_ascii=False)),
            ],
            max_tokens=300,
        )
    except AiError as exc:
        await _save(conn, status="FAILED", error_code=exc.code, **meta)
        return fallback
    if not passes_guard(output, facts):
        logger.info("Trust explanation rejected by guard", extra={"sme_id": passport.store.id})
        await _save(conn, status="FAILED", error_code="guard_rejected", **meta)
        return fallback

    await _save(conn, status="DONE", output={"text": output}, **meta)
    return TrustExplanationOut(
        text=output, source="AI", model=ai.model, generated_at=datetime.now(UTC), **base
    )


async def _cached(conn: AsyncConnection, sme_id: str, locale: str, input_hash: str) -> Any:
    async with Database.privileged(conn):
        return (
            (
                await conn.execute(
                    text(
                        "select output, model, created_at from public.ai_analyses where kind = 'TRUST_EXPLANATION' "
                        "and status = 'DONE' and target_id = :sme and locale = :locale and input_hash = :hash"
                    ),
                    {"sme": sme_id, "locale": locale, "hash": input_hash},
                )
            )
            .mappings()
            .first()
        )


async def _save(conn: AsyncConnection, **values: Any) -> None:
    # A concurrent request may have cached the same explanation; that is fine.
    try:
        async with conn.begin_nested():
            await store.save(conn, **values)
    except IntegrityError:
        pass
