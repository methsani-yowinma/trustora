"""Complaints: a customer allegation, the seller's response, and — if escalated — an admin decision.

Fact vs allegation: an open complaint is only ever presented as a *customer allegation*. It
carries no trust points; only an admin's UPHELD decision turns it into a verified finding.
Complaint text and evidence are private to the customer, the seller and admins.
"""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.complaints.schemas import (
    OPEN_STATUSES,
    ComplaintCategory,
    ComplaintDecisionIn,
    ComplaintOut,
    ComplaintSummaryItem,
    PublicComplaintSummary,
)
from app.core.db import Database
from app.core.errors import ConflictError, NotFoundError, is_unique_violation
from app.core.storage import PRIVATE_BUCKET, StorageClient, delete_quietly
from app.core.uploads import ValidatedFile
from app.evidence import service as evidence
from app.smes.service import require_own_sme
from app.trust import trust_engine

COMPLAINT_WINDOW_DAYS = 90
MAX_EVIDENCE_PER_COMPLAINT = 10
Viewer = Literal["CUSTOMER", "SME", "ADMIN"]

_COLUMNS = (
    "c.id, c.order_id, o.order_number, s.name as store_name, s.slug as store_slug, c.sme_id, "
    "c.customer_id, c.category, c.description, c.status, c.sme_response, c.sme_responded_at, "
    "c.escalated_at, c.resolution_note, c.decided_at, c.closed_at, c.created_at"
)
_FROM = (
    "from public.complaints c join public.orders o on o.id = c.order_id "
    "join public.smes s on s.id = c.sme_id "
)


def _actions(viewer: Viewer, status: str) -> list[str]:
    if status not in OPEN_STATUSES:
        return []
    if viewer == "CUSTOMER":
        return ["add_evidence"] + (["resolve", "escalate"] if status != "UNDER_REVIEW" else [])
    if viewer == "SME":
        return (["respond"] if status == "SUBMITTED" else []) + ["add_evidence"]
    return ["decide"]


async def _row(
    conn: AsyncConnection, complaint_id: str, where: str, params: dict[str, Any], lock: bool = False
) -> Mapping[str, Any]:
    sql = f"select {_COLUMNS} {_FROM} where c.id = :id and {where}"  # noqa: S608 — fixed fragments
    row = (await conn.execute(text(sql), {"id": complaint_id, **params})).mappings().first()
    if row is None:
        raise NotFoundError("Complaint not found")
    if lock:
        async with Database.privileged(conn):
            await conn.execute(
                text("select 1 from public.complaints where id = :id for update"),
                {"id": complaint_id},
            )
            row = (await conn.execute(text(sql), {"id": complaint_id, **params})).mappings().one()
    return row


async def _build(
    conn: AsyncConnection, storage: StorageClient, row: Mapping[str, Any], viewer: Viewer
) -> ComplaintOut:
    files = await evidence.list_evidence(
        conn,
        storage,
        where="complaint_id = :cid",
        params={"cid": row["id"]},
        with_download_urls=True,
    )
    return ComplaintOut(
        **{k: v for k, v in row.items() if k not in ("id", "order_id", "sme_id", "customer_id")},
        id=str(row["id"]),
        order_id=str(row["order_id"]),
        evidence=files,
        allowed_actions=_actions(viewer, row["status"]),
    )


def within_window(placed_at: datetime) -> bool:
    return datetime.now(UTC) - placed_at <= timedelta(days=COMPLAINT_WINDOW_DAYS)


# --- Customer ---------------------------------------------------------------------------------
async def create(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    order_id: str,
    *,
    category: ComplaintCategory,
    description: str,
    files: list[ValidatedFile],
) -> ComplaintOut:
    order = (
        (
            await conn.execute(
                text(
                    "select id, sme_id, placed_at from public.orders where id = :id and customer_id = :uid"
                ),
                {"id": order_id, "uid": user.id},
            )
        )
        .mappings()
        .first()
    )
    if order is None:
        raise NotFoundError("Order not found")
    if not within_window(order["placed_at"]):
        raise ConflictError(
            "Complaints can be raised within 90 days of the order", code="complaint_window_closed"
        )

    try:
        async with Database.privileged(conn):
            complaint_id = str(
                (
                    await conn.execute(
                        text(
                            "insert into public.complaints (order_id, sme_id, customer_id, category, description) "
                            "values (:order, :sme, :uid, cast(:category as public.complaint_category), :description) "
                            "returning id"
                        ),
                        {"order": order_id, "sme": order["sme_id"], "uid": user.id,
                         "category": category.value, "description": description},
                    )
                ).scalar_one()
            )  # fmt: skip
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise ConflictError(
                "This order already has an open complaint", code="complaint_open"
            ) from exc
        raise

    await _attach(conn, storage, user, complaint_id, str(order["sme_id"]), files, viewer="CUSTOMER")
    # Metadata never includes the complaint text.
    await audit.record(conn, actor=user, action="complaint.created", target_type="complaint",
                       target_id=complaint_id, metadata={"order_id": order_id, "category": category.value})  # fmt: skip
    await trust_engine.recalculate(
        conn, str(order["sme_id"]), trigger="complaint.created", actor=user
    )
    return await get_for_customer(conn, storage, user, complaint_id)


async def _attach(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    complaint_id: str,
    sme_id: str,
    files: list[ValidatedFile],
    *,
    viewer: Viewer,
    description: str | None = None,
) -> None:
    if not files:
        return
    count = (
        await conn.execute(
            text("select count(*) from public.evidence where complaint_id = :id"),
            {"id": complaint_id},
        )
    ).scalar_one()
    if count + len(files) > MAX_EVIDENCE_PER_COMPLAINT:
        raise ConflictError("Evidence limit reached for this complaint", code="limit_reached")
    is_customer = viewer == "CUSTOMER"
    uploaded: list[str] = []
    try:
        for file in files:
            stored = await evidence.store_private_file(storage, sme_id, file)
            uploaded.append(stored.path)
            await evidence.insert_file_evidence(
                conn,
                stored=stored,
                # A customer's upload supports an allegation; a seller's upload is the seller's claim.
                evidence_type="CUSTOMER_COMPLAINT" if is_customer else "SELLER_CLAIM",
                provenance="CUSTOMER_ALLEGATION" if is_customer else "SELLER_CLAIM",
                sme_id=sme_id,
                created_by=user.id,
                complaint_id=complaint_id,
                description=description
                or ("Customer complaint evidence" if is_customer else "Seller response evidence"),
            )
    except Exception:
        await delete_quietly(storage, PRIVATE_BUCKET, uploaded)
        raise


async def get_for_customer(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, complaint_id: str
) -> ComplaintOut:
    return await _build(
        conn,
        storage,
        await _row(conn, complaint_id, "c.customer_id = :uid", {"uid": user.id}),
        "CUSTOMER",
    )


async def list_for_customer(conn: AsyncConnection, user: CurrentUser) -> list[ComplaintSummaryItem]:
    return await _list(conn, "c.customer_id = :uid", {"uid": user.id})


async def customer_add_evidence(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, complaint_id: str,
    files: list[ValidatedFile], description: str | None,
) -> ComplaintOut:  # fmt: skip
    row = await _row(conn, complaint_id, "c.customer_id = :uid", {"uid": user.id}, lock=True)
    if "add_evidence" not in _actions("CUSTOMER", row["status"]):
        raise ConflictError("This complaint is closed", code="invalid_transition")
    await _attach(
        conn,
        storage,
        user,
        complaint_id,
        str(row["sme_id"]),
        files,
        viewer="CUSTOMER",
        description=description,
    )
    await audit.record(
        conn, actor=user, action="evidence.created", target_type="complaint", target_id=complaint_id
    )
    return await get_for_customer(conn, storage, user, complaint_id)


async def customer_transition(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, complaint_id: str,
    action: Literal["resolve", "escalate"],
) -> ComplaintOut:  # fmt: skip
    row = await _row(conn, complaint_id, "c.customer_id = :uid", {"uid": user.id}, lock=True)
    if action not in _actions("CUSTOMER", row["status"]):
        raise ConflictError(
            "That is not possible for this complaint now", code="invalid_transition"
        )
    sql = (
        "update public.complaints set status = 'RESOLVED', closed_at = now() where id = :id"
        if action == "resolve"
        else "update public.complaints set status = 'UNDER_REVIEW', escalated_at = now() where id = :id"
    )
    async with Database.privileged(conn):
        await conn.execute(text(sql), {"id": complaint_id})
    await audit.record(conn, actor=user, action=f"complaint.{'resolved' if action == 'resolve' else 'escalated'}",
                       target_type="complaint", target_id=complaint_id)  # fmt: skip
    await trust_engine.recalculate(
        conn, str(row["sme_id"]), trigger=f"complaint.{action}", actor=user
    )
    return await get_for_customer(conn, storage, user, complaint_id)


# --- SME ----------------------------------------------------------------------------------------
async def get_for_sme(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, complaint_id: str
) -> ComplaintOut:
    sme = await require_own_sme(conn, user)
    return await _build(
        conn, storage, await _row(conn, complaint_id, "c.sme_id = :sme", {"sme": sme["id"]}), "SME"
    )


async def list_for_sme(
    conn: AsyncConnection, user: CurrentUser, status: str | None
) -> list[ComplaintSummaryItem]:
    sme = await require_own_sme(conn, user)
    where = "c.sme_id = :sme" + (
        " and c.status = cast(:status as public.complaint_status)" if status else ""
    )
    return await _list(conn, where, {"sme": sme["id"], "status": status})


async def sme_respond(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    complaint_id: str,
    response: str,
) -> ComplaintOut:
    sme = await require_own_sme(conn, user)
    row = await _row(conn, complaint_id, "c.sme_id = :sme", {"sme": sme["id"]}, lock=True)
    if "respond" not in _actions("SME", row["status"]):
        raise ConflictError(
            "This complaint has already been answered or closed", code="invalid_transition"
        )
    async with Database.privileged(conn):
        await conn.execute(
            text(
                "update public.complaints set status = 'SME_RESPONDED', sme_response = :response, "
                "sme_responded_at = now() where id = :id"
            ),
            {"response": response, "id": complaint_id},
        )
    await audit.record(
        conn,
        actor=user,
        action="complaint.responded",
        target_type="complaint",
        target_id=complaint_id,
    )
    await trust_engine.recalculate(conn, str(sme["id"]), trigger="complaint.responded", actor=user)
    return await get_for_sme(conn, storage, user, complaint_id)


async def sme_add_evidence(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, complaint_id: str,
    files: list[ValidatedFile], description: str | None,
) -> ComplaintOut:  # fmt: skip
    sme = await require_own_sme(conn, user)
    row = await _row(conn, complaint_id, "c.sme_id = :sme", {"sme": sme["id"]}, lock=True)
    if "add_evidence" not in _actions("SME", row["status"]):
        raise ConflictError("This complaint is closed", code="invalid_transition")
    await _attach(
        conn,
        storage,
        user,
        complaint_id,
        str(sme["id"]),
        files,
        viewer="SME",
        description=description,
    )
    await audit.record(
        conn, actor=user, action="evidence.created", target_type="complaint", target_id=complaint_id
    )
    return await get_for_sme(conn, storage, user, complaint_id)


# --- Admin ----------------------------------------------------------------------------------------
async def get_for_admin(
    conn: AsyncConnection, storage: StorageClient, complaint_id: str
) -> ComplaintOut:
    return await _build(conn, storage, await _row(conn, complaint_id, "true", {}), "ADMIN")


async def list_for_admin(conn: AsyncConnection, status: str | None) -> list[ComplaintSummaryItem]:
    where = "c.status = cast(:status as public.complaint_status)" if status else "true"
    return await _list(conn, where, {"status": status})


async def admin_decide(
    conn: AsyncConnection,
    storage: StorageClient,
    admin: CurrentUser,
    complaint_id: str,
    decision: ComplaintDecisionIn,
) -> ComplaintOut:
    row = await _row(conn, complaint_id, "true", {}, lock=True)
    if row["status"] not in OPEN_STATUSES:
        raise ConflictError("This complaint has already been closed", code="already_decided")

    decided = decision.decision in ("UPHELD", "DISMISSED")
    async with Database.privileged(conn):
        await conn.execute(
            text(
                "update public.complaints set status = cast(:status as public.complaint_status), "
                "resolution_note = :note, decided_by = :admin, closed_at = now(), "
                "decided_at = case when :decided then now() end where id = :id"
            ),
            {
                "status": decision.decision,
                "note": decision.note,
                "admin": admin.id,
                "decided": decided,
                "id": complaint_id,
            },
        )
        if decision.decision == "UPHELD":
            # The customer's supporting evidence was accepted as part of the finding.
            await conn.execute(
                text(
                    "update public.evidence set review_status = 'ACCEPTED', reviewed_by = :admin, "
                    "reviewed_at = now() where complaint_id = :id and provenance = 'CUSTOMER_ALLEGATION' "
                    "and review_status = 'PENDING'"
                ),
                {"admin": admin.id, "id": complaint_id},
            )
    await audit.record(conn, actor=admin, action=f"complaint.{decision.decision.lower()}", target_type="complaint",
                       target_id=complaint_id, metadata={"category": row["category"]})  # fmt: skip
    await trust_engine.recalculate(
        conn, str(row["sme_id"]), trigger=f"complaint.{decision.decision.lower()}", actor=admin
    )
    return await get_for_admin(conn, storage, complaint_id)


# --- Shared ----------------------------------------------------------------------------------------
async def _list(
    conn: AsyncConnection, where: str, params: dict[str, Any]
) -> list[ComplaintSummaryItem]:
    sql = (
        "select c.id, o.order_number, s.name as store_name, c.category, c.status, c.created_at, "
        f"c.escalated_at {_FROM} where {where} order by c.created_at desc limit 200"  # noqa: S608
    )
    async with Database.privileged(conn):
        # Privileged so store names resolve even for unpublished stores; `where` always scopes
        # the rows to the caller (customer, own SME, or admin route).
        rows = (await conn.execute(text(sql), params)).mappings().all()
    return [ComplaintSummaryItem(**{**r, "id": str(r["id"])}) for r in rows]


async def latest_for_order(conn: AsyncConnection, order_id: str) -> ComplaintSummaryItem | None:
    items = await _list(conn, "c.order_id = :order", {"order": order_id})
    return items[0] if items else None


async def public_summary(conn: AsyncConnection, slug: str) -> PublicComplaintSummary:
    """Anon transaction: the store must be visible to the public; counts are computed privileged."""
    sme_id = (
        await conn.execute(
            text("select id from public.smes where slug = :slug"), {"slug": slug.lower()}
        )
    ).scalar_one_or_none()
    if sme_id is None:
        raise NotFoundError("Store not found")
    async with Database.privileged(conn):
        rows = (
            (
                await conn.execute(
                    text(
                        "select category, status, count(*) as n from public.complaints where sme_id = :id group by 1, 2"
                    ),
                    {"id": sme_id},
                )
            )
            .mappings()
            .all()
        )
    open_allegations: dict[str, int] = {}
    upheld: dict[str, int] = {}
    resolved = dismissed = 0
    for r in rows:
        if r["status"] in OPEN_STATUSES:
            open_allegations[r["category"]] = open_allegations.get(r["category"], 0) + r["n"]
        elif r["status"] == "UPHELD":
            upheld[r["category"]] = upheld.get(r["category"], 0) + r["n"]
        elif r["status"] == "RESOLVED":
            resolved += r["n"]
        else:
            dismissed += r["n"]
    return PublicComplaintSummary(
        open_allegations=open_allegations,  # type: ignore[arg-type]
        upheld=upheld,  # type: ignore[arg-type]
        resolved=resolved,
        dismissed=dismissed,
        total=sum(r["n"] for r in rows),
    )
