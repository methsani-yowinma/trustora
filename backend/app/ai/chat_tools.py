"""Tools Trustora AI may call. Each one is a thin, read-only view over the existing services.

Security model:
- The caller's identity comes from the verified session (`ToolContext`), never from model
  arguments. Which tools exist at all depends on the caller's role.
- Public tools run as Postgres role `anon` (exactly what any visitor can see); personal tools run
  in the caller's own RLS-scoped transaction, through the same service functions as the API.
- Results are minimal projections: no names, addresses, phone numbers, emails, account ids,
  signed file URLs or complaint/review text are ever passed to the model.
- No tool writes data. `draft_complaint` only validates a draft that the user must confirm in
  the UI, which then calls the normal complaints endpoint.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
)

from app.ai.gemini_client import ToolSpec
from app.ai.trust_explainer import passport_facts
from app.auth.models import CurrentUser, UserRole
from app.complaints import service as complaints_service
from app.complaints.schemas import ComplaintCategory
from app.core.db import Database
from app.core.errors import AppError
from app.core.security import AuthClaims
from app.core.storage import StorageClient
from app.orders import service as orders_service
from app.products import browse
from app.trust import service as trust_service

logger = logging.getLogger("trustora.ai.chat")

AUTHENTICITY_MEANING = {
    "VERIFIED": "authenticity evidence accepted by Trustora (verified fact)",
    "PARTIALLY_VERIFIED": "some authenticity evidence accepted by Trustora",
    "UNVERIFIED": "no accepted authenticity evidence yet (not the same as fake)",
    "CONCERN": "an authenticity concern was upheld by Trustora",
}

COMPLAINT_STATUS_MEANING = {
    "SUBMITTED": "customer allegation, waiting for the seller's response (not verified)",
    "SME_RESPONDED": "seller has responded; still an unverified allegation",
    "UNDER_REVIEW": "Trustora is reviewing it; still an unverified allegation",
    "RESOLVED": "closed as resolved",
    "UPHELD": "Trustora upheld the complaint (verified finding)",
    "DISMISSED": "Trustora dismissed the complaint",
}


@dataclass
class ToolContext:
    db: Database
    storage: StorageClient
    locale: str
    user: CurrentUser | None = None
    claims: AuthClaims | None = None
    # Filled by tools so the response can link to what the answer is based on.
    sources: dict[str, dict[str, str]] = field(default_factory=dict)
    draft: dict[str, Any] | None = None

    def source(self, kind: str, ref: str, label: str) -> None:
        self.sources[f"{kind}:{ref}"] = {"kind": kind, "ref": ref, "label": label}


def _name(i18n: dict[str, str] | None, locale: str) -> str:
    if not i18n:
        return ""
    return i18n.get(locale) or i18n.get("en") or next(iter(i18n.values()), "")


# --- Arguments ------------------------------------------------------------------------------
class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


StoreSlug = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{3,40}$")]
# Upper-cased before the pattern check: models (and users) often write "tr-ab12cd34".
OrderNumber = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
    StringConstraints(pattern=r"^TR-[A-Z0-9]{8}$"),
]
Query = Annotated[str, StringConstraints(min_length=1, max_length=80)]


class NoArgs(_Args):
    pass


class StoreArgs(_Args):
    store_slug: StoreSlug = Field(description="The store's slug, e.g. from search_stores.")


class HistoryArgs(StoreArgs):
    days: int = Field(default=30, ge=1, le=365, description="Window in days (default 30).")


class SearchArgs(_Args):
    query: Query = Field(description="Words from the store or product name.")


class ProductSearchArgs(SearchArgs):
    store_slug: StoreSlug | None = Field(default=None, description="Limit to one store.")


class ProductArgs(_Args):
    product_id: str = Field(
        pattern=r"^[0-9a-fA-F-]{36}$", description="Product id, e.g. from search_products."
    )


class OrderArgs(_Args):
    order_number: OrderNumber = Field(description="Order number such as TR-AB12CD34.")


class DraftComplaintArgs(OrderArgs):
    category: ComplaintCategory
    description: Annotated[str, StringConstraints(min_length=10, max_length=2000)] = Field(
        description="The problem in the customer's own words (their language)."
    )


# --- Public tools ---------------------------------------------------------------------------
async def search_stores(ctx: ToolContext, args: SearchArgs) -> dict[str, Any]:
    async with ctx.db.anon_transaction() as conn:
        page = await browse.list_stores(
            conn, ctx.storage, q=args.query, verified_only=False, page=1, page_size=5
        )
    return {
        "stores": [
            {"store_slug": s.slug, "name": s.name, "verification_status": s.verification_status,
             "trust_level": s.trust_level, "trust_score": s.trust_score}
            for s in page.items
        ]
    }  # fmt: skip


async def get_seller_trust(ctx: ToolContext, args: StoreArgs) -> dict[str, Any]:
    async with ctx.db.anon_transaction() as conn:
        passport = await trust_service.public_passport(conn, ctx.storage, args.store_slug)
        complaints = await complaints_service.public_summary(conn, args.store_slug)
    ctx.source("STORE", passport.store.slug, passport.store.name)
    change = passport.history.change
    return {
        **passport_facts(passport),
        "store_slug": passport.store.slug,
        "verification_status": passport.store.verification_status,
        "member_since": passport.store.member_since.date().isoformat(),
        "rules_version": passport.trust.rules_version,
        "evidence": passport.evidence_summary.model_dump(),
        "change_30_days": change.model_dump() if change else None,
        "complaint_record": {
            "note": "Open complaints are customer allegations, not verified facts.",
            "open_allegations_by_category": complaints.open_allegations,
            "upheld_by_category": complaints.upheld,
            "resolved": complaints.resolved,
            "dismissed": complaints.dismissed,
        },
    }


async def get_trust_score_history(ctx: ToolContext, args: HistoryArgs) -> dict[str, Any]:
    async with ctx.db.anon_transaction() as conn:
        history = await trust_service.public_history(conn, args.store_slug, args.days)
    return history.model_dump(mode="json")


async def search_products(ctx: ToolContext, args: ProductSearchArgs) -> dict[str, Any]:
    async with ctx.db.anon_transaction() as conn:
        page = await browse.search_products(
            conn, ctx.storage, q=args.query, category_id=None, verified_only=False,
            store_slug=args.store_slug, sort="trust", page=1, page_size=5,
        )  # fmt: skip
    return {
        "products": [
            {"product_id": p.id, "name": _name(p.name_i18n, ctx.locale),
             "authenticity_status": p.authenticity_status, "in_stock": p.in_stock,
             "store_slug": p.store.slug, "store_name": p.store.name}
            for p in page.items
        ]
    }  # fmt: skip


async def get_product_trust(ctx: ToolContext, args: ProductArgs) -> dict[str, Any]:
    async with ctx.db.anon_transaction() as conn:
        product = await browse.get_product(conn, ctx.storage, args.product_id)
    name = _name(product.name_i18n, ctx.locale)
    ctx.source("PRODUCT", product.id, name)
    return {
        "product_id": product.id,
        "name": name,
        "price_lkr": str(product.price_lkr),
        "in_stock": product.in_stock,
        "authenticity_status": product.authenticity_status,
        "authenticity_meaning": AUTHENTICITY_MEANING.get(product.authenticity_status),
        "store": {
            "store_slug": product.store.slug,
            "name": product.store.name,
            "verification_status": product.store.verification_status,
            "trust_level": product.store.trust_level,
            "trust_score": product.store.trust_score,
        },
    }


# --- Customer tools -------------------------------------------------------------------------
def _require(ctx: ToolContext) -> tuple[CurrentUser, AuthClaims]:
    if ctx.user is None or ctx.claims is None:  # pragma: no cover - tools are role-gated
        raise AppError("Not signed in", code="not_signed_in")
    return ctx.user, ctx.claims


async def get_my_orders(ctx: ToolContext, args: NoArgs) -> dict[str, Any]:
    user, claims = _require(ctx)
    async with ctx.db.user_transaction(claims) as conn:
        orders = (
            await orders_service.list_customer_orders(conn, user)
            if user.role == UserRole.CUSTOMER
            else await orders_service.list_sme_orders(conn, user, None)
        )
    return {
        "orders": [
            {"order_number": o.order_number, "status": o.status, "delivery_status": o.delivery_status,
             "store_name": o.store_name, "total_lkr": str(o.total_lkr), "item_count": o.item_count,
             "placed_at": o.placed_at.date().isoformat()}
            for o in orders[:15]
        ],
        "total_orders": len(orders),
    }  # fmt: skip


async def _own_order(ctx: ToolContext, order_number: str) -> Any:
    user, claims = _require(ctx)
    async with ctx.db.user_transaction(claims) as conn:
        match = next(
            (o for o in await orders_service.list_customer_orders(conn, user)
             if o.order_number == order_number),
            None,
        )  # fmt: skip
        if match is None:
            # Not the caller's order (or it does not exist): indistinguishable on purpose.
            raise AppError("Order not found", code="not_found")
        return await orders_service.get_customer_order(conn, user, match.id)


async def get_order_status(ctx: ToolContext, args: OrderArgs) -> dict[str, Any]:
    order = await _own_order(ctx, args.order_number)
    ctx.source("ORDER", order.id, order.order_number)
    d = order.delivery
    return {
        "order_number": order.order_number,
        "status": order.status,
        "store": {"name": order.store.name, "store_slug": order.store.slug},
        "items": [{"name": _name(i.product_name_i18n, ctx.locale), "quantity": i.quantity} for i in order.items],
        "total_lkr": str(order.total_lkr),
        "payment": {"method": order.payment.method, "status": order.payment.status},
        "delivery": {
            "status": d.status, "provider": d.provider_code, "tracking_ref": d.tracking_ref,
            "estimated_delivery_date": d.estimated_delivery_date.isoformat() if d.estimated_delivery_date else None,
            "dispatched_at": d.dispatched_at.isoformat() if d.dispatched_at else None,
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None,
            "failure_reason": d.failure_reason,
        },
        "placed_at": order.placed_at.isoformat(),
        "cancelled_by": order.cancelled_by,
        "allowed_actions": order.allowed_actions,
        "complaint_status": order.complaint.status if order.complaint else None,
    }  # fmt: skip


async def get_my_complaints(ctx: ToolContext, args: NoArgs) -> dict[str, Any]:
    user, claims = _require(ctx)
    async with ctx.db.user_transaction(claims) as conn:
        items = (
            await complaints_service.list_for_customer(conn, user)
            if user.role == UserRole.CUSTOMER
            else await complaints_service.list_for_sme(conn, user, None)
        )
    return {
        "complaints": [
            {"order_number": c.order_number, "store_name": c.store_name, "category": c.category,
             "status": c.status, "status_meaning": COMPLAINT_STATUS_MEANING.get(c.status),
             "created_at": c.created_at.date().isoformat()}
            for c in items[:15]
        ],
        "total": len(items),
    }  # fmt: skip


async def draft_complaint(ctx: ToolContext, args: DraftComplaintArgs) -> dict[str, Any]:
    order = await _own_order(ctx, args.order_number)
    if "complain" not in order.allowed_actions:
        return {"drafted": False, "reason": "A complaint cannot be opened for this order now.",
                "order_status": order.status,
                "existing_complaint_status": order.complaint.status if order.complaint else None}  # fmt: skip
    ctx.draft = {
        "order_id": order.id,
        "order_number": order.order_number,
        "category": args.category.value,
        "description": args.description,
    }
    return {
        "drafted": True,
        "note": "Nothing was submitted. The customer must review and confirm the draft shown below "
        "your reply; they can also attach photos on the order page.",
    }


# --- SME tools ------------------------------------------------------------------------------
async def get_my_trust(ctx: ToolContext, args: NoArgs) -> dict[str, Any]:
    user, claims = _require(ctx)
    async with ctx.db.user_transaction(claims) as conn:
        trust = await trust_service.own_trust(conn, ctx.storage, user)
    change = trust.history.change
    return {
        **passport_facts(trust),
        "verification_status": trust.store.verification_status,
        "evidence": trust.evidence_summary.model_dump(),
        "change_30_days": change.model_dump() if change else None,
        "improvement_suggestions": [s.model_dump() for s in trust.suggestions],
    }


# --- Registry -------------------------------------------------------------------------------
Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[_Args]
    handler: Handler
    roles: frozenset[str]  # "PUBLIC" means everyone, including visitors


PUBLIC = frozenset({"PUBLIC"})
TOOLS = [
    Tool("search_stores", "Find stores on Trustora by name.", SearchArgs, search_stores, PUBLIC),
    Tool("get_seller_trust", "A store's Trust Passport: trust score and level (calculated by "
         "Trustora's rules), the signals behind it with their sources, evidence counts, 30-day "
         "change and complaint record.", StoreArgs, get_seller_trust, PUBLIC),
    Tool("get_trust_score_history", "A store's trust score history.", HistoryArgs,
         get_trust_score_history, PUBLIC),
    Tool("search_products", "Find products by name.", ProductSearchArgs, search_products, PUBLIC),
    Tool("get_product_trust", "A product's authenticity status, availability and its seller's "
         "trust.", ProductArgs, get_product_trust, PUBLIC),
    Tool("get_my_orders", "The signed-in user's own orders.", NoArgs, get_my_orders,
         frozenset({"CUSTOMER", "SME"})),
    Tool("get_order_status", "Status, payment and delivery of one of the customer's own orders.",
         OrderArgs, get_order_status, frozenset({"CUSTOMER"})),
    Tool("get_my_complaints", "The signed-in user's complaints (customer: filed; seller: "
         "received) with their status.", NoArgs, get_my_complaints, frozenset({"CUSTOMER", "SME"})),
    Tool("draft_complaint", "Prepare (not submit) a complaint about one of the customer's own "
         "orders. Only call this when the customer clearly wants to complain.", DraftComplaintArgs,
         draft_complaint, frozenset({"CUSTOMER"})),
    Tool("get_my_trust", "The seller's own trust breakdown and suggestions to improve it.",
         NoArgs, get_my_trust, frozenset({"SME"})),
]  # fmt: skip


def tools_for(user: CurrentUser | None) -> dict[str, Tool]:
    role = user.role.value if user else None
    return {t.name: t for t in TOOLS if "PUBLIC" in t.roles or role in t.roles}


def specs(tools: dict[str, Tool]) -> list[ToolSpec]:
    return [_spec(t) for t in tools.values()]


def _spec(tool: Tool) -> ToolSpec:
    schema = tool.args.model_json_schema()
    defs = schema.get("$defs", {})
    return ToolSpec(
        name=tool.name,
        description=tool.description,
        parameters={
            "type": "object",
            "properties": {k: _plain(v, defs) for k, v in schema.get("properties", {}).items()},
            "required": schema.get("required", []),
        },
    )


def _plain(prop: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """A self-contained property schema (no $ref, no nullable anyOf), as Gemini expects.

    Arguments are still validated in full by the Pydantic model before any tool runs.
    """
    if "$ref" in prop:
        prop = {
            **defs[prop["$ref"].rsplit("/", 1)[-1]],
            **{k: v for k, v in prop.items() if k != "$ref"},
        }
    if "anyOf" in prop:
        options = [o for o in prop["anyOf"] if o.get("type") != "null"]
        if len(options) == 1:
            prop = {**options[0], **{k: v for k, v in prop.items() if k != "anyOf"}}
    return {k: v for k, v in prop.items() if k not in ("title", "default")}


async def run_tool(
    ctx: ToolContext, tools: dict[str, Tool], name: str, raw_args: dict[str, Any]
) -> dict[str, Any]:
    """Runs one tool call. Errors become short codes the model can explain, never stack traces."""
    tool = tools.get(name)
    if tool is None:
        # Unknown, or not available to this role: same answer either way.
        return {"error": "tool_not_available"}
    try:
        args = tool.args.model_validate(raw_args)
    except ValidationError:
        return {"error": "invalid_arguments"}
    try:
        return await tool.handler(ctx, args)
    except AppError as exc:
        return {"error": exc.code}
    except Exception:
        logger.exception("Chat tool failed", extra={"tool": name})
        return {"error": "temporarily_unavailable"}
