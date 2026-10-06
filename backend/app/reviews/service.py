"""Verified-purchase reviews: one per delivered order, with an optional public SME response."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.db import Database
from app.core.errors import ConflictError, NotFoundError, is_unique_violation
from app.reviews.schemas import ReviewCreate, ReviewOut, ReviewPage, SmeReviewOut
from app.smes.service import require_own_sme
from app.trust import trust_engine

REVIEW_WINDOW_DAYS = 90
_PUBLIC_COLUMNS = "id, rating, comment, sme_response, sme_responded_at, created_at"


def can_review(order: dict, has_review: bool) -> bool:
    if (
        has_review
        or order["status"] not in ("DELIVERED", "COMPLETED")
        or order["delivered_at"] is None
    ):
        return False
    return datetime.now(UTC) - order["delivered_at"] <= timedelta(days=REVIEW_WINDOW_DAYS)


async def get_order_review(conn: AsyncConnection, order_id: str) -> ReviewOut | None:
    row = (
        (
            await conn.execute(
                text(f"select {_PUBLIC_COLUMNS} from public.reviews where order_id = :id"),  # noqa: S608
                {"id": order_id},
            )
        )
        .mappings()
        .first()
    )
    return ReviewOut(**{**row, "id": str(row["id"])}) if row else None


async def create_review(
    conn: AsyncConnection, user: CurrentUser, order_id: str, data: ReviewCreate
) -> ReviewOut:
    order = (
        (
            await conn.execute(
                text(
                    "select id, sme_id, status, delivered_at from public.orders "
                    "where id = :id and customer_id = :uid"
                ),
                {"id": order_id, "uid": user.id},
            )
        )
        .mappings()
        .first()
    )
    if order is None:
        raise NotFoundError("Order not found")
    existing = await get_order_review(conn, order_id)
    if not can_review(dict(order), existing is not None):
        raise ConflictError(
            "Only delivered orders can be reviewed, once, within 90 days", code="review_not_allowed"
        )

    try:
        async with Database.privileged(conn):
            review_id = str(
                (
                    await conn.execute(
                        text(
                            "insert into public.reviews (order_id, sme_id, customer_id, rating, comment) "
                            "values (:order, :sme, :uid, :rating, :comment) returning id"
                        ),
                        {
                            "order": order_id,
                            "sme": order["sme_id"],
                            "uid": user.id,
                            "rating": data.rating,
                            "comment": data.comment,
                        },
                    )
                ).scalar_one()
            )
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise ConflictError(
                "This order has already been reviewed", code="review_not_allowed"
            ) from exc
        raise

    await audit.record(
        conn,
        actor=user,
        action="review.created",
        target_type="review",
        target_id=review_id,
        metadata={"order_id": order_id, "rating": data.rating},
    )
    await trust_engine.recalculate(conn, str(order["sme_id"]), trigger="review.created", actor=user)
    return ReviewOut(
        id=review_id, rating=data.rating, comment=data.comment, sme_response=None,
        sme_responded_at=None, created_at=datetime.now(UTC),
    )  # fmt: skip


async def public_reviews(conn: AsyncConnection, slug: str, page: int, page_size: int) -> ReviewPage:
    """Anon transaction: RLS exposes reviews of published stores without reviewer identity."""
    sme_id = (
        await conn.execute(
            text("select id from public.smes where slug = :slug"), {"slug": slug.lower()}
        )
    ).scalar_one_or_none()
    if sme_id is None:
        raise NotFoundError("Store not found")
    stats = (
        (
            await conn.execute(
                text(
                    "select rating, count(*) as n from public.reviews where sme_id = :id group by rating"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .all()
    )
    distribution = {r: 0 for r in range(1, 6)} | {row["rating"]: row["n"] for row in stats}
    count = sum(distribution.values())
    average = round(sum(r * n for r, n in distribution.items()) / count, 1) if count else None
    rows = (
        (
            await conn.execute(
                text(
                    f"select {_PUBLIC_COLUMNS} from public.reviews where sme_id = :id "  # noqa: S608
                    "order by created_at desc limit :limit offset :offset"
                ),
                {"id": sme_id, "limit": page_size, "offset": (page - 1) * page_size},
            )
        )
        .mappings()
        .all()
    )
    return ReviewPage(
        average=average,
        count=count,
        distribution=distribution,
        items=[ReviewOut(**{**r, "id": str(r["id"])}) for r in rows],
    )


_SME_SQL = (
    "select r.id, r.rating, r.comment, r.sme_response, r.sme_responded_at, r.created_at, "
    "o.order_number from public.reviews r join public.orders o on o.id = r.order_id "
    "where r.sme_id = :sme "
)


async def sme_reviews(
    conn: AsyncConnection, user: CurrentUser, review_id: str | None = None
) -> list[SmeReviewOut]:
    sme = await require_own_sme(conn, user)
    sql = (
        _SME_SQL + ("and r.id = :id " if review_id else "") + "order by r.created_at desc limit 200"
    )
    rows = (await conn.execute(text(sql), {"sme": sme["id"], "id": review_id})).mappings().all()
    return [SmeReviewOut(**{**r, "id": str(r["id"])}) for r in rows]


async def respond(
    conn: AsyncConnection, user: CurrentUser, review_id: str, response: str
) -> SmeReviewOut:
    sme = await require_own_sme(conn, user, active=True)
    async with Database.privileged(conn):
        updated = (
            await conn.execute(
                text(
                    "update public.reviews set sme_response = :response, sme_responded_at = now() "
                    "where id = :id and sme_id = :sme and sme_response is null returning id"
                ),
                {"response": response, "id": review_id, "sme": sme["id"]},
            )
        ).scalar_one_or_none()
    if updated is None:
        raise NotFoundError("Review not found or already answered")
    await audit.record(
        conn, actor=user, action="review.responded", target_type="review", target_id=review_id
    )
    return (await sme_reviews(conn, user, review_id))[0]
