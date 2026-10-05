"""Direct database access as a browser would have it (Supabase REST + user JWT), bypassing
the backend. Verification, trust and evidence fields must be safe even then."""

from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.test_rls import as_role

API = "/api/v1"


async def _product(client: httpx.AsyncClient, owner: Any) -> str:
    response = await client.post(
        f"{API}/sme/products",
        headers=owner.headers,
        json={"category_id": 1, "name_i18n": {"en": "Tea"}, "price_lkr": "950.00", "stock": 3},
    )
    return response.json()["id"]


@pytest.mark.parametrize(
    "assignment",
    [
        "verification_status = 'VERIFIED'",
        "verified_at = now()",
        "contact_verified = true",
        "status = 'SUSPENDED'",
    ],
)
async def test_owner_cannot_self_verify(
    engine: AsyncEngine, make_store: Any, assignment: str
) -> None:
    owner, store = await make_store()
    async with as_role(engine, "authenticated", owner.id) as conn:
        with pytest.raises(DBAPIError, match="Only administrators"):
            await conn.execute(
                text(f"update public.smes set {assignment} where id = :id"),  # noqa: S608
                {"id": store["id"]},
            )


@pytest.mark.parametrize("column", ["slug", "logo_path", "owner_id"])
async def test_owner_cannot_change_identity_columns(
    engine: AsyncEngine, make_store: Any, column: str
) -> None:
    owner, store = await make_store()
    async with as_role(engine, "authenticated", owner.id) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(
                text(f"update public.smes set {column} = {column} where id = :id"),  # noqa: S608
                {"id": store["id"]},
            )


async def test_owner_cannot_set_product_authenticity(
    engine: AsyncEngine, client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, _ = await make_store()
    product_id = await _product(client, owner)
    async with as_role(engine, "authenticated", owner.id) as conn:
        with pytest.raises(DBAPIError, match="Only administrators"):
            await conn.execute(
                text("update public.products set authenticity_status = 'VERIFIED' where id = :id"),
                {"id": product_id},
            )
    # authenticity_status is not even in the insert grant.
    async with as_role(engine, "authenticated", owner.id) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(
                text(
                    "insert into public.products (sme_id, category_id, name_i18n, price_lkr, authenticity_status) "
                    "select sme_id, category_id, name_i18n, price_lkr, 'VERIFIED' from public.products where id = :id"
                ),
                {"id": product_id},
            )


async def test_sme_cannot_touch_other_sme_rows(
    engine: AsyncEngine, client: httpx.AsyncClient, make_store: Any
) -> None:
    owner_a, store_a = await make_store()
    owner_b, _ = await make_store()
    product_a = await _product(client, owner_a)
    async with as_role(engine, "authenticated", owner_b.id) as conn:
        assert (
            await conn.execute(
                text("select count(*) from public.smes where id = :id"), {"id": store_a["id"]}
            )
        ).scalar_one() == 0
        assert (
            await conn.execute(
                text("select count(*) from public.products where id = :id"), {"id": product_a}
            )
        ).scalar_one() == 0
        result = await conn.execute(
            text("update public.products set price_lkr = 1 where id = :id"), {"id": product_a}
        )
        assert result.rowcount == 0
    async with as_role(engine, "authenticated", owner_b.id) as conn:
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                text(
                    "insert into public.products (sme_id, category_id, name_i18n, price_lkr) "
                    'values (:sme, 1, \'{"en": "Fake"}\', 10)'
                ),
                {"sme": store_a["id"]},
            )


@pytest.mark.parametrize(
    "table", ["evidence", "business_verifications", "sme_social_accounts", "product_images"]
)
async def test_clients_cannot_insert_backend_only_rows(
    engine: AsyncEngine, make_store: Any, table: str
) -> None:
    owner, _ = await make_store()
    async with as_role(engine, "authenticated", owner.id) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text(f"insert into public.{table} default values"))  # noqa: S608


async def test_evidence_is_private(
    engine: AsyncEngine, client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, _ = await make_store(published=True)
    await client.post(
        f"{API}/smes/me/verification",
        headers=owner.headers,
        data={"business_reg_number": "PV 1", "registered_name": "Name"},
        files=[("documents", ("br.pdf", b"%PDF-1.4\n%%EOF", "application/pdf"))],
    )
    customer = await make_actor("CUSTOMER")
    async with as_role(engine, "authenticated", customer.id) as conn:
        assert (await conn.execute(text("select count(*) from public.evidence"))).scalar_one() == 0
        assert (
            await conn.execute(text("select count(*) from public.business_verifications"))
        ).scalar_one() == 0
    async with as_role(engine, "anon") as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("select * from public.evidence"))


async def test_anon_sees_only_published_stores_and_safe_columns(
    engine: AsyncEngine, make_store: Any
) -> None:
    _, published = await make_store(published=True)
    _, draft = await make_store()
    async with as_role(engine, "anon") as conn:
        slugs = set((await conn.execute(text("select slug from public.smes"))).scalars().all())
        assert published["slug"] in slugs and draft["slug"] not in slugs
    async with as_role(engine, "anon") as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("select owner_id from public.smes"))
    async with as_role(engine, "anon") as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("select verification_code from public.sme_social_accounts"))


async def test_contact_change_clears_contact_verification_even_via_direct_update(
    engine: AsyncEngine, make_store: Any
) -> None:
    owner, store = await make_store(contact_email="shop@example.lk")
    async with engine.begin() as conn:  # an admin confirmed the contact
        await conn.execute(
            text("update public.smes set contact_verified = true where id = :id"),
            {"id": store["id"]},
        )
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "select set_config('request.jwt.claims', :c, true), set_config('role', 'authenticated', true)"
            ),
            {"c": f'{{"sub": "{owner.id}", "role": "authenticated"}}'},
        )
        await conn.execute(
            text("update public.smes set contact_email = 'new@example.lk' where id = :id"),
            {"id": store["id"]},
        )
    async with engine.connect() as conn:
        verified = (
            await conn.execute(
                text("select contact_verified from public.smes where id = :id"), {"id": store["id"]}
            )
        ).scalar_one()
    assert verified is False
