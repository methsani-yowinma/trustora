from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.complaints.schemas import ComplaintSummaryItem
from app.deliveries.provider import District
from app.reviews.schemas import ReviewOut
from app.trust.schemas import Level

OrderStatus = Literal[
    "PLACED", "CONFIRMED", "DISPATCHED", "DELIVERED", "COMPLETED", "CANCELLED", "DELIVERY_FAILED"
]
PaymentMethod = Literal["COD", "MOCK_CARD"]
MAX_LINES = 20


class CartLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: int = Field(ge=1, le=10)


class _CartBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CartLine] = Field(min_length=1, max_length=MAX_LINES)
    district: District

    @model_validator(mode="after")
    def _unique_products(self) -> "_CartBase":
        ids = [line.product_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once")
        return self


class QuoteRequest(_CartBase):
    pass


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class ShippingAddress(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    recipient_name: Text
    phone: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9 ]{7,20}$")]
    address_line1: Annotated[str, StringConstraints(min_length=3, max_length=200)]
    address_line2: Annotated[str, StringConstraints(max_length=200)] | None = None
    city: Text
    district: District
    postal_code: Annotated[str, StringConstraints(pattern=r"^[0-9]{5}$")] | None = None


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CartLine] = Field(min_length=1, max_length=MAX_LINES)
    shipping_address: ShippingAddress
    payment_method: PaymentMethod
    # Retried submissions with the same key return the same order instead of a duplicate.
    idempotency_key: UUID
    # The total the customer saw; checkout is refused if prices changed since.
    expected_total_lkr: Decimal = Field(gt=0, max_digits=12, decimal_places=2)

    @model_validator(mode="after")
    def _unique_products(self) -> "CheckoutRequest":
        ids = [line.product_id for line in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Each product may appear only once")
        return self


class QuoteLine(BaseModel):
    product_id: str
    name_i18n: dict[str, str]
    image_url: str | None
    unit_price_lkr: Decimal
    quantity: int
    line_total_lkr: Decimal
    available: bool
    in_stock_quantity_ok: bool


class StoreRef(BaseModel):
    id: str
    slug: str
    name: str
    verification_status: str
    trust_level: Level | None
    trust_score: int | None


class DeliveryQuoteOut(BaseModel):
    provider_code: str
    fee_lkr: Decimal
    eta_days: int


class QuoteOut(BaseModel):
    store: StoreRef
    lines: list[QuoteLine]
    subtotal_lkr: Decimal
    delivery: DeliveryQuoteOut
    total_lkr: Decimal
    # Problems that block checkout: "unavailable:<product_id>", "insufficient_stock:<product_id>".
    issues: list[str]

    @property
    def ok(self) -> bool:
        return not self.issues


class OrderItemOut(BaseModel):
    product_id: str
    product_name_i18n: dict[str, str]
    unit_price_lkr: Decimal
    quantity: int
    line_total_lkr: Decimal


class PaymentOut(BaseModel):
    method: PaymentMethod
    status: Literal["PENDING", "PAID", "REFUNDED"]
    amount_lkr: Decimal
    mock_reference: str | None
    paid_at: datetime | None
    refunded_at: datetime | None


class DeliveryOut(BaseModel):
    provider_code: str
    district: str
    fee_lkr: Decimal
    eta_days: int
    status: Literal["PENDING", "DISPATCHED", "IN_TRANSIT", "DELIVERED", "FAILED"]
    tracking_ref: str | None
    estimated_delivery_date: date | None
    dispatched_at: datetime | None
    in_transit_at: datetime | None
    delivered_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None


class OrderOut(BaseModel):
    id: str
    order_number: str
    status: OrderStatus
    store: StoreRef
    items: list[OrderItemOut]
    subtotal_lkr: Decimal
    delivery_fee_lkr: Decimal
    total_lkr: Decimal
    shipping_address: dict[str, str | None]
    payment: PaymentOut
    delivery: DeliveryOut
    placed_at: datetime
    confirmed_at: datetime | None
    dispatched_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: Literal["CUSTOMER", "SME", "ADMIN"] | None
    cancellation_reason: str | None
    # Actions the caller may take now (e.g. ["cancel"], ["confirm_receipt"], ["review"], ["complain"]).
    allowed_actions: list[str]
    review: ReviewOut | None = None
    complaint: ComplaintSummaryItem | None = None


class OrderSummary(BaseModel):
    id: str
    order_number: str
    status: OrderStatus
    store_name: str
    store_slug: str
    total_lkr: Decimal
    item_count: int
    placed_at: datetime
    delivery_status: str


SmeAction = Literal["confirm", "dispatch", "in_transit", "delivered", "failed", "cancel"]


class SmeStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: SmeAction
    reason: Annotated[str, StringConstraints(max_length=500)] | None = None

    @model_validator(mode="after")
    def _reason_required(self) -> "SmeStatusUpdate":
        if self.action in ("cancel", "failed") and not self.reason:
            raise ValueError("A reason is required")
        return self


class CustomerCancel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: Annotated[str, StringConstraints(max_length=500)] | None = None
