"""Admin-triggered document reading (business registration certificates, invoices, …).

Gemini only *extracts* what is written. Trustora code then compares the extraction with the
application (registered name, registration number, product names). Neither step decides
anything: the admin still reviews the document and makes the verification decision.
"""

import hashlib
import re
import unicodedata
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ai import prompts, store
from app.ai.gemini_client import AiClient, AiError, FilePart, TextPart
from app.ai.output import AiAnalysisOut
from app.ai.schemas import DocumentExtraction
from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.storage import PRIVATE_BUCKET, StorageClient

ANALYZABLE_TYPES = ("BUSINESS_DOCUMENT", "PRODUCT_DOCUMENT", "PRODUCT_IMAGE")
# Parentheses are stripped before matching, so "(Pvt) Ltd" becomes "pvt ltd".
_COMPANY_SUFFIXES = re.compile(r"\b(pvt|private|ltd|limited|plc|co|company)\b")


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = _COMPANY_SUFFIXES.sub(" ", value.replace("(", " ").replace(")", " "))
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def _normalize_number(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def compare_name(extracted: str | None, expected: str) -> str:
    if not extracted:
        return "NOT_FOUND"
    a, b = _normalize_name(extracted), _normalize_name(expected)
    if a == b:
        return "MATCH"
    if a and b and (a in b or b in a):
        return "PARTIAL"
    return "MISMATCH"


def compare_number(extracted: str | None, expected: str) -> str:
    if not extracted:
        return "NOT_FOUND"
    return "MATCH" if _normalize_number(extracted) == _normalize_number(expected) else "MISMATCH"


def _product_mentioned(extracted: list[str], names: dict[str, str]) -> str:
    if not extracted:
        return "NOT_FOUND"
    wanted = {_normalize_name(n) for n in names.values() if n}
    found = {_normalize_name(n) for n in extracted}
    return (
        "MATCH" if any(w and any(w in f or f in w for f in found) for w in wanted) else "MISMATCH"
    )


async def analyze_evidence(
    conn: AsyncConnection,
    storage: StorageClient,
    ai: AiClient,
    admin: CurrentUser,
    evidence_id: str,
) -> AiAnalysisOut:
    row = (
        (
            await conn.execute(
                text(
                    "select e.id, e.type, e.sme_id, e.storage_path, e.mime_type, e.sha256, "
                    "v.registered_name, v.business_reg_number, p.name_i18n as product_name "
                    "from public.evidence e "
                    "left join public.business_verifications v on v.id = e.verification_id "
                    "left join public.products p on p.id = e.product_id where e.id = :id"
                ),
                {"id": evidence_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Evidence not found")
    if row["type"] not in ANALYZABLE_TYPES or not row["storage_path"]:
        raise ConflictError("This evidence cannot be analysed", code="not_analyzable")
    if not ai.enabled:
        raise AppError("AI analysis is not configured", code="ai_unavailable", status_code=503)

    data = await storage.download(PRIVATE_BUCKET, row["storage_path"])
    # Integrity: only analyse the exact file that was hashed at upload.
    if hashlib.sha256(data).hexdigest() != row["sha256"]:
        raise ConflictError(
            "The stored file does not match its recorded hash", code="integrity_mismatch"
        )

    meta = {"kind": "DOCUMENT", "target_id": evidence_id, "sme_id": str(row["sme_id"]),
            "model": ai.model, "prompt_version": prompts.DOCUMENT_VERSION}  # fmt: skip
    try:
        extraction = await ai.generate_json(
            system=prompts.DOCUMENT_SYSTEM,
            parts=[
                FilePart(data=data, mime_type=row["mime_type"]),
                TextPart("Extract the fields from this document."),
            ],
            schema=DocumentExtraction,
        )
    except AiError as exc:
        # Recorded and returned (not raised) so the admin sees that AI could not read it.
        await store.save(conn, status="FAILED", error_code=exc.code, **meta)
        return store.to_out((await store.latest(conn, "DOCUMENT", [evidence_id]))[evidence_id])

    checks: dict[str, Any] = {}
    if row["registered_name"]:
        checks["registered_name"] = compare_name(extraction.business_name, row["registered_name"])
        checks["registration_number"] = compare_number(
            extraction.registration_number, row["business_reg_number"]
        )
    if row["product_name"]:
        checks["product_name"] = _product_mentioned(extraction.product_names, row["product_name"])

    analysis_id = await store.save(
        conn,
        status="DONE",
        output={"extraction": extraction.model_dump(), "checks": checks},
        **meta,
    )
    await audit.record(conn, actor=admin, action="ai.document_analyzed", target_type="evidence",
                       target_id=evidence_id, metadata={"analysis_id": analysis_id, "checks": checks})  # fmt: skip
    latest = await store.latest(conn, "DOCUMENT", [evidence_id])
    return store.to_out(latest[evidence_id])
