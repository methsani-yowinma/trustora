from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_anon_db, get_storage, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.core.rate_limit import rate_limit
from app.core.storage import StorageClient
from app.orders import service
from app.orders.schemas import (
    CheckoutRequest,
    CustomerCancel,
    OrderOut,
    OrderStatus,
    OrderSummary,
    QuoteOut,
    QuoteRequest,
    SmeStatusUpdate,
)

Db = Annotated[AsyncConnection, Depends(get_user_db, scope="function")]
AnonDb = Annotated[AsyncConnection, Depends(get_anon_db, scope="function")]
Storage = Annotated[StorageClient, Depends(get_storage)]
Customer = Annotated[CurrentUser, Depends(require_role(UserRole.CUSTOMER))]
Sme = Annotated[CurrentUser, Depends(require_role(UserRole.SME))]

# --- Customer ---------------------------------------------------------------------------
router = APIRouter(tags=["orders"])


@router.post("/checkout/quote", response_model=QuoteOut)
async def quote(request: QuoteRequest, conn: AnonDb, storage: Storage) -> QuoteOut:
    """Server-side pricing of a cart. Public, so a cart can be reviewed before signing in."""
    return await service.quote_request(conn, storage, request)


@router.post(
    "/checkout",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("10/minute", scope="checkout"))],
)
async def checkout(
    request: CheckoutRequest, user: Customer, conn: Db, storage: Storage
) -> OrderOut:
    return await service.checkout(conn, storage, user, request)


@router.get("/orders", response_model=list[OrderSummary])
async def list_orders(user: Customer, conn: Db) -> list[OrderSummary]:
    return await service.list_customer_orders(conn, user)


@router.get("/orders/{order_id}", response_model=OrderOut)
async def get_order(order_id: UUID, user: Customer, conn: Db) -> OrderOut:
    return await service.get_customer_order(conn, user, str(order_id))


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(
    order_id: UUID, user: Customer, conn: Db, body: Annotated[CustomerCancel | None, Body()] = None
) -> OrderOut:
    return await service.customer_cancel(conn, user, str(order_id), body.reason if body else None)


@router.post("/orders/{order_id}/confirm-receipt", response_model=OrderOut)
async def confirm_receipt(order_id: UUID, user: Customer, conn: Db) -> OrderOut:
    return await service.confirm_receipt(conn, user, str(order_id))


# --- SME ------------------------------------------------------------------------------------
sme_router = APIRouter(prefix="/sme/orders", tags=["sme-orders"])


@sme_router.get("", response_model=list[OrderSummary])
async def list_sme_orders(
    user: Sme, conn: Db, status: OrderStatus | None = None
) -> list[OrderSummary]:
    return await service.list_sme_orders(conn, user, status)


@sme_router.get("/{order_id}", response_model=OrderOut)
async def get_sme_order(order_id: UUID, user: Sme, conn: Db) -> OrderOut:
    return await service.get_sme_order(conn, user, str(order_id))


@sme_router.post("/{order_id}/status", response_model=OrderOut)
async def update_status(order_id: UUID, update: SmeStatusUpdate, user: Sme, conn: Db) -> OrderOut:
    return await service.sme_update_status(conn, user, str(order_id), update)
