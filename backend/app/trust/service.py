"""Digital Trust Passport assembly and admin evidence review."""

from collections.abc import Mapping
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.errors import ConflictError, NotFoundError
from app.core.storage import PRIVATE_BUCKET, PUBLIC_BUCKET, StorageClient, signed_url_or_none
from app.smes.service import require_own_sme
from app.trust import trust_engine
from app.trust.schemas import (
    AdminEvidenceItem,
    EvidenceReviewIn,
    EvidenceSummary,
    HistoryOut,
    PassportOut,
    PassportStore,
    SmeTrustOut,
    TrustScoreOut,
    TrustSignalOut,
)
from app.trust.trust_explanation import improvement_suggestions
from app.trust.trust_history import load_history

PASSPORT_HISTORY_DAYS = 30

_STORE_COLUMNS = (
    "id, slug, name, logo_path, description_i18n, verification_status, verified_at, created_at"
)


async def _store_by_slug(conn: AsyncConnection, slug: str) -> Mapping[str, Any]:
    """RLS decides visibility: anon callers only see published, active stores."""
    row = (
        (
            await conn.execute(
                text(f"select {_STORE_COLUMNS} from public.smes where slug = :slug"),  # noqa: S608
                {"slug": slug.lower()},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Store not found")
    return row


async def _assemble(
    conn: AsyncConnection, storage: StorageClient, store: Mapping[str, Any]
) -> PassportOut:
    sme_id = str(store["id"])
    score = (
        (
            await conn.execute(
                text(
                    "select overall_score, level, business_score, product_score, transaction_score, "
                    "rules_version, computed_at, evidence_summary from public.trust_scores where sme_id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .first()
    )
    if score is None:
        # Stores created before the trust engine existed get their first score on demand.
        await trust_engine.recalculate(conn, sme_id, trigger="initial")
        return await _assemble(conn, storage, store)

    signals = [
        TrustSignalOut(
            dimension=r["dimension"],
            kind=r["kind"],
            code=r["code"],
            points=r["points"],
            provenance=r["provenance"],
            params=r["params"],
            evidence_count=len(r["evidence_ids"] or []),
        )
        for r in (
            await conn.execute(
                text(
                    "select dimension, kind, code, points, provenance, params, evidence_ids "
                    "from public.trust_signals where sme_id = :id order by abs(points) desc, id"
                ),
                {"id": sme_id},
            )
        ).mappings()
    ]

    return PassportOut(
        store=PassportStore(
            id=sme_id,
            slug=store["slug"],
            name=store["name"],
            logo_url=storage.public_url(PUBLIC_BUCKET, store["logo_path"])
            if store["logo_path"]
            else None,
            description_i18n=store["description_i18n"],
            verification_status=store["verification_status"],
            verified_at=store["verified_at"],
            member_since=store["created_at"],
        ),
        trust=TrustScoreOut(**{k: v for k, v in score.items() if k != "evidence_summary"}),
        positive_signals=[s for s in signals if s.kind == "POSITIVE"],
        risk_signals=[s for s in signals if s.kind == "RISK"],
        info_signals=[s for s in signals if s.kind == "INFO"],
        evidence_summary=EvidenceSummary(**score["evidence_summary"]),
        history=await load_history(conn, sme_id, PASSPORT_HISTORY_DAYS),
    )


async def public_passport(conn: AsyncConnection, storage: StorageClient, slug: str) -> PassportOut:
    return await _assemble(conn, storage, await _store_by_slug(conn, slug))


async def public_history(conn: AsyncConnection, slug: str, days: int) -> HistoryOut:
    store = await _store_by_slug(conn, slug)
    return await load_history(conn, str(store["id"]), days)


async def own_trust(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser
) -> SmeTrustOut:
    sme = await require_own_sme(conn, user)
    store = (
        (
            await conn.execute(
                text(f"select {_STORE_COLUMNS} from public.smes where id = :id"),  # noqa: S608
                {"id": sme["id"]},
            )
        )
        .mappings()
        .one()
    )
    passport = await _assemble(conn, storage, store)
    signals = passport.positive_signals + passport.risk_signals + passport.info_signals
    return SmeTrustOut(**passport.model_dump(), suggestions=improvement_suggestions(signals))


# --- Admin ----------------------------------------------------------------------------------
_EVIDENCE_SQL = (
    "select e.id, e.type, e.provenance, e.description, e.mime_type, e.size_bytes, e.sha256, "
    "e.review_status, e.created_at, e.storage_path, e.flagged_misleading, e.review_note, "
    "s.id as sme_id, s.name as sme_name, s.slug as sme_slug, "
    "p.id as product_id, p.name_i18n as product_name_i18n "
    "from public.evidence e join public.smes s on s.id = e.sme_id "
    "left join public.products p on p.id = e.product_id "
    # Verification documents are reviewed through the verification workflow instead.
    "where e.verification_id is null and e.storage_path is not null "
)


async def _evidence_item(storage: StorageClient, row: Mapping[str, Any]) -> AdminEvidenceItem:
    return AdminEvidenceItem(
        **{k: v for k, v in row.items() if k not in ("id", "storage_path", "sme_id", "product_id")},
        id=str(row["id"]),
        sme_id=str(row["sme_id"]),
        product_id=str(row["product_id"]) if row["product_id"] else None,
        download_url=await signed_url_or_none(storage, PRIVATE_BUCKET, row["storage_path"]),
    )


async def admin_list_evidence(
    conn: AsyncConnection,
    storage: StorageClient,
    status: Literal["PENDING", "ACCEPTED", "REJECTED"],
) -> list[AdminEvidenceItem]:
    rows = (
        (
            await conn.execute(
                text(
                    _EVIDENCE_SQL
                    + "and e.review_status = cast(:status as public.evidence_review_status) "
                    + "order by e.created_at limit 200"
                ),
                {"status": status},
            )
        )
        .mappings()
        .all()
    )
    return [await _evidence_item(storage, r) for r in rows]


async def admin_review_evidence(
    conn: AsyncConnection,
    storage: StorageClient,
    admin: CurrentUser,
    evidence_id: str,
    review: EvidenceReviewIn,
) -> AdminEvidenceItem:
    current = (
        (
            await conn.execute(
                text(_EVIDENCE_SQL + "and e.id = :id for update of e"), {"id": evidence_id}
            )
        )
        .mappings()
        .first()
    )
    if current is None:
        raise NotFoundError("Evidence not found")
    if current["review_status"] != "PENDING":
        raise ConflictError("This evidence has already been reviewed", code="already_decided")

    await conn.execute(
        text(
            "update public.evidence set review_status = cast(:status as public.evidence_review_status), "
            "flagged_misleading = :misleading, review_note = :note, reviewed_by = :admin, "
            "reviewed_at = now() where id = :id"
        ),
        {
            "status": review.decision,
            "misleading": review.misleading,
            "note": review.note,
            "admin": admin.id,
            "id": evidence_id,
        },
    )
    await audit.record(
        conn,
        actor=admin,
        action="evidence.reviewed",
        target_type="evidence",
        target_id=evidence_id,
        metadata={"decision": review.decision, "misleading": review.misleading},
    )
    await trust_engine.recalculate(
        conn, str(current["sme_id"]), trigger="evidence.reviewed", actor=admin
    )

    row = (
        (await conn.execute(text(_EVIDENCE_SQL + "and e.id = :id"), {"id": evidence_id}))
        .mappings()
        .one()
    )
    return await _evidence_item(storage, row)


async def admin_recalculate(
    conn: AsyncConnection, admin: CurrentUser, sme_id: str
) -> TrustScoreOut:
    exists = (
        await conn.execute(text("select 1 from public.smes where id = :id"), {"id": sme_id})
    ).first()
    if exists is None:
        raise NotFoundError("SME not found")
    await trust_engine.recalculate(conn, sme_id, trigger="admin.recalculate", actor=admin)
    row = (
        (
            await conn.execute(
                text(
                    "select overall_score, level, business_score, product_score, transaction_score, "
                    "rules_version, computed_at from public.trust_scores where sme_id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .one()
    )
    return TrustScoreOut(**row)
