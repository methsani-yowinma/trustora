"""Phase 5: browsing, cart quotes, checkout, order state machine, isolation, trust feedback."""

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_rls import as_role

API = "/api/v1"
ADDRESS = {
    "recipient_name": "Kamala Perera",
    "phone": "+94 77 555 1234",
    "address_line1": "12 Temple Road",
    "city": "Nugegoda",
    "district": "COLOMBO",
}


async def _product(client: httpx.AsyncClient, owner: Any, **overrides: Any) -> dict[str, Any]:
    payload = {
        "category_id": 1,
        "name_i18n": {"en": "Batik sarong", "si": "බතික් සරම"},
        "price_lkr": "2500.00",
        "stock": 5,
        **overrides,
    }
    response = await client.post(f"{API}/sme/products", headers=owner.headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def shop(client: httpx.AsyncClient, make_store: Any) -> Any:
    """A published store with two products."""

    async def _make(**store_fields: Any) -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
        owner, store = await make_store(published=True, **store_fields)
        products = [
            await _product(client, owner),
            await _product(
                client,
                owner,
                name_i18n={"en": "Clay pot"},
                price_lkr="1200.50",
                stock=2,
                category_id=4,
            ),
        ]
        return owner, store, products

    return _make


async def _checkout(
    client: httpx.AsyncClient, customer: Any, lines: list[tuple[str, int]], **overrides: Any
) -> httpx.Response:
    items = [{"product_id": pid, "quantity": qty} for pid, qty in lines]
    quote = (
        await client.post(f"{API}/checkout/quote", json={"items": items, "district": "COLOMBO"})
    ).json()
    body = {
        "items": items,
        "shipping_address": ADDRESS,
        "payment_method": "COD",
        "idempotency_key": str(uuid.uuid4()),
        "expected_total_lkr": quote.get("total_lkr", "1.00"),
        **overrides,
    }
    return await client.post(f"{API}/checkout", headers=customer.headers, json=body)


async def _stock(engine: AsyncEngine, product_id: str) -> int:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text("select stock from public.products where id = :id"), {"id": product_id}
            )
        ).scalar_one()


async def _sme_action(
    client: httpx.AsyncClient, owner: Any, order_id: str, action: str, reason: str | None = None
) -> httpx.Response:
    body: dict[str, Any] = {"action": action}
    if reason:
        body["reason"] = reason
    return await client.post(
        f"{API}/sme/orders/{order_id}/status", headers=owner.headers, json=body
    )


# --- Browsing -------------------------------------------------------------------------------
async def test_search_and_filters(client: httpx.AsyncClient, shop: Any, make_store: Any) -> None:
    owner, store, (sarong, pot) = await shop(name="Galle Batik House")
    draft_owner, _ = await make_store()
    await _product(client, draft_owner, name_i18n={"en": "Batik draft item"})

    by_english = (
        await client.get(f"{API}/products", params={"q": "sarong", "store": store["slug"]})
    ).json()
    assert [p["id"] for p in by_english["items"]] == [sarong["id"]]
    by_sinhala = (
        await client.get(f"{API}/products", params={"q": "සරම", "store": store["slug"]})
    ).json()
    assert by_sinhala["total"] == 1
    by_store_name = (await client.get(f"{API}/products", params={"q": "Galle Batik"})).json()
    assert {sarong["id"], pot["id"]} <= {p["id"] for p in by_store_name["items"]}
    # Products of unpublished stores never appear.
    assert all(
        p["name_i18n"].get("en") != "Batik draft item"
        for p in (await client.get(f"{API}/products", params={"q": "draft"})).json()["items"]
    )

    category = (
        await client.get(f"{API}/products", params={"category": 4, "store": store["slug"]})
    ).json()
    assert [p["id"] for p in category["items"]] == [pot["id"]]
    cheapest = (
        await client.get(f"{API}/products", params={"store": store["slug"], "sort": "price_asc"})
    ).json()
    assert [p["id"] for p in cheapest["items"]] == [pot["id"], sarong["id"]]
    card = cheapest["items"][0]
    assert card["store"]["slug"] == store["slug"] and card["store"]["trust_level"] is not None
    assert "stock" not in card

    paged = (
        await client.get(
            f"{API}/products", params={"store": store["slug"], "page_size": 1, "page": 2}
        )
    ).json()
    assert paged["total"] == 2 and len(paged["items"]) == 1


async def test_search_escapes_wildcards(client: httpx.AsyncClient, shop: Any) -> None:
    _, store, _ = await shop()
    result = (await client.get(f"{API}/products", params={"q": "%", "store": store["slug"]})).json()
    assert result["total"] == 0


async def test_verified_only_filter(client: httpx.AsyncClient, shop: Any, make_actor: Any) -> None:
    owner, store, (sarong, _) = await shop()
    admin = await make_actor("ADMIN")
    detail = (
        await client.post(
            f"{API}/sme/products/{sarong['id']}/evidence",
            headers=owner.headers,
            data={"evidence_type": "PRODUCT_DOCUMENT", "description": "Supplier invoice"},
            files={"file": ("invoice.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        )
    ).json()
    await client.post(
        f"{API}/admin/evidence/{detail['evidence'][0]['id']}/review",
        headers=admin.headers,
        json={"decision": "ACCEPTED"},
    )
    verified = (
        await client.get(f"{API}/products", params={"verified": "true", "store": store["slug"]})
    ).json()
    assert [p["id"] for p in verified["items"]] == [sarong["id"]]


async def test_product_detail_and_store_list(client: httpx.AsyncClient, shop: Any) -> None:
    owner, store, (sarong, _) = await shop()
    await client.patch(
        f"{API}/sme/products/{sarong['id']}", headers=owner.headers, json={"stock": 40}
    )
    detail = (await client.get(f"{API}/products/{sarong['id']}")).json()
    assert detail["max_quantity"] == 10  # capped; exact stock is not disclosed
    assert detail["store"]["name"] == store["name"]

    await client.patch(
        f"{API}/sme/products/{sarong['id']}", headers=owner.headers, json={"status": "HIDDEN"}
    )
    assert (await client.get(f"{API}/products/{sarong['id']}")).status_code == 404

    stores = (await client.get(f"{API}/stores", params={"q": store["name"]})).json()
    entry = next(s for s in stores["items"] if s["id"] == store["id"])
    assert entry["product_count"] == 1 and entry["trust_level"] is not None


# --- Quotes -----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("district", "fee"), [("COLOMBO", "350.00"), ("KANDY", "500.00"), ("JAFFNA", "600.00")]
)
async def test_quote_prices_and_delivery_by_district(
    client: httpx.AsyncClient, shop: Any, district: str, fee: str
) -> None:
    _, _, (sarong, pot) = await shop()
    quote = (
        await client.post(
            f"{API}/checkout/quote",
            json={
                "items": [
                    {"product_id": sarong["id"], "quantity": 2},
                    {"product_id": pot["id"], "quantity": 1},
                ],
                "district": district,
            },
        )
    ).json()
    assert quote["subtotal_lkr"] == "6200.50"
    assert quote["delivery"]["fee_lkr"] == fee
    assert (
        quote["total_lkr"] == str(6200.50 + float(fee)).replace(".5", ".50")
        if False
        else quote["total_lkr"]
    )
    assert float(quote["total_lkr"]) == pytest.approx(6200.50 + float(fee))
    assert quote["issues"] == []


async def test_quote_reports_problems(client: httpx.AsyncClient, shop: Any) -> None:
    owner, _, (sarong, pot) = await shop()
    quote = (
        await client.post(
            f"{API}/checkout/quote",
            json={
                "items": [
                    {"product_id": pot["id"], "quantity": 3},
                    {"product_id": str(uuid.uuid4()), "quantity": 1},
                ],
                "district": "GALLE",
            },
        )
    ).json()
    assert f"insufficient_stock:{pot['id']}" in quote["issues"]
    assert any(i.startswith("unavailable:") for i in quote["issues"])

    _, _, (other, _) = await shop()
    mixed = await client.post(
        f"{API}/checkout/quote",
        json={
            "items": [
                {"product_id": sarong["id"], "quantity": 1},
                {"product_id": other["id"], "quantity": 1},
            ],
            "district": "GALLE",
        },
    )
    assert mixed.status_code == 422 and mixed.json()["error"]["code"] == "multiple_stores"


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"product_id": "00000000-0000-0000-0000-000000000001", "quantity": 11}],
        [{"product_id": "00000000-0000-0000-0000-000000000001", "quantity": 1}] * 2,
    ],
)
async def test_quote_validation(client: httpx.AsyncClient, items: list[dict[str, Any]]) -> None:
    assert (
        await client.post(f"{API}/checkout/quote", json={"items": items, "district": "COLOMBO"})
    ).status_code == 422


# --- Checkout ----------------------------------------------------------------------------------
async def test_cod_checkout(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    owner, store, (sarong, pot) = await shop()
    customer = await make_actor("CUSTOMER")
    response = await _checkout(client, customer, [(sarong["id"], 2), (pot["id"], 1)])
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["order_number"].startswith("TR-") and order["status"] == "PLACED"
    assert order["store"]["slug"] == store["slug"]
    assert order["total_lkr"] == "6550.50"  # 2 × 2500 + 1200.50 + 350 delivery
    assert order["payment"] == {
        **order["payment"],
        "method": "COD",
        "status": "PENDING",
        "mock_reference": None,
    }
    assert order["delivery"]["status"] == "PENDING" and order["delivery"]["district"] == "COLOMBO"
    assert order["allowed_actions"] == ["cancel", "complain"]
    assert order["items"][0]["product_name_i18n"]["en"] in ("Batik sarong", "Clay pot")
    assert await _stock(engine, sarong["id"]) == 3 and await _stock(engine, pot["id"]) == 1

    sme_view = (await client.get(f"{API}/sme/orders/{order['id']}", headers=owner.headers)).json()
    assert sme_view["shipping_address"]["recipient_name"] == "Kamala Perera"
    assert sme_view["allowed_actions"] == ["confirm", "cancel"]


async def test_mock_card_checkout_is_paid_without_card_data(
    client: httpx.AsyncClient, shop: Any, make_actor: Any
) -> None:
    _, _, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    order = (
        await _checkout(client, customer, [(sarong["id"], 1)], payment_method="MOCK_CARD")
    ).json()
    assert order["payment"]["status"] == "PAID"
    assert order["payment"]["mock_reference"].startswith("MOCK-")
    # Card numbers are never accepted.
    rejected = await _checkout(
        client, customer, [(sarong["id"], 1)], card_number="4111111111111111"
    )
    assert rejected.status_code == 422


async def test_price_change_blocks_checkout(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    _, _, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    response = await _checkout(client, customer, [(sarong["id"], 1)], expected_total_lkr="100.00")
    assert response.status_code == 409 and response.json()["error"]["code"] == "price_changed"
    assert await _stock(engine, sarong["id"]) == 5
    assert (await client.get(f"{API}/orders", headers=customer.headers)).json() == []


async def test_client_cannot_set_prices(
    client: httpx.AsyncClient, shop: Any, make_actor: Any
) -> None:
    _, _, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    response = await _checkout(
        client,
        customer,
        [(sarong["id"], 1)],
        items=[{"product_id": sarong["id"], "quantity": 1, "unit_price_lkr": "1.00"}],
    )
    assert response.status_code == 422


async def test_checkout_is_idempotent(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    _, _, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    key = str(uuid.uuid4())
    first = await _checkout(client, customer, [(sarong["id"], 1)], idempotency_key=key)
    retry = await _checkout(client, customer, [(sarong["id"], 1)], idempotency_key=key)
    assert first.json()["id"] == retry.json()["id"]
    assert await _stock(engine, sarong["id"]) == 4
    assert len((await client.get(f"{API}/orders", headers=customer.headers)).json()) == 1


async def test_cannot_oversell(client: httpx.AsyncClient, shop: Any, make_actor: Any) -> None:
    _, _, (_, pot) = await shop()  # stock 2
    customers = [await make_actor("CUSTOMER") for _ in range(3)]
    results = await asyncio.gather(*(_checkout(client, c, [(pot["id"], 1)]) for c in customers))
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 201, 409]


@pytest.mark.parametrize("role", ["SME", "ADMIN"])
async def test_only_customers_can_checkout(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, role: str
) -> None:
    _, _, (sarong, _) = await shop()
    actor = await make_actor(role)
    assert (await _checkout(client, actor, [(sarong["id"], 1)])).status_code == 403
    assert (await client.post(f"{API}/checkout", json={})).status_code == 401


@pytest.mark.parametrize(
    "address",
    [
        {**ADDRESS, "district": "ATLANTIS"},
        {**ADDRESS, "phone": "call me"},
        {**ADDRESS, "postal_code": "ABC"},
    ],
)
async def test_address_validation(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, address: dict[str, Any]
) -> None:
    _, _, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    assert (
        await _checkout(client, customer, [(sarong["id"], 1)], shipping_address=address)
    ).status_code == 422


# --- State machine ------------------------------------------------------------------------------
async def test_full_delivery_lifecycle(
    client: httpx.AsyncClient, shop: Any, make_actor: Any
) -> None:
    owner, store, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    order = (await _checkout(client, customer, [(sarong["id"], 1)])).json()
    oid = order["id"]

    assert (
        await _sme_action(client, owner, oid, "delivered")
    ).status_code == 409  # not yet dispatched
    confirmed = (await _sme_action(client, owner, oid, "confirm")).json()
    assert confirmed["status"] == "CONFIRMED" and confirmed["allowed_actions"] == [
        "dispatch",
        "cancel",
    ]
    assert (
        await client.post(f"{API}/orders/{oid}/cancel", headers=customer.headers)
    ).status_code == 409

    dispatched = (await _sme_action(client, owner, oid, "dispatch")).json()
    assert dispatched["delivery"]["tracking_ref"].startswith("SIM-")
    assert dispatched["delivery"]["estimated_delivery_date"] is not None
    assert dispatched["allowed_actions"] == ["in_transit", "delivered", "failed"]

    in_transit = (await _sme_action(client, owner, oid, "in_transit")).json()
    assert (
        in_transit["delivery"]["status"] == "IN_TRANSIT"
        and "in_transit" not in in_transit["allowed_actions"]
    )

    delivered = (await _sme_action(client, owner, oid, "delivered")).json()
    assert (
        delivered["status"] == "DELIVERED" and delivered["payment"]["status"] == "PAID"
    )  # COD collected

    customer_view = (await client.get(f"{API}/orders/{oid}", headers=customer.headers)).json()
    assert customer_view["allowed_actions"] == ["confirm_receipt", "review", "complain"]
    completed = (
        await client.post(f"{API}/orders/{oid}/confirm-receipt", headers=customer.headers)
    ).json()
    assert completed["status"] == "COMPLETED" and completed["allowed_actions"] == [
        "review",
        "complain",
    ]

    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    assert "COMPLETED_ORDERS" in {s["code"] for s in passport["positive_signals"]}
    assert passport["trust"]["transaction_score"] > 50


async def test_customer_cancel_restocks_and_refunds(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    _, _, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    order = (
        await _checkout(client, customer, [(sarong["id"], 2)], payment_method="MOCK_CARD")
    ).json()
    cancelled = (
        await client.post(
            f"{API}/orders/{order['id']}/cancel",
            headers=customer.headers,
            json={"reason": "Changed my mind"},
        )
    ).json()
    assert cancelled["status"] == "CANCELLED" and cancelled["cancelled_by"] == "CUSTOMER"
    assert cancelled["payment"]["status"] == "REFUNDED"
    assert await _stock(engine, sarong["id"]) == 5


async def test_seller_cancellation_and_failed_delivery_lower_trust(
    client: httpx.AsyncClient, shop: Any, make_actor: Any
) -> None:
    owner, store, (sarong, pot) = await shop()
    customer = await make_actor("CUSTOMER")
    first = (await _checkout(client, customer, [(sarong["id"], 1)])).json()
    assert (
        await _sme_action(client, owner, first["id"], "cancel")
    ).status_code == 422  # reason required
    cancelled = (
        await _sme_action(client, owner, first["id"], "cancel", "Out of stock at warehouse")
    ).json()
    assert cancelled["cancelled_by"] == "SME"

    second = (
        await _checkout(client, customer, [(pot["id"], 1)], payment_method="MOCK_CARD")
    ).json()
    for action in ("confirm", "dispatch"):
        await _sme_action(client, owner, second["id"], action)
    failed = (await _sme_action(client, owner, second["id"], "failed", "Address not found")).json()
    assert failed["status"] == "DELIVERY_FAILED" and failed["payment"]["status"] == "REFUNDED"
    assert failed["delivery"]["failure_reason"] == "Address not found"

    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    risks = {s["code"] for s in passport["risk_signals"]}
    # Visible even before the first completed order.
    assert {"SELLER_CANCELLATIONS", "DELIVERY_FAILURES"} <= risks
    assert passport["trust"]["transaction_score"] < 50


async def test_late_delivery_is_detected(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    owner, store, (sarong, _) = await shop()
    customer = await make_actor("CUSTOMER")
    order = (await _checkout(client, customer, [(sarong["id"], 1)])).json()
    for action in ("confirm", "dispatch"):
        await _sme_action(client, owner, order["id"], action)
    async with engine.begin() as conn:  # pretend the promised date has passed
        await conn.execute(
            text(
                "update public.deliveries set estimated_delivery_date = current_date - 3 where order_id = :id"
            ),
            {"id": order["id"]},
        )
    await _sme_action(client, owner, order["id"], "delivered")
    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    assert "LATE_DELIVERIES" in {s["code"] for s in passport["risk_signals"]}


# --- Isolation ------------------------------------------------------------------------------------
async def test_order_isolation(client: httpx.AsyncClient, shop: Any, make_actor: Any) -> None:
    owner_a, _, (product_a, _) = await shop()
    owner_b, _, _ = await shop()
    alice, bob = await make_actor("CUSTOMER"), await make_actor("CUSTOMER")
    order = (await _checkout(client, alice, [(product_a["id"], 1)])).json()

    # Customer A cannot see Customer B's order, and vice versa.
    assert (await client.get(f"{API}/orders/{order['id']}", headers=bob.headers)).status_code == 404
    assert (
        await client.post(f"{API}/orders/{order['id']}/cancel", headers=bob.headers)
    ).status_code == 404
    assert (await client.get(f"{API}/orders", headers=bob.headers)).json() == []
    # SME B cannot see or change SME A's orders.
    assert (
        await client.get(f"{API}/sme/orders/{order['id']}", headers=owner_b.headers)
    ).status_code == 404
    assert (await _sme_action(client, owner_b, order["id"], "confirm")).status_code == 404
    assert (await client.get(f"{API}/sme/orders", headers=owner_b.headers)).json() == []
    assert len((await client.get(f"{API}/sme/orders", headers=owner_a.headers)).json()) == 1


async def test_order_tables_rls(
    client: httpx.AsyncClient, shop: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    _, _, (product, _) = await shop()
    alice, bob = await make_actor("CUSTOMER"), await make_actor("CUSTOMER")
    order = (await _checkout(client, alice, [(product["id"], 1)])).json()
    for table in ("orders", "order_items", "payments", "deliveries"):
        column = "id" if table == "orders" else "order_id"
        async with as_role(engine, "authenticated", bob.id) as conn:
            count = await conn.execute(
                text(f"select count(*) from public.{table} where {column} = :id"),  # noqa: S608
                {"id": order["id"]},
            )
            assert count.scalar_one() == 0
        async with as_role(engine, "authenticated", alice.id) as conn:
            count = await conn.execute(
                text(f"select count(*) from public.{table} where {column} = :id"),  # noqa: S608
                {"id": order["id"]},
            )
            assert count.scalar_one() == 1
    for statement in (
        "update public.orders set status = 'COMPLETED' where id = :id",
        "update public.payments set status = 'PAID' where order_id = :id",
        "delete from public.orders where id = :id",
    ):
        async with as_role(engine, "authenticated", alice.id) as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(statement), {"id": order["id"]})
