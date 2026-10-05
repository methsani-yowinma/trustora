"""Cart quotes, checkout and the order state machine.

Prices, stock and totals are always recomputed from the database: the client's cart is only a
list of product ids and quantities. Order rows, stock changes, payments and deliveries are
written privileged after the caller's authorization has been checked here.
"""

import json
import secrets
import string
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.db import Database
from app.core.errors import ConflictError, NotFoundError, ValidationAppError, is_unique_violation
from app.core.storage import PUBLIC_BUCKET, StorageClient
from app.deliveries.provider import get_provider
from app.orders import payment_provider
from app.orders.schemas import (
    CartLine,
    CheckoutRequest,
    DeliveryOut,
    DeliveryQuoteOut,
    OrderItemOut,
    OrderOut,
    OrderSummary,
    PaymentOut,
    QuoteLine,
    QuoteOut,
    QuoteRequest,
    SmeStatusUpdate,
    StoreRef,
)
from app.smes.service import require_own_sme
from app.trust import trust_engine

# Sri Lanka Standard Time is a fixed UTC+05:30 (no daylight saving).
SRI_LANKA = timezone(timedelta(hours=5, minutes=30))

# Who may do what, in which order status.
CUSTOMER_ACTIONS: dict[str, list[str]] = {"PLACED": ["cancel"], "DELIVERED": ["confirm_receipt"]}
SME_ACTIONS: dict[str, list[str]] = {
    "PLACED": ["confirm", "cancel"],
    "CONFIRMED": ["dispatch", "cancel"],
    "DISPATCHED": ["in_transit", "delivered", "failed"],
}


# --- Quotes ---------------------------------------------------------------------------------
async def _store_ref(conn: AsyncConnection, sme_id: Any) -> StoreRef:
    row = (
        (
            await conn.execute(
                text(
                    "select s.id, s.slug, s.name, s.verification_status, t.level, t.overall_score "
                    "from public.smes s left join public.trust_scores t on t.sme_id = s.id where s.id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .one()
    )
    return StoreRef(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        verification_status=row["verification_status"],
        trust_level=row["level"],
        trust_score=row["overall_score"],
    )


async def quote(
    conn: AsyncConnection, storage: StorageClient, items: list[CartLine], district: str
) -> QuoteOut:
    """Uses the caller's RLS: only ACTIVE products of published, active stores are visible."""
    ids = [str(line.product_id) for line in items]
    rows = {
        str(r["id"]): r
        for r in (
            await conn.execute(
                text(
                    "select p.id, p.sme_id, p.name_i18n, p.price_lkr, p.stock, "
                    "(select storage_path from public.product_images i where i.product_id = p.id "
                    " order by sort_order limit 1) as image_path "
                    "from public.products p where p.id in :ids and p.status = 'ACTIVE'"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": ids},
            )
        ).mappings()
    }
    if not rows:
        raise ValidationAppError("None of these products are available", code="cart_unavailable")
    sme_ids = {r["sme_id"] for r in rows.values()}
    if len(sme_ids) > 1:
        raise ValidationAppError(
            "A cart can only contain products from one store", code="multiple_stores"
        )
    sme_id = sme_ids.pop()

    lines: list[QuoteLine] = []
    issues: list[str] = []
    subtotal = Decimal("0")
    for line in items:
        pid = str(line.product_id)
        row = rows.get(pid)
        if row is None:
            issues.append(f"unavailable:{pid}")
            continue
        stock_ok = row["stock"] >= line.quantity
        if not stock_ok:
            issues.append(f"insufficient_stock:{pid}")
        line_total = row["price_lkr"] * line.quantity
        subtotal += line_total
        lines.append(
            QuoteLine(
                product_id=pid,
                name_i18n=row["name_i18n"],
                image_url=storage.public_url(PUBLIC_BUCKET, row["image_path"])
                if row["image_path"]
                else None,
                unit_price_lkr=row["price_lkr"],
                quantity=line.quantity,
                line_total_lkr=line_total,
                available=True,
                in_stock_quantity_ok=stock_ok,
            )
        )

    delivery = get_provider().quote(district)  # type: ignore[arg-type]
    fee = Decimal(delivery.fee_lkr).quantize(Decimal("0.01"))
    return QuoteOut(
        store=await _store_ref(conn, sme_id),
        lines=lines,
        subtotal_lkr=subtotal,
        delivery=DeliveryQuoteOut(
            provider_code=delivery.provider_code, fee_lkr=fee, eta_days=delivery.eta_days
        ),
        total_lkr=subtotal + fee,
        issues=issues,
    )


async def quote_request(
    conn: AsyncConnection, storage: StorageClient, request: QuoteRequest
) -> QuoteOut:
    return await quote(conn, storage, request.items, request.district)


# --- Checkout ------------------------------------------------------------------------------
def _order_number() -> str:
    return "TR-" + "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def checkout(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, request: CheckoutRequest
) -> OrderOut:
    existing = (
        await conn.execute(
            text(
                "select id from public.orders where customer_id = :uid and idempotency_key = :key"
            ),
            {"uid": user.id, "key": request.idempotency_key},
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await get_customer_order(conn, user, str(existing))

    priced = await quote(conn, storage, request.items, request.shipping_address.district)
    if priced.issues:
        raise ConflictError(
            "Some items are no longer available in that quantity", code="cart_changed"
        )
    if priced.total_lkr != request.expected_total_lkr:
        raise ConflictError("Prices changed since you reviewed your cart", code="price_changed")

    payment = payment_provider.authorize(request.payment_method)
    try:
        async with Database.privileged(conn):
            # Reserve stock atomically; a concurrent purchase of the last unit makes this fail.
            for line in priced.lines:
                reserved = await conn.execute(
                    text(
                        "update public.products set stock = stock - :qty "
                        "where id = :id and status = 'ACTIVE' and stock >= :qty"
                    ),
                    {"qty": line.quantity, "id": line.product_id},
                )
                if reserved.rowcount != 1:
                    raise ConflictError("An item just sold out", code="cart_changed")

            order_id = str(
                (
                    await conn.execute(
                        text(
                            "insert into public.orders (order_number, customer_id, sme_id, "
                            "subtotal_lkr, delivery_fee_lkr, total_lkr, shipping_address, "
                            "payment_method, idempotency_key) values (:number, :customer, :sme, "
                            ":subtotal, :fee, :total, cast(:address as jsonb), "
                            "cast(:method as public.payment_method), :key) returning id"
                        ),
                        {
                            "number": _order_number(),
                            "customer": user.id,
                            "sme": priced.store.id,
                            "subtotal": priced.subtotal_lkr,
                            "fee": priced.delivery.fee_lkr,
                            "total": priced.total_lkr,
                            "address": json.dumps(request.shipping_address.model_dump()),
                            "method": request.payment_method,
                            "key": request.idempotency_key,
                        },
                    )
                ).scalar_one()
            )
            await conn.execute(
                text(
                    "insert into public.order_items (order_id, product_id, product_name_i18n, "
                    "unit_price_lkr, quantity, line_total_lkr) values (:order, :product, "
                    "cast(:name as jsonb), :price, :qty, :total)"
                ),
                [
                    {
                        "order": order_id,
                        "product": line.product_id,
                        "name": json.dumps(line.name_i18n),
                        "price": line.unit_price_lkr,
                        "qty": line.quantity,
                        "total": line.line_total_lkr,
                    }
                    for line in priced.lines
                ],
            )
            await conn.execute(
                text(
                    "insert into public.payments (order_id, method, status, amount_lkr, "
                    "mock_reference, paid_at) values (:order, cast(:method as public.payment_method), "
                    "cast(:status as public.payment_status), :amount, :ref, "
                    "case when :status = 'PAID' then now() end)"
                ),
                {
                    "order": order_id,
                    "method": request.payment_method,
                    "status": payment.status,
                    "amount": priced.total_lkr,
                    "ref": payment.mock_reference,
                },
            )
            await conn.execute(
                text(
                    "insert into public.deliveries (order_id, provider_code, district, fee_lkr, eta_days) "
                    "values (:order, :provider, :district, :fee, :eta)"
                ),
                {
                    "order": order_id,
                    "provider": priced.delivery.provider_code,
                    "district": request.shipping_address.district,
                    "fee": priced.delivery.fee_lkr,
                    "eta": priced.delivery.eta_days,
                },
            )
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise ConflictError(
                "This order was already submitted", code="duplicate_submission"
            ) from exc
        raise

    await audit.record(
        conn,
        actor=user,
        action="order.placed",
        target_type="order",
        target_id=order_id,
        metadata={
            "sme_id": priced.store.id,
            "total_lkr": str(priced.total_lkr),
            "payment": request.payment_method,
        },
    )
    return await get_customer_order(conn, user, order_id)


# --- Loading --------------------------------------------------------------------------------
_ORDER_COLUMNS = (
    "id, order_number, status, sme_id, customer_id, subtotal_lkr, delivery_fee_lkr, total_lkr, "
    "shipping_address, placed_at, confirmed_at, dispatched_at, delivered_at, completed_at, "
    "cancelled_at, cancelled_by, cancellation_reason"
)


async def _order_row(
    conn: AsyncConnection,
    order_id: str,
    *,
    where: str,
    params: dict[str, Any],
    lock: bool = False,
) -> Mapping[str, Any]:
    """Loads an order the caller is a party to. ``where`` is a fixed SQL fragment.

    With ``lock``, the row is re-read FOR UPDATE (privileged: clients have no update grant) so
    concurrent state changes on the same order are serialized.
    """
    sql = f"select {_ORDER_COLUMNS} from public.orders where id = :id and {where}"  # noqa: S608
    row = (await conn.execute(text(sql), {"id": order_id, **params})).mappings().first()
    if row is None:
        raise NotFoundError("Order not found")
    if lock:
        async with Database.privileged(conn):
            row = (
                (await conn.execute(text(sql + " for update"), {"id": order_id, **params}))
                .mappings()
                .one()
            )
    return row


async def _build(conn: AsyncConnection, row: Mapping[str, Any], actions: list[str]) -> OrderOut:
    items = (
        (
            await conn.execute(
                text(
                    "select product_id, product_name_i18n, unit_price_lkr, quantity, line_total_lkr "
                    "from public.order_items where order_id = :id order by id"
                ),
                {"id": row["id"]},
            )
        )
        .mappings()
        .all()
    )
    payment = (
        (
            await conn.execute(
                text(
                    "select method, status, amount_lkr, mock_reference, paid_at, refunded_at "
                    "from public.payments where order_id = :id"
                ),
                {"id": row["id"]},
            )
        )
        .mappings()
        .one()
    )
    delivery = (
        (
            await conn.execute(
                text(
                    "select provider_code, district, fee_lkr, eta_days, status, tracking_ref, "
                    "estimated_delivery_date, dispatched_at, in_transit_at, delivered_at, failed_at, "
                    "failure_reason from public.deliveries where order_id = :id"
                ),
                {"id": row["id"]},
            )
        )
        .mappings()
        .one()
    )
    async with Database.privileged(conn):
        # Store identity and trust are public facts, readable even if the store is now unpublished.
        store = await _store_ref(conn, row["sme_id"])

    return OrderOut(
        id=str(row["id"]),
        order_number=row["order_number"],
        status=row["status"],
        store=store,
        items=[OrderItemOut(**{**i, "product_id": str(i["product_id"])}) for i in items],
        subtotal_lkr=row["subtotal_lkr"],
        delivery_fee_lkr=row["delivery_fee_lkr"],
        total_lkr=row["total_lkr"],
        shipping_address=row["shipping_address"],
        payment=PaymentOut(**payment),
        delivery=DeliveryOut(**delivery),
        placed_at=row["placed_at"],
        confirmed_at=row["confirmed_at"],
        dispatched_at=row["dispatched_at"],
        delivered_at=row["delivered_at"],
        completed_at=row["completed_at"],
        cancelled_at=row["cancelled_at"],
        cancelled_by=row["cancelled_by"],
        cancellation_reason=row["cancellation_reason"],
        allowed_actions=actions,
    )


async def get_customer_order(conn: AsyncConnection, user: CurrentUser, order_id: str) -> OrderOut:
    row = await _order_row(conn, order_id, where="customer_id = :uid", params={"uid": user.id})
    return await _build(conn, row, CUSTOMER_ACTIONS.get(row["status"], []))


async def _sme_actions(conn: AsyncConnection, row: Mapping[str, Any]) -> list[str]:
    actions = list(SME_ACTIONS.get(row["status"], []))
    if "in_transit" in actions:
        status = (
            await conn.execute(
                text("select status from public.deliveries where order_id = :id"), {"id": row["id"]}
            )
        ).scalar_one()
        if status != "DISPATCHED":
            actions.remove("in_transit")
    return actions


async def get_sme_order(conn: AsyncConnection, user: CurrentUser, order_id: str) -> OrderOut:
    sme = await require_own_sme(conn, user)
    row = await _order_row(conn, order_id, where="sme_id = :sme", params={"sme": sme["id"]})
    return await _build(conn, row, await _sme_actions(conn, row))


_SUMMARY_SQL = (
    "select o.id, o.order_number, o.status, s.name as store_name, s.slug as store_slug, "
    "o.total_lkr, o.placed_at, d.status as delivery_status, "
    "(select coalesce(sum(quantity), 0) from public.order_items i where i.order_id = o.id) as item_count "
    "from public.orders o join public.deliveries d on d.order_id = o.id "
    "join public.smes s on s.id = o.sme_id "
)


async def list_customer_orders(conn: AsyncConnection, user: CurrentUser) -> list[OrderSummary]:
    async with Database.privileged(conn):
        rows = (
            (
                await conn.execute(
                    text(
                        _SUMMARY_SQL
                        + "where o.customer_id = :uid order by o.placed_at desc limit 100"
                    ),
                    {"uid": user.id},
                )
            )
            .mappings()
            .all()
        )
    return [OrderSummary(**{**r, "id": str(r["id"])}) for r in rows]


async def list_sme_orders(
    conn: AsyncConnection, user: CurrentUser, status: str | None
) -> list[OrderSummary]:
    sme = await require_own_sme(conn, user)
    where = "where o.sme_id = :sme " + (
        "and o.status = cast(:status as public.order_status) " if status else ""
    )
    rows = (
        (
            await conn.execute(
                text(_SUMMARY_SQL + where + "order by o.placed_at desc limit 200"),  # noqa: S608
                {"sme": sme["id"], "status": status},
            )
        )
        .mappings()
        .all()
    )
    return [OrderSummary(**{**r, "id": str(r["id"])}) for r in rows]


# --- State changes ----------------------------------------------------------------------------
async def _restock(conn: AsyncConnection, order_id: str) -> None:
    await conn.execute(
        text(
            "update public.products p set stock = p.stock + i.quantity from public.order_items i "
            "where i.order_id = :id and p.id = i.product_id"
        ),
        {"id": order_id},
    )


async def _refund_if_paid(conn: AsyncConnection, order_id: str) -> None:
    await conn.execute(
        text(
            "update public.payments set status = 'REFUNDED', refunded_at = now() "
            "where order_id = :id and status = 'PAID'"
        ),
        {"id": order_id},
    )


async def _cancel(conn: AsyncConnection, order_id: str, by: str, reason: str | None) -> None:
    await conn.execute(
        text(
            "update public.orders set status = 'CANCELLED', cancelled_at = now(), "
            "cancelled_by = cast(:by as public.user_role), cancellation_reason = :reason where id = :id"
        ),
        {"by": by, "reason": reason, "id": order_id},
    )
    await _restock(conn, order_id)
    await _refund_if_paid(conn, order_id)


async def customer_cancel(
    conn: AsyncConnection, user: CurrentUser, order_id: str, reason: str | None
) -> OrderOut:
    row = await _order_row(
        conn, order_id, where="customer_id = :uid", params={"uid": user.id}, lock=True
    )
    if "cancel" not in CUSTOMER_ACTIONS.get(row["status"], []):
        raise ConflictError("This order can no longer be cancelled", code="invalid_transition")
    async with Database.privileged(conn):
        await _cancel(conn, order_id, "CUSTOMER", reason)
    await audit.record(conn, actor=user, action="order.cancelled", target_type="order", target_id=order_id,
                       metadata={"by": "CUSTOMER"})  # fmt: skip
    return await get_customer_order(conn, user, order_id)


async def confirm_receipt(conn: AsyncConnection, user: CurrentUser, order_id: str) -> OrderOut:
    row = await _order_row(
        conn, order_id, where="customer_id = :uid", params={"uid": user.id}, lock=True
    )
    if "confirm_receipt" not in CUSTOMER_ACTIONS.get(row["status"], []):
        raise ConflictError(
            "Receipt can only be confirmed after delivery", code="invalid_transition"
        )
    async with Database.privileged(conn):
        await conn.execute(
            text(
                "update public.orders set status = 'COMPLETED', completed_at = now() where id = :id"
            ),
            {"id": order_id},
        )
    await audit.record(
        conn, actor=user, action="order.completed", target_type="order", target_id=order_id
    )
    return await get_customer_order(conn, user, order_id)


async def sme_update_status(
    conn: AsyncConnection, user: CurrentUser, order_id: str, update: SmeStatusUpdate
) -> OrderOut:
    sme = await require_own_sme(conn, user)
    row = await _order_row(
        conn, order_id, where="sme_id = :sme", params={"sme": sme["id"]}, lock=True
    )
    if update.action not in await _sme_actions(conn, row):
        raise ConflictError(
            "That action is not possible for this order now", code="invalid_transition"
        )

    affects_trust = update.action in ("cancel", "delivered", "failed")
    async with Database.privileged(conn):
        if update.action == "confirm":
            await conn.execute(
                text(
                    "update public.orders set status = 'CONFIRMED', confirmed_at = now() where id = :id"
                ),
                {"id": order_id},
            )
        elif update.action == "cancel":
            await _cancel(conn, order_id, "SME", update.reason)
        elif update.action == "dispatch":
            delivery = (
                (
                    await conn.execute(
                        text(
                            "select provider_code, eta_days from public.deliveries where order_id = :id"
                        ),
                        {"id": order_id},
                    )
                )
                .mappings()
                .one()
            )
            tracking = get_provider(delivery["provider_code"]).create_shipment(row["order_number"])
            today = datetime.now(SRI_LANKA).date()
            await conn.execute(
                text(
                    "update public.deliveries set status = 'DISPATCHED', dispatched_at = now(), "
                    "tracking_ref = :tracking, estimated_delivery_date = :eta where order_id = :id"
                ),
                {
                    "tracking": tracking,
                    "eta": today + timedelta(days=delivery["eta_days"]),
                    "id": order_id,
                },
            )
            await conn.execute(
                text(
                    "update public.orders set status = 'DISPATCHED', dispatched_at = now() where id = :id"
                ),
                {"id": order_id},
            )
        elif update.action == "in_transit":
            await conn.execute(
                text(
                    "update public.deliveries set status = 'IN_TRANSIT', in_transit_at = now() where order_id = :id"
                ),
                {"id": order_id},
            )
        elif update.action == "delivered":
            await conn.execute(
                text(
                    "update public.deliveries set status = 'DELIVERED', delivered_at = now() where order_id = :id"
                ),
                {"id": order_id},
            )
            await conn.execute(
                text(
                    "update public.orders set status = 'DELIVERED', delivered_at = now() where id = :id"
                ),
                {"id": order_id},
            )
            # Cash on delivery is collected at the door.
            await conn.execute(
                text(
                    "update public.payments set status = 'PAID', paid_at = now() "
                    "where order_id = :id and method = 'COD' and status = 'PENDING'"
                ),
                {"id": order_id},
            )
        elif update.action == "failed":
            await conn.execute(
                text(
                    "update public.deliveries set status = 'FAILED', failed_at = now(), "
                    "failure_reason = :reason where order_id = :id"
                ),
                {"reason": update.reason, "id": order_id},
            )
            await conn.execute(
                text("update public.orders set status = 'DELIVERY_FAILED' where id = :id"),
                {"id": order_id},
            )
            await _refund_if_paid(conn, order_id)

    await audit.record(
        conn,
        actor=user,
        action=f"order.{update.action}",
        target_type="order",
        target_id=order_id,
        metadata={"reason": update.reason} if update.reason else None,
    )
    if affects_trust:
        await trust_engine.recalculate(
            conn, str(sme["id"]), trigger=f"order.{update.action}", actor=user
        )
    return await get_sme_order(conn, user, order_id)
