"""Trust engine end to end: events → recalculation → passport, history, audit, RLS."""

from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import JPEG_BYTES, PDF_BYTES
from tests.test_rls import as_role

API = "/api/v1"


async def _history_triggers(engine: AsyncEngine, sme_id: str) -> list[str]:
    async with engine.connect() as conn:
        return list(
            (
                await conn.execute(
                    text(
                        "select trigger from public.trust_score_history where sme_id = :id order by id"
                    ),
                    {"id": sme_id},
                )
            ).scalars()
        )


async def _verify(
    client: httpx.AsyncClient, owner: Any, admin: Any, **decision: Any
) -> dict[str, Any]:
    submitted = await client.post(
        f"{API}/smes/me/verification",
        headers=owner.headers,
        data={"business_reg_number": "PV 1234", "registered_name": "Lanka Crafts (Pvt) Ltd"},
        files=[("documents", ("br.pdf", PDF_BYTES, "application/pdf"))],
    )
    assert submitted.status_code == 201, submitted.text
    response = await client.post(
        f"{API}/admin/verifications/{submitted.json()['id']}/decision",
        headers=admin.headers,
        json={"decision": "APPROVED", **decision},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _product_with_evidence(
    client: httpx.AsyncClient, owner: Any, evidence_type: str = "PRODUCT_DOCUMENT"
) -> tuple[str, str]:
    product = (
        await client.post(
            f"{API}/sme/products",
            headers=owner.headers,
            json={
                "category_id": 2,
                "name_i18n": {"en": "Face serum"},
                "price_lkr": "4500.00",
                "stock": 10,
            },
        )
    ).json()
    filename, data, mime = (
        ("invoice.pdf", PDF_BYTES, "application/pdf")
        if evidence_type == "PRODUCT_DOCUMENT"
        else ("label.jpg", JPEG_BYTES, "image/jpeg")
    )
    detail = (
        await client.post(
            f"{API}/sme/products/{product['id']}/evidence",
            headers=owner.headers,
            data={"evidence_type": evidence_type, "description": "Distributor invoice"},
            files={"file": (filename, data, mime)},
        )
    ).json()
    return product["id"], detail["evidence"][0]["id"]


# --- Lifecycle -----------------------------------------------------------------------------
async def test_registration_creates_initial_score_history_and_audit(
    client: httpx.AsyncClient, make_store: Any, engine: AsyncEngine
) -> None:
    _, store = await make_store()
    assert await _history_triggers(engine, store["id"]) == ["sme.registered"]
    async with engine.connect() as conn:
        audit = (
            await conn.execute(
                text(
                    "select metadata from public.audit_logs where action = 'trust.score_changed' and target_id = :id"
                ),
                {"id": store["id"]},
            )
        ).scalar_one()
    assert audit["from"] is None and audit["to"]["level"] == "CAUTION"


async def test_verification_raises_business_trust(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    owner, store = await make_store(published=True, contact_phone="+94 77 000 0000")
    admin = await make_actor("ADMIN")
    before = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()

    await _verify(client, owner, admin, contact_verified=True)
    after = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()

    assert after["trust"]["business_score"] == before["trust"]["business_score"] + 40 + 15
    verified = next(s for s in after["positive_signals"] if s["code"] == "BUSINESS_VERIFIED")
    assert verified["provenance"] == "VERIFIED_FACT" and verified["evidence_count"] == 1
    assert "CONTACT_CONFIRMED" in {s["code"] for s in after["positive_signals"]}
    assert "evidence_ids" not in verified  # evidence identifiers are never public
    assert after["store"]["verification_status"] == "VERIFIED"
    assert after["evidence_summary"]["by_provenance"]["VERIFIED_FACT"] == 1
    assert "verification.approved" in await _history_triggers(engine, store["id"])

    change = after["history"]["change"]
    assert change["to_score"] == after["trust"]["overall_score"]
    assert change["from_score"] < change["to_score"]


async def test_recalculation_without_changes_adds_no_history(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    _, store = await make_store()
    admin = await make_actor("ADMIN")
    for _ in range(2):
        response = await client.post(
            f"{API}/admin/smes/{store['id']}/trust/recalculate", headers=admin.headers
        )
        assert response.status_code == 200
    assert await _history_triggers(engine, store["id"]) == ["sme.registered"]


async def test_store_edits_update_trust(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, store = await make_store(published=True)
    response = await client.patch(
        f"{API}/smes/me",
        headers=owner.headers,
        json={"policies_i18n": {"returns": {"en": "7 days"}, "refunds": {"en": "Full refund"}}},
    )
    assert response.status_code == 200
    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    policies = next(s for s in passport["positive_signals"] if s["code"] == "POLICIES_PUBLISHED")
    assert policies["provenance"] == "SELLER_CLAIM"
    assert policies["params"]["policies"] == ["refunds", "returns"]
    assert "NO_POLICIES" not in {s["code"] for s in passport["risk_signals"]}


# --- Product evidence review → authenticity ---------------------------------------------------
async def test_accepted_document_verifies_product_authenticity(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    owner, store = await make_store(published=True)
    admin = await make_actor("ADMIN")
    product_id, evidence_id = await _product_with_evidence(client, owner)

    queue = (await client.get(f"{API}/admin/evidence", headers=admin.headers)).json()
    item = next(i for i in queue if i["id"] == evidence_id)
    assert item["product_name_i18n"] == {"en": "Face serum"}
    assert item["download_url"].startswith("https://storage.test/sign/")

    response = await client.post(
        f"{API}/admin/evidence/{evidence_id}/review",
        headers=admin.headers,
        json={"decision": "ACCEPTED"},
    )
    assert response.status_code == 200, response.text

    products = (await client.get(f"{API}/stores/{store['slug']}/products")).json()
    assert next(p for p in products if p["id"] == product_id)["authenticity_status"] == "VERIFIED"
    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    assert passport["trust"]["product_score"] == 100
    async with engine.connect() as conn:
        actions = (
            (
                await conn.execute(
                    text(
                        "select action from public.audit_logs where target_id in (:p, :e) order by id"
                    ),
                    {"p": product_id, "e": evidence_id},
                )
            )
            .scalars()
            .all()
        )
    assert "evidence.reviewed" in actions and "product.authenticity_changed" in actions


async def test_accepted_photo_is_partial_verification(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, _ = await make_store()
    admin = await make_actor("ADMIN")
    product_id, evidence_id = await _product_with_evidence(client, owner, "PRODUCT_IMAGE")
    await client.post(
        f"{API}/admin/evidence/{evidence_id}/review",
        headers=admin.headers,
        json={"decision": "ACCEPTED"},
    )
    product = (await client.get(f"{API}/sme/products/{product_id}", headers=owner.headers)).json()
    assert product["authenticity_status"] == "PARTIALLY_VERIFIED"


async def test_misleading_evidence_creates_concern_and_caps_level(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, store = await make_store(published=True)
    admin = await make_actor("ADMIN")
    await _verify(client, owner, admin, contact_verified=True)
    product_id, evidence_id = await _product_with_evidence(client, owner)

    response = await client.post(
        f"{API}/admin/evidence/{evidence_id}/review",
        headers=admin.headers,
        json={
            "decision": "REJECTED",
            "misleading": True,
            "note": "Invoice does not match the distributor's records",
        },
    )
    assert response.status_code == 200
    assert response.json()["flagged_misleading"] is True

    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    risk_codes = {s["code"] for s in passport["risk_signals"]}
    assert {"MISLEADING_EVIDENCE", "PRODUCT_AUTHENTICITY_CONCERN"} <= risk_codes
    assert passport["trust"]["level"] in ("CAUTION", "HIGH_RISK")
    product = (await client.get(f"{API}/sme/products/{product_id}", headers=owner.headers)).json()
    assert product["authenticity_status"] == "CONCERN"


async def test_rejected_but_not_misleading_evidence_has_no_penalty(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, store = await make_store(published=True)
    admin = await make_actor("ADMIN")
    product_id, evidence_id = await _product_with_evidence(client, owner)
    await client.post(
        f"{API}/admin/evidence/{evidence_id}/review",
        headers=admin.headers,
        json={"decision": "REJECTED", "note": "Image is too blurry to read"},
    )
    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    assert "MISLEADING_EVIDENCE" not in {s["code"] for s in passport["risk_signals"]}
    product = (await client.get(f"{API}/sme/products/{product_id}", headers=owner.headers)).json()
    assert product["authenticity_status"] == "UNVERIFIED"


async def test_forged_verification_documents_are_a_risk_finding(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, store = await make_store(published=True)
    admin = await make_actor("ADMIN")
    submitted = await client.post(
        f"{API}/smes/me/verification",
        headers=owner.headers,
        data={"business_reg_number": "PV 1", "registered_name": "Name"},
        files=[("documents", ("br.pdf", PDF_BYTES, "application/pdf"))],
    )
    await client.post(
        f"{API}/admin/verifications/{submitted.json()['id']}/decision",
        headers=admin.headers,
        json={
            "decision": "REJECTED",
            "note": "Registration number belongs to another company",
            "documents_misleading": True,
        },
    )
    passport = (await client.get(f"{API}/stores/{store['slug']}/passport")).json()
    assert {"MISLEADING_EVIDENCE", "VERIFICATION_NOT_APPROVED"} <= {
        s["code"] for s in passport["risk_signals"]
    }
    # A forged registration with no other positive evidence is a verified negative finding.
    assert passport["trust"]["level"] == "HIGH_RISK"


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "REJECTED"},  # note required
        {"decision": "ACCEPTED", "misleading": True},
        {"decision": "MAYBE"},
    ],
)
async def test_evidence_review_validation(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, payload: dict[str, Any]
) -> None:
    owner, _ = await make_store()
    admin = await make_actor("ADMIN")
    _, evidence_id = await _product_with_evidence(client, owner)
    response = await client.post(
        f"{API}/admin/evidence/{evidence_id}/review", headers=admin.headers, json=payload
    )
    assert response.status_code == 422


async def test_evidence_review_is_admin_only_and_once(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, _ = await make_store()
    admin = await make_actor("ADMIN")
    _, evidence_id = await _product_with_evidence(client, owner)
    url = f"{API}/admin/evidence/{evidence_id}/review"
    assert (
        await client.post(url, headers=owner.headers, json={"decision": "ACCEPTED"})
    ).status_code == 403
    assert (await client.get(f"{API}/admin/evidence", headers=owner.headers)).status_code == 403
    assert (
        await client.post(url, headers=admin.headers, json={"decision": "ACCEPTED"})
    ).status_code == 200
    assert (
        await client.post(url, headers=admin.headers, json={"decision": "ACCEPTED"})
    ).status_code == 409


# --- Passport visibility, SME view, history -------------------------------------------------
async def test_passport_is_public_only_for_published_stores(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, store = await make_store()
    assert (await client.get(f"{API}/stores/{store['slug']}/passport")).status_code == 404
    assert (await client.get(f"{API}/stores/{store['slug']}/trust/history")).status_code == 404
    # The owner still sees their own passport.
    own = await client.get(f"{API}/sme/trust", headers=owner.headers)
    assert own.status_code == 200
    assert own.json()["trust"]["level"] == "CAUTION"


async def test_sme_trust_suggestions_follow_progress(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, _ = await make_store()
    first = {
        s["code"]
        for s in (await client.get(f"{API}/sme/trust", headers=owner.headers)).json()["suggestions"]
    }
    assert {"GET_VERIFIED", "PUBLISH_POLICIES", "ADD_PRODUCTS"} <= first

    await client.patch(
        f"{API}/smes/me",
        headers=owner.headers,
        json={
            "policies_i18n": {k: {"en": "Policy text"} for k in ("returns", "refunds", "delivery")}
        },
    )
    after = {
        s["code"]
        for s in (await client.get(f"{API}/sme/trust", headers=owner.headers)).json()["suggestions"]
    }
    assert "PUBLISH_POLICIES" not in after


async def test_history_endpoint_reports_change(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, store = await make_store(published=True)
    admin = await make_actor("ADMIN")
    await _verify(client, owner, admin)
    history = (await client.get(f"{API}/stores/{store['slug']}/trust/history?days=30")).json()
    assert len(history["points"]) >= 2
    assert history["change"]["from_level"] == "CAUTION"
    assert history["change"]["to_score"] > history["change"]["from_score"]
    assert (
        await client.get(f"{API}/stores/{store['slug']}/trust/history?days=0")
    ).status_code == 422


# --- Database-level protection --------------------------------------------------------------
@pytest.mark.parametrize(
    "statement",
    [
        "update public.trust_scores set overall_score = 100, level = 'VERIFIED' where sme_id = :id",
        "delete from public.trust_signals where sme_id = :id",
        "insert into public.trust_score_history (sme_id, overall_score, level, business_score, product_score, transaction_score, rules_version, trigger) values (:id, 100, 'VERIFIED', 100, 100, 100, 'x', 'fake')",
    ],
)
async def test_sme_cannot_write_trust_tables(
    engine: AsyncEngine, make_store: Any, statement: str
) -> None:
    owner, store = await make_store()
    async with as_role(engine, "authenticated", owner.id) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text(statement), {"id": store["id"]})


async def test_trust_history_is_append_only(engine: AsyncEngine, make_store: Any) -> None:
    _, store = await make_store()
    for statement in (
        "update public.trust_score_history set overall_score = 100 where sme_id = :id",
        "delete from public.trust_score_history where sme_id = :id",
    ):
        async with engine.begin() as conn:
            with pytest.raises(DBAPIError, match="append-only"):
                await conn.execute(text(statement), {"id": store["id"]})


async def test_anon_reads_trust_only_for_public_stores(
    engine: AsyncEngine, make_store: Any
) -> None:
    _, public = await make_store(published=True)
    _, draft = await make_store()
    async with as_role(engine, "anon") as conn:
        visible = set(
            str(r)
            for r in (await conn.execute(text("select sme_id from public.trust_scores"))).scalars()
        )
    assert public["id"] in visible and draft["id"] not in visible


async def test_concurrent_recalculations_record_history_once(
    engine: AsyncEngine, database: Any, make_store: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from app.trust import trust_engine

    _, store = await make_store()
    async with engine.begin() as conn:  # simulate a store whose score was never computed
        await conn.execute(
            text("delete from public.trust_scores where sme_id = :id"), {"id": store["id"]}
        )

    # Line all three up after they have read the (missing) previous score, so unserialized
    # recalculations would all record the change. With the per-SME lock, only one can be
    # past the lock at a time: the barrier never fills, times out, and they proceed in turn.
    original = trust_engine.collect_inputs
    barrier = asyncio.Barrier(3)

    async def synchronized_collect(conn: Any, sme_id: str) -> Any:
        collected = await original(conn, sme_id)
        try:
            await asyncio.wait_for(barrier.wait(), timeout=1)
        except (TimeoutError, asyncio.BrokenBarrierError):
            pass
        return collected

    monkeypatch.setattr(trust_engine, "collect_inputs", synchronized_collect)

    async def recalc() -> None:
        async with database.anon_transaction() as conn:
            await trust_engine.recalculate(conn, store["id"], trigger="concurrent")

    await asyncio.gather(recalc(), recalc(), recalc())
    assert (await _history_triggers(engine, store["id"])).count("concurrent") == 1
