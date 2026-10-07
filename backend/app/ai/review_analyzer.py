"""Background classification of complaints and reviews.

Runs after the request has committed. Reads, calls Gemini and writes in separate steps so no
database transaction is held open during the AI call. Results are stored as AI analysis only —
they never change a complaint's status, a score, or what the customer wrote.
"""

import logging
from typing import Any

from sqlalchemy import text

from app.ai import prompts, store
from app.ai.gemini_client import AiClient, AiError, TextPart
from app.ai.privacy import as_untrusted
from app.ai.schemas import ComplaintAnalysis, ReviewAnalysis
from app.core.db import Database

logger = logging.getLogger("trustora.ai")


async def _record(db: Database, ai: AiClient, *, kind: str, target_id: str, sme_id: str, version: str,
                  status: str, output: dict[str, Any] | None = None, error: str | None = None) -> None:  # fmt: skip
    async with db.system_transaction() as conn:
        await store.save(conn, kind=kind, target_id=target_id, sme_id=sme_id, model=ai.model,
                         prompt_version=version, status=status, output=output, error_code=error)  # fmt: skip


async def analyze_complaint(db: Database, ai: AiClient, complaint_id: str) -> None:
    try:
        async with db.system_transaction() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "select sme_id, category, description from public.complaints where id = :id"
                        ),
                        {"id": complaint_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return
        meta = {"kind": "COMPLAINT", "target_id": complaint_id, "sme_id": str(row["sme_id"]),
                "version": prompts.COMPLAINT_VERSION}  # fmt: skip
        if not ai.enabled:
            await _record(db, ai, status="SKIPPED", error="ai_not_configured", **meta)
            return
        try:
            result = await ai.generate_json(
                system=prompts.COMPLAINT_SYSTEM,
                parts=[
                    # Only the category and the (redacted) text — never names, contacts or order details.
                    TextPart(f"Category chosen by the customer: {row['category']}"),
                    TextPart(as_untrusted("Complaint", row["description"])),
                ],
                schema=ComplaintAnalysis,
            )
        except AiError as exc:
            await _record(db, ai, status="FAILED", error=exc.code, **meta)
            return
        output = result.model_dump()
        # Whatever the model says, a complaint stays a customer allegation.
        output["claim_type"] = "CUSTOMER_ALLEGATION"
        output["customer_category"] = row["category"]
        await _record(db, ai, status="DONE", output=output, **meta)
    except Exception:  # background work must never crash the worker
        logger.exception("Complaint analysis failed", extra={"complaint_id": complaint_id})


async def analyze_review(db: Database, ai: AiClient, review_id: str) -> None:
    try:
        async with db.system_transaction() as conn:
            row = (
                (
                    await conn.execute(
                        text("select sme_id, rating, comment from public.reviews where id = :id"),
                        {"id": review_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None or not row["comment"]:
            return  # nothing to analyse in a rating-only review
        meta = {"kind": "REVIEW", "target_id": review_id, "sme_id": str(row["sme_id"]),
                "version": prompts.REVIEW_VERSION}  # fmt: skip
        if not ai.enabled:
            await _record(db, ai, status="SKIPPED", error="ai_not_configured", **meta)
            return
        try:
            result = await ai.generate_json(
                system=prompts.REVIEW_SYSTEM,
                parts=[
                    TextPart(f"Star rating: {row['rating']} of 5"),
                    TextPart(as_untrusted("Review", row["comment"])),
                ],
                schema=ReviewAnalysis,
            )
        except AiError as exc:
            await _record(db, ai, status="FAILED", error=exc.code, **meta)
            return
        output = result.model_dump()
        output["claim_type"] = "CUSTOMER_OPINION"
        await _record(db, ai, status="DONE", output=output, **meta)
    except Exception:
        logger.exception("Review analysis failed", extra={"review_id": review_id})
