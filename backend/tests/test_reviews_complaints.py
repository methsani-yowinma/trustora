"""Phase 6: verified reviews, complaints (allegation → response → decision), fact vs allegation."""

import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import JPEG_BYTES, PDF_BYTES
from tests.test_rls import as_role

API = "/api/v1"
ADDRESS = {
    "recipient_name": "Nimali",
    "phone": "+94 71 222 3333",
    "address_line1": "5 Lake Rd",
    "city": "Kandy",
    "district": "KANDY",
}


async def _order(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, *, delivered: bool
) -> dict[str, Any]:
    owner, store = await make_store(published=True)
    product = (
        await client.post(
            f"{API}/sme/products",
            headers=owner.headers,
            json={
                "category_id": 2,
                "name_i18n": {"en": "Herbal face cream"},
                "price_lkr": "1800.00",
                "stock": 10,
            },
        )
    ).json()
    customer = await make_actor("CUSTOMER")
    items = [{"product_id": product["id"], "quantity": 1}]
    quote = (
        await client.post(f"{API}/checkout/quote", json={"items": items, "district": "KANDY"})
    ).json()
    order = (
        await client.post(
            f"{API}/checkout", headers=customer.headers,
            json={"items": items, "shipping_address": ADDRESS, "payment_method": "COD",
                  "idempotency_key": str(uuid.uuid4()), "expected_total_lkr": quote["total_lkr"]},
        )
    ).json()  # fmt: skip
    if delivered:
        for action in ("confirm", "dispatch", "delivered"):
            response = await client.post(
                f"{API}/sme/orders/{order['id']}/status",
                headers=owner.headers,
                json={"action": action},
            )
            assert response.status_code == 200, response.text
    return {
        "owner": owner,
        "store": store,
        "customer": customer,
        "order": order,
        "product": product,
    }


async def _complain(
    client: httpx.AsyncClient,
    ctx: dict[str, Any],
    category: str = "DELIVERY",
    files: list[Any] | None = None,
) -> httpx.Response:
    return await client.post(
        f"{API}/orders/{ctx['order']['id']}/complaints",
        headers=ctx["customer"].headers,
        data={
            "category": category,
            "description": "The parcel arrived damaged and the cream had leaked.",
        },
        files=files or [],
    )


async def _passport(client: httpx.AsyncClient, ctx: dict[str, Any]) -> dict[str, Any]:
    return (await client.get(f"{API}/stores/{ctx['store']['slug']}/passport")).json()


# --- Reviews ----------------------------------------------------------------------------------
async def test_review_requires_delivered_order(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=False)
    response = await client.post(
        f"{API}/orders/{ctx['order']['id']}/review",
        headers=ctx["customer"].headers,
        json={"rating": 5},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "review_not_allowed"


async def test_verified_review_flow(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    order_view = (
        await client.get(f"{API}/orders/{ctx['order']['id']}", headers=ctx["customer"].headers)
    ).json()
    assert "review" in order_view["allowed_actions"]

    review = await client.post(
        f"{API}/orders/{ctx['order']['id']}/review",
        headers=ctx["customer"].headers,
        json={"rating": 4, "comment": "  Good quality, fast delivery  "},
    )
    assert review.status_code == 201 and review.json()["comment"] == "Good quality, fast delivery"
    again = await client.post(
        f"{API}/orders/{ctx['order']['id']}/review",
        headers=ctx["customer"].headers,
        json={"rating": 1},
    )
    assert again.status_code == 409

    response = await client.post(
        f"{API}/sme/reviews/{review.json()['id']}/response",
        headers=ctx["owner"].headers,
        json={"response": "Thank you!"},
    )
    assert response.status_code == 200 and response.json()["sme_response"] == "Thank you!"
    assert (
        await client.post(
            f"{API}/sme/reviews/{review.json()['id']}/response",
            headers=ctx["owner"].headers,
            json={"response": "Again"},
        )
    ).status_code == 404

    public = (await client.get(f"{API}/stores/{ctx['store']['slug']}/reviews")).json()
    assert public["count"] == 1 and public["average"] == 4.0 and public["distribution"]["4"] == 1
    assert "customer_id" not in public["items"][0] and "order_number" not in public["items"][0]


@pytest.mark.parametrize(
    "payload",
    [
        {"rating": 0},
        {"rating": 6},
        {"rating": 3, "comment": "x" * 1001},
        {"rating": 5, "author": "me"},
    ],
)
async def test_review_validation(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, payload: dict[str, Any]
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    assert (
        await client.post(
            f"{API}/orders/{ctx['order']['id']}/review",
            headers=ctx["customer"].headers,
            json=payload,
        )
    ).status_code == 422


async def test_only_the_buyer_can_review(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    stranger = await make_actor("CUSTOMER")
    response = await client.post(
        f"{API}/orders/{ctx['order']['id']}/review", headers=stranger.headers, json={"rating": 1}
    )
    assert response.status_code == 404


async def test_reviews_feed_transaction_trust(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    await client.post(
        f"{API}/orders/{ctx['order']['id']}/review",
        headers=ctx["customer"].headers,
        json={"rating": 5},
    )
    async with engine.connect() as conn:
        sme_id = ctx["store"]["id"]
        n = (
            await conn.execute(
                text("select count(*) from public.reviews where sme_id = :id"), {"id": sme_id}
            )
        ).scalar_one()
    assert n == 1  # a rating signal appears once there are at least 3 verified reviews (rule tests)


# --- Complaints: allegation → response → resolution ---------------------------------------------
async def test_complaint_is_an_allegation_until_decided(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    before = await _passport(client, ctx)

    created = await _complain(
        client, ctx, files=[("files", ("photo.jpg", JPEG_BYTES, "image/jpeg"))]
    )
    assert created.status_code == 201, created.text
    complaint = created.json()
    assert complaint["status"] == "SUBMITTED"
    assert complaint["evidence"][0]["provenance"] == "CUSTOMER_ALLEGATION"
    assert set(complaint["allowed_actions"]) == {"add_evidence", "resolve", "escalate"}

    after = await _passport(client, ctx)
    open_signal = next(s for s in after["info_signals"] if s["code"] == "OPEN_COMPLAINTS")
    assert open_signal["provenance"] == "CUSTOMER_ALLEGATION" and open_signal["points"] == 0
    # An allegation alone never changes the score.
    assert after["trust"]["overall_score"] == before["trust"]["overall_score"]

    summary = (await client.get(f"{API}/stores/{ctx['store']['slug']}/complaints/summary")).json()
    assert summary["open_allegations"] == {"DELIVERY": 1} and summary["upheld"] == {}
    assert "description" not in str(summary)

    # Second open complaint on the same order is refused.
    assert (await _complain(client, ctx)).status_code == 409


async def test_seller_responds_and_customer_resolves(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    complaint = (await _complain(client, ctx)).json()
    cid = complaint["id"]

    sme_view = (
        await client.get(f"{API}/sme/complaints/{cid}", headers=ctx["owner"].headers)
    ).json()
    assert (
        sme_view["description"].startswith("The parcel")
        and "respond" in sme_view["allowed_actions"]
    )
    responded = await client.post(
        f"{API}/sme/complaints/{cid}/response",
        headers=ctx["owner"].headers,
        json={"response": "Sorry — we will send a replacement today."},
    )
    assert responded.json()["status"] == "SME_RESPONDED"
    proof = await client.post(
        f"{API}/sme/complaints/{cid}/evidence",
        headers=ctx["owner"].headers,
        files=[("files", ("courier-receipt.pdf", PDF_BYTES, "application/pdf"))],
    )
    assert any(e["provenance"] == "SELLER_CLAIM" for e in proof.json()["evidence"])

    customer_view = (
        await client.get(f"{API}/complaints/{cid}", headers=ctx["customer"].headers)
    ).json()
    assert customer_view["sme_response"].startswith("Sorry")
    assert len(customer_view["evidence"]) == 1  # the seller's evidence is visible to the customer
    resolved = (
        await client.post(f"{API}/complaints/{cid}/resolve", headers=ctx["customer"].headers)
    ).json()
    assert resolved["status"] == "RESOLVED" and resolved["allowed_actions"] == []

    summary = (await client.get(f"{API}/stores/{ctx['store']['slug']}/complaints/summary")).json()
    assert summary["resolved"] == 1 and summary["open_allegations"] == {}


async def test_escalation_and_upheld_decision(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    admin = await make_actor("ADMIN")
    cid = (await _complain(client, ctx, category="PRODUCT_AUTHENTICITY")).json()["id"]
    before = await _passport(client, ctx)

    escalated = (
        await client.post(f"{API}/complaints/{cid}/escalate", headers=ctx["customer"].headers)
    ).json()
    assert escalated["status"] == "UNDER_REVIEW" and escalated["allowed_actions"] == [
        "add_evidence"
    ]
    queue = (await client.get(f"{API}/admin/complaints", headers=admin.headers)).json()
    assert cid in [c["id"] for c in queue]

    assert (
        await client.post(
            f"{API}/admin/complaints/{cid}/decision",
            headers=admin.headers,
            json={"decision": "UPHELD"},
        )
    ).status_code == 422
    decided = await client.post(
        f"{API}/admin/complaints/{cid}/decision",
        headers=admin.headers,
        json={"decision": "UPHELD", "note": "Batch number does not exist with the manufacturer."},
    )
    assert decided.status_code == 200 and decided.json()["status"] == "UPHELD"
    again = await client.post(
        f"{API}/admin/complaints/{cid}/decision",
        headers=admin.headers,
        json={"decision": "DISMISSED", "note": "x"},
    )
    assert again.status_code == 409

    after = await _passport(client, ctx)
    upheld = next(s for s in after["risk_signals"] if s["code"] == "UPHELD_COMPLAINTS")
    assert upheld["provenance"] == "VERIFIED_FACT" and upheld["points"] < 0
    assert after["trust"]["transaction_score"] < before["trust"]["transaction_score"]
    # An upheld authenticity complaint marks the product as an authenticity concern.
    product = (
        await client.get(f"{API}/sme/products/{ctx['product']['id']}", headers=ctx["owner"].headers)
    ).json()
    assert product["authenticity_status"] == "CONCERN"
    summary = (await client.get(f"{API}/stores/{ctx['store']['slug']}/complaints/summary")).json()
    assert summary["upheld"] == {"PRODUCT_AUTHENTICITY": 1}

    async with engine.connect() as conn:
        actions = (await conn.execute(
            text("select action from public.audit_logs where target_id = :id order by id"), {"id": cid}
        )).scalars().all()  # fmt: skip
    assert actions == ["complaint.created", "complaint.escalated", "complaint.upheld"]


async def test_dismissed_complaint_has_no_trust_penalty(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    admin = await make_actor("ADMIN")
    before = await _passport(client, ctx)
    cid = (await _complain(client, ctx)).json()["id"]
    await client.post(f"{API}/admin/complaints/{cid}/decision", headers=admin.headers,
                      json={"decision": "DISMISSED", "note": "Courier records show an intact delivery."})  # fmt: skip
    after = await _passport(client, ctx)
    assert after["trust"]["overall_score"] == before["trust"]["overall_score"]
    assert "UPHELD_COMPLAINTS" not in {s["code"] for s in after["risk_signals"]}


async def test_unanswered_complaints_become_a_risk_after_14_days(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    cid = (await _complain(client, ctx)).json()["id"]
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "update public.complaints set created_at = now() - interval '15 days' where id = :id"
            ),
            {"id": cid},
        )
        # Make the passport stale so it refreshes on the next view (time-based input).
        await conn.execute(
            text(
                "update public.trust_scores set computed_at = now() - interval '2 hours' where sme_id = :id"
            ),
            {"id": ctx["store"]["id"]},
        )
    passport = await _passport(client, ctx)
    assert "UNRESOLVED_COMPLAINTS" in {s["code"] for s in passport["risk_signals"]}
    suggestions = (await client.get(f"{API}/sme/trust", headers=ctx["owner"].headers)).json()[
        "suggestions"
    ]
    assert "RESPOND_TO_COMPLAINTS" in {s["code"] for s in suggestions}


@pytest.mark.parametrize(
    ("data", "files"),
    [
        ({"category": "DELIVERY", "description": "too short"}, []),
        ({"category": "SCAM", "description": "This is a long enough description."}, []),
        (
            {"category": "DELIVERY", "description": "This is a long enough description."},
            [("files", (f"f{i}.pdf", PDF_BYTES, "application/pdf")) for i in range(4)],
        ),
    ],
)
async def test_complaint_validation(
    client: httpx.AsyncClient,
    make_store: Any,
    make_actor: Any,
    data: dict[str, str],
    files: list[Any],
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=False)
    response = await client.post(
        f"{API}/orders/{ctx['order']['id']}/complaints",
        headers=ctx["customer"].headers,
        data=data,
        files=files,
    )
    assert response.status_code == 422


# --- Isolation & database protection -------------------------------------------------------------
async def test_complaint_isolation(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=False)
    cid = (
        await _complain(client, ctx, files=[("files", ("p.jpg", JPEG_BYTES, "image/jpeg"))])
    ).json()["id"]
    stranger = await make_actor("CUSTOMER")
    other_sme, _ = await make_store()

    assert (
        await client.get(f"{API}/complaints/{cid}", headers=stranger.headers)
    ).status_code == 404
    assert (
        await client.post(f"{API}/complaints/{cid}/escalate", headers=stranger.headers)
    ).status_code == 404
    assert (
        await client.get(f"{API}/sme/complaints/{cid}", headers=other_sme.headers)
    ).status_code == 404
    assert (
        await client.post(
            f"{API}/sme/complaints/{cid}/response",
            headers=other_sme.headers,
            json={"response": "hi"},
        )
    ).status_code == 404
    assert (
        await client.get(f"{API}/admin/complaints/{cid}", headers=ctx["owner"].headers)
    ).status_code == 403

    async with as_role(engine, "authenticated", stranger.id) as conn:
        assert (
            await conn.execute(
                text("select count(*) from public.complaints where id = :id"), {"id": cid}
            )
        ).scalar_one() == 0
        assert (
            await conn.execute(
                text("select count(*) from public.evidence where complaint_id = :id"), {"id": cid}
            )
        ).scalar_one() == 0
    async with as_role(engine, "authenticated", ctx["customer"].id) as conn:
        assert (
            await conn.execute(
                text("select count(*) from public.evidence where complaint_id = :id"), {"id": cid}
            )
        ).scalar_one() == 1
    async with as_role(engine, "anon") as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("select * from public.complaints"))
    for statement in (
        "update public.complaints set status = 'DISMISSED' where id = :id",
        "delete from public.complaints where id = :id",
    ):
        async with as_role(engine, "authenticated", ctx["owner"].id) as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text(statement), {"id": cid})


async def test_reviewer_identity_is_not_public(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    ctx = await _order(client, make_store, make_actor, delivered=True)
    await client.post(
        f"{API}/orders/{ctx['order']['id']}/review",
        headers=ctx["customer"].headers,
        json={"rating": 5},
    )
    async with as_role(engine, "anon") as conn:
        assert (
            await conn.execute(
                text("select count(*) from public.reviews where sme_id = :id"),
                {"id": ctx["store"]["id"]},
            )
        ).scalar_one() == 1
    async with as_role(engine, "anon") as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("select customer_id from public.reviews"))
