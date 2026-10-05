"""Admin review of business verifications and social-account ownership.

Runs in the admin's RLS-scoped transaction (admin policies apply). Platform-generated
evidence and audit entries are written privileged.
"""

from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.errors import ConflictError, NotFoundError
from app.core.storage import StorageClient
from app.evidence import service as evidence
from app.smes.schemas import (
    AdminSocialAccountItem,
    AdminVerificationDetail,
    AdminVerificationListItem,
    SocialDecisionIn,
    VerificationDecisionIn,
)
from app.smes.service import SME_COLUMNS, build_sme_out, to_verification_summary

_LIST_SQL = (
    "select v.id, v.status, v.business_reg_number, v.registered_name, v.submitted_at, "
    "v.reviewed_at, v.decision_note, s.id as sme_id, s.name as sme_name, s.slug as sme_slug "
    "from public.business_verifications v join public.smes s on s.id = v.sme_id "
)


def _list_item(row: dict) -> AdminVerificationListItem:
    return AdminVerificationListItem(
        **to_verification_summary(row).model_dump(),
        sme_id=str(row["sme_id"]),
        sme_name=row["sme_name"],
        sme_slug=row["sme_slug"],
    )


async def list_verifications(
    conn: AsyncConnection, status: Literal["SUBMITTED", "APPROVED", "REJECTED"] | None
) -> list[AdminVerificationListItem]:
    where = "where v.status = cast(:status as public.verification_decision) " if status else ""
    order = (
        "order by v.submitted_at asc" if status == "SUBMITTED" else "order by v.submitted_at desc"
    )
    rows = (
        (
            await conn.execute(text(_LIST_SQL + where + order + " limit 200"), {"status": status})  # noqa: S608
        )
        .mappings()
        .all()
    )
    return [_list_item(dict(r)) for r in rows]


async def get_verification(
    conn: AsyncConnection, storage: StorageClient, verification_id: str
) -> AdminVerificationDetail:
    row = (
        (
            await conn.execute(text(_LIST_SQL + "where v.id = :id"), {"id": verification_id})  # noqa: S608
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Verification request not found")

    sme_row = (
        (
            await conn.execute(
                text(f"select {SME_COLUMNS} from public.smes where id = :id"),  # noqa: S608
                {"id": row["sme_id"]},
            )
        )
        .mappings()
        .one()
    )
    documents = await evidence.list_evidence(
        conn,
        storage,
        where="verification_id = :vid",
        params={"vid": verification_id},
        with_download_urls=True,
    )
    history = (
        (
            await conn.execute(
                text(
                    "select id, status, business_reg_number, registered_name, submitted_at, "
                    "reviewed_at, decision_note from public.business_verifications "
                    "where sme_id = :sme and id <> :id order by submitted_at desc"
                ),
                {"sme": row["sme_id"], "id": verification_id},
            )
        )
        .mappings()
        .all()
    )

    return AdminVerificationDetail(
        **_list_item(dict(row)).model_dump(),
        sme=await build_sme_out(conn, storage, sme_row),
        documents=documents,
        history=[to_verification_summary(h) for h in history],
    )


async def decide_verification(
    conn: AsyncConnection,
    storage: StorageClient,
    admin: CurrentUser,
    verification_id: str,
    decision: VerificationDecisionIn,
) -> AdminVerificationDetail:
    row = (
        (
            await conn.execute(
                text(
                    "select v.id, v.sme_id, v.status from public.business_verifications v "
                    "where v.id = :id for update"
                ),
                {"id": verification_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Verification request not found")
    if row["status"] != "SUBMITTED":
        raise ConflictError("This request has already been decided", code="already_decided")

    approved = decision.decision == "APPROVED"
    await conn.execute(
        text(
            "update public.business_verifications set status = cast(:status as public.verification_decision), "
            "reviewed_by = :admin, reviewed_at = now(), decision_note = :note where id = :id"
        ),
        {
            "status": decision.decision,
            "admin": admin.id,
            "note": decision.note,
            "id": verification_id,
        },
    )
    if approved:
        await conn.execute(
            text(
                "update public.smes set verification_status = 'VERIFIED', verified_at = now(), "
                "contact_verified = :contact where id = :sme"
            ),
            {"contact": decision.contact_verified, "sme": row["sme_id"]},
        )
    else:
        await conn.execute(
            text("update public.smes set verification_status = 'REJECTED' where id = :sme"),
            {"sme": row["sme_id"]},
        )

    await conn.execute(
        text(
            "update public.evidence set review_status = cast(:review as public.evidence_review_status), "
            "reviewed_by = :admin, reviewed_at = now(), review_note = :note "
            "where verification_id = :id"
        ),
        {
            "review": "ACCEPTED" if approved else "REJECTED",
            "admin": admin.id,
            "note": decision.note,
            "id": verification_id,
        },
    )
    if approved:
        await evidence.insert_record_evidence(
            conn,
            evidence_type="VERIFICATION_RESULT",
            provenance="VERIFIED_FACT",
            sme_id=str(row["sme_id"]),
            source="ADMIN_REVIEW",
            description="Business registration verified by a Trustora administrator"
            + (" (contact details confirmed)" if decision.contact_verified else ""),
            created_by=admin.id,
            verification_id=verification_id,
        )

    await audit.record(
        conn,
        actor=admin,
        action="verification.approved" if approved else "verification.rejected",
        target_type="business_verification",
        target_id=verification_id,
        metadata={"sme_id": str(row["sme_id"]), "contact_verified": decision.contact_verified},
    )
    return await get_verification(conn, storage, verification_id)


# --- Social accounts ----------------------------------------------------------------
async def list_social_accounts(
    conn: AsyncConnection, *, pending_only: bool, account_id: str | None = None
) -> list[AdminSocialAccountItem]:
    if account_id:
        where = "where a.id = :id "
    elif pending_only:
        where = "where not a.ownership_verified "
    else:
        where = ""
    rows = (
        (
            await conn.execute(
                text(
                    "select a.id, a.platform, a.handle, a.url, a.ownership_verified, a.verified_at, "  # noqa: S608 — fixed column list, values are bound
                    "a.verification_code, a.created_at, s.id as sme_id, s.name as sme_name, "
                    "s.slug as sme_slug from public.sme_social_accounts a "
                    "join public.smes s on s.id = a.sme_id "
                    + where
                    + "order by a.created_at limit 200"
                ),
                {"id": account_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        AdminSocialAccountItem(**{**r, "id": str(r["id"]), "sme_id": str(r["sme_id"])})
        for r in rows
    ]


async def decide_social_account(
    conn: AsyncConnection, admin: CurrentUser, account_id: str, decision: SocialDecisionIn
) -> AdminSocialAccountItem:
    row = (
        (
            await conn.execute(
                text(
                    "update public.sme_social_accounts set ownership_verified = :verified, "
                    "verified_at = case when :verified then now() end, "
                    "verified_by = case when :verified then cast(:admin as uuid) end "
                    "where id = :id returning sme_id, platform, handle"
                ),
                {"verified": decision.verified, "admin": admin.id, "id": account_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Social account not found")

    if decision.verified:
        await evidence.insert_record_evidence(
            conn,
            evidence_type="VERIFICATION_RESULT",
            provenance="VERIFIED_FACT",
            sme_id=str(row["sme_id"]),
            source="ADMIN_REVIEW",
            description=f"Ownership of {row['platform']} account @{row['handle']} confirmed",
            created_by=admin.id,
        )
    await audit.record(
        conn,
        actor=admin,
        action="social_account.verified" if decision.verified else "social_account.unverified",
        target_type="social_account",
        target_id=account_id,
        metadata={"sme_id": str(row["sme_id"]), "platform": row["platform"]},
    )
    return (await list_social_accounts(conn, pending_only=False, account_id=account_id))[0]
