"""Phase 9: security hardening — regression tests.

Covers what Phase 9 fixed or locked down: direct Data API access to domain tables, RPC exposure
of helper functions, the authorization contract of every route, request size limits and
security headers.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.middleware import MAX_MULTIPART_BYTES, MAX_OTHER_BYTES
from app.main import create_app
from tests.test_ai import _delivered_order
from tests.test_rls import as_role

API = "/api/v1"


# --- Direct Data API access (PostgREST/GraphQL as anon/authenticated) ---------------------------
@pytest.fixture
async def marketplace(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> dict[str, Any]:
    """A published store with a product, a delivered order, a review and a social account."""
    ctx = await _delivered_order(client, make_store, make_actor)
    review = await client.post(f"{API}/orders/{ctx['order']['id']}/review",
                               headers=ctx["customer"].headers, json={"rating": 5, "comment": "Great"})  # fmt: skip
    assert review.status_code == 201, review.text
    social = await client.post(f"{API}/smes/me/social-accounts", headers=ctx["owner"].headers,
                               json={"platform": "FACEBOOK", "handle": "lankacrafts"})  # fmt: skip
    assert social.status_code == 201, social.text
    return ctx


async def _public_tables(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("select tablename from pg_tables where schemaname = 'public' order by 1")
        )
        return list(rows.scalars())


async def _count(conn: Any, table: str) -> int | str:
    """Visible rows, or "denied" when the role has no privilege on the table at all."""
    savepoint = await conn.begin_nested()
    try:
        count = (await conn.execute(text(f'select count(*) from public."{table}"'))).scalar_one()  # noqa: S608
    except DBAPIError as exc:
        assert "permission denied" in str(exc)
        await savepoint.rollback()
        return "denied"
    await savepoint.commit()
    return count


async def test_direct_data_api_requests_see_no_rows(
    engine: AsyncEngine, marketplace: dict[str, Any], make_actor: Any
) -> None:
    customer, owner = marketplace["customer"], marketplace["owner"]
    stranger = await make_actor("CUSTOMER")
    tables = await _public_tables(engine)
    assert len(tables) >= 19

    for role, user in (("anon", None), ("authenticated", customer.id),
                       ("authenticated", owner.id), ("authenticated", stranger.id)):  # fmt: skip
        async with as_role(engine, role, user, via_api=False) as conn:
            visible = {t: await _count(conn, t) for t in tables}
        assert set(visible.values()) <= {0, "denied"}, (role, user, visible)

    # The same requests through the API path still see what RLS allows (rows exist).
    async with as_role(engine, "authenticated", customer.id) as conn:
        assert await _count(conn, "orders") == 1
    async with as_role(engine, "anon") as conn:
        assert await _count(conn, "reviews") >= 1


async def test_reviewer_identity_and_codes_are_not_reachable_directly(
    engine: AsyncEngine, marketplace: dict[str, Any], make_actor: Any
) -> None:
    # Previously: any signed-in user could read reviews.customer_id and social verification codes
    # of public stores through the Data API (column grants are per role, not per row).
    stranger = await make_actor("CUSTOMER")
    async with as_role(engine, "authenticated", stranger.id, via_api=False) as conn:
        assert (await conn.execute(text("select customer_id from public.reviews"))).all() == []
        assert (await conn.execute(
            text("select verification_code, verified_by from public.sme_social_accounts")
        )).all() == []  # fmt: skip
        assert (await conn.execute(text("select owner_id from public.smes"))).all() == []


async def test_direct_data_api_requests_cannot_write(
    engine: AsyncEngine, marketplace: dict[str, Any]
) -> None:
    owner = marketplace["owner"]
    store_id = marketplace["store"]["id"]
    async with as_role(engine, "authenticated", owner.id, via_api=False) as conn:
        updated = await conn.execute(
            text("update public.products set price_lkr = 1 where sme_id = :id"), {"id": store_id}
        )
        assert updated.rowcount == 0
        deleted = await conn.execute(
            text("delete from public.sme_social_accounts where sme_id = :id"), {"id": store_id}
        )
        assert deleted.rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(text(
                "insert into public.products (sme_id, category_id, name_i18n, price_lkr, stock) "
                "values (:id, 2, '{\"en\": \"Fake\"}', 10, 1)"
            ), {"id": store_id})  # fmt: skip

    # The owner can still edit through the API.
    async with as_role(engine, "authenticated", owner.id) as conn:
        updated = await conn.execute(
            text("update public.products set price_lkr = 600 where sme_id = :id"), {"id": store_id}
        )
        assert updated.rowcount == 1


async def test_every_table_requires_the_api_path(engine: AsyncEngine) -> None:
    """Fails when a new table is added without the restrictive api_only policy."""
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "select t.tablename, t.rowsecurity, p.permissive, p.roles::text[] as roles, p.cmd "
            "from pg_tables t left join pg_policies p "
            "  on p.schemaname = t.schemaname and p.tablename = t.tablename and p.policyname = 'api_only' "
            "where t.schemaname = 'public' order by 1"
        ))).mappings().all()  # fmt: skip
    for row in rows:
        assert row["rowsecurity"], row["tablename"]
        assert row["permissive"] == "RESTRICTIVE", row["tablename"]
        assert sorted(row["roles"]) == ["anon", "authenticated"], row["tablename"]
        assert row["cmd"] == "ALL", row["tablename"]


async def test_no_callable_functions_in_the_exposed_schema(engine: AsyncEngine) -> None:
    """RLS helpers live in `private`; `public` keeps trigger functions only (not callable as RPC)."""
    async with engine.connect() as conn:
        callable_ = (await conn.execute(text(
            "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public' and p.prorettype <> 'trigger'::regtype"
        ))).scalars().all()  # fmt: skip
        unpinned = (await conn.execute(text(
            "select n.nspname || '.' || p.proname from pg_proc p "
            "join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname in ('public', 'private') and p.prosecdef "
            "and not coalesce(p.proconfig::text[] @> array['search_path=\"\"'], false)"
        ))).scalars().all()  # fmt: skip
    assert callable_ == []
    assert unpinned == []  # SECURITY DEFINER functions must pin an empty search_path


# --- Authorization contract of every route -------------------------------------------------------
# Every route must be listed here with its access rule. A new route without an entry fails, so
# its authorization is a deliberate, reviewed decision.
EXPECTED_ACCESS = {
    "GET /api/v1/health": "PUBLIC",
    "GET /api/v1/me": "ANY_USER",
    "PATCH /api/v1/me": "ANY_USER",
    "POST /api/v1/chat": "OPTIONAL_USER",
    # Public, read-only (anon role)
    **{f"GET /api/v1/{p}": "PUBLIC" for p in (
        "stores", "stores/{slug}", "stores/{slug}/products", "stores/{slug}/passport",
        "stores/{slug}/trust/history", "stores/{slug}/trust/explanation", "stores/{slug}/reviews",
        "stores/{slug}/complaints/summary", "products", "products/{product_id}", "categories",
    )},
    "POST /api/v1/checkout/quote": "PUBLIC",
    # Customer
    **{route: "CUSTOMER" for route in (
        "POST /api/v1/checkout", "GET /api/v1/orders", "GET /api/v1/orders/{order_id}",
        "POST /api/v1/orders/{order_id}/cancel", "POST /api/v1/orders/{order_id}/confirm-receipt",
        "POST /api/v1/orders/{order_id}/review", "POST /api/v1/orders/{order_id}/complaints",
        "GET /api/v1/complaints", "GET /api/v1/complaints/{complaint_id}",
        "POST /api/v1/complaints/{complaint_id}/resolve",
        "POST /api/v1/complaints/{complaint_id}/escalate",
        "POST /api/v1/complaints/{complaint_id}/evidence",
    )},
    # SME
    **{route: "SME" for route in (
        "POST /api/v1/smes", "GET /api/v1/smes/me", "PATCH /api/v1/smes/me",
        "POST /api/v1/smes/me/logo", "POST /api/v1/smes/me/social-accounts",
        "DELETE /api/v1/smes/me/social-accounts/{account_id}",
        "GET /api/v1/smes/me/verification", "POST /api/v1/smes/me/verification",
        "GET /api/v1/sme/products", "POST /api/v1/sme/products",
        "GET /api/v1/sme/products/{product_id}", "PATCH /api/v1/sme/products/{product_id}",
        "DELETE /api/v1/sme/products/{product_id}", "POST /api/v1/sme/products/{product_id}/images",
        "DELETE /api/v1/sme/products/{product_id}/images/{image_id}",
        "POST /api/v1/sme/products/{product_id}/evidence", "GET /api/v1/sme/trust",
        "GET /api/v1/sme/orders", "GET /api/v1/sme/orders/{order_id}",
        "POST /api/v1/sme/orders/{order_id}/status", "GET /api/v1/sme/reviews",
        "POST /api/v1/sme/reviews/{review_id}/response", "GET /api/v1/sme/complaints",
        "GET /api/v1/sme/complaints/{complaint_id}",
        "POST /api/v1/sme/complaints/{complaint_id}/response",
        "POST /api/v1/sme/complaints/{complaint_id}/evidence",
    )},
    # Admin
    **{route: "ADMIN" for route in (
        "GET /api/v1/admin/verifications", "GET /api/v1/admin/verifications/{verification_id}",
        "POST /api/v1/admin/verifications/{verification_id}/decision",
        "GET /api/v1/admin/social-accounts", "POST /api/v1/admin/social-accounts/{account_id}/decision",
        "GET /api/v1/admin/evidence", "POST /api/v1/admin/evidence/{evidence_id}/review",
        "POST /api/v1/admin/evidence/{evidence_id}/analyze",
        "POST /api/v1/admin/smes/{sme_id}/trust/recalculate", "GET /api/v1/admin/complaints",
        "GET /api/v1/admin/complaints/{complaint_id}",
        "POST /api/v1/admin/complaints/{complaint_id}/decision",
    )},
}  # fmt: skip


def _walk(dependant: Any, found: set[str]) -> set[str]:
    call = dependant.call
    name = getattr(call, "__qualname__", type(call).__name__)
    if name == "require_role.<locals>._check":
        roles = next(
            c.cell_contents for c in call.__closure__ if isinstance(c.cell_contents, tuple)
        )
        found.add("ROLE:" + "|".join(sorted(r.value for r in roles)))
    else:
        found.add(name)
    for sub in dependant.dependencies:
        _walk(sub, found)
    return found


def _route_access(app: Any) -> dict[str, tuple[str, set[str]]]:
    access: dict[str, tuple[str, set[str]]] = {}
    for route in app.routes:
        if not hasattr(route, "effective_route_contexts"):
            continue
        for ctx in route.effective_route_contexts():
            deps = _walk(ctx.dependant, set())
            roles = sorted(d[5:] for d in deps if d.startswith("ROLE:"))
            rule = (roles[0] if len(roles) == 1 else "|".join(roles)) if roles else (
                "OPTIONAL_USER" if "get_optional_identity" in deps
                else "ANY_USER" if "get_current_user" in deps else "PUBLIC"
            )  # fmt: skip
            for method in ctx.methods:
                access[f"{method} {ctx.path}"] = (rule, deps)
    return access


def test_every_route_has_the_expected_access_rule(app: Any) -> None:
    actual = {route: rule for route, (rule, _) in _route_access(app).items()}
    assert actual == EXPECTED_ACCESS


def test_public_routes_never_use_a_signed_in_transaction(app: Any) -> None:
    for route, (rule, deps) in _route_access(app).items():
        if rule == "PUBLIC":
            assert "get_user_db" not in deps and "get_current_user" not in deps, route


# --- Request size limits -------------------------------------------------------------------------
async def test_oversized_json_body_is_rejected_before_parsing(client: httpx.AsyncClient) -> None:
    body = b'{"messages": [{"role": "user", "text": "' + b"x" * (MAX_OTHER_BYTES + 10) + b'"}]}'
    response = await client.post(
        f"{API}/chat", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert response.headers["X-Request-ID"]


async def test_streamed_body_without_length_is_limited(client: httpx.AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(MAX_OTHER_BYTES // (64 * 1024) + 2):
            yield b"x" * (64 * 1024)

    response = await client.post(
        f"{API}/checkout/quote", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413


async def test_invalid_content_length_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{API}/checkout/quote",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "abc"},
    )
    assert response.status_code in (400, 413)


async def test_multipart_has_a_larger_but_finite_limit(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, _ = await make_store()
    oversized = await client.post(
        f"{API}/smes/me/logo",
        headers={**owner.headers, "Content-Type": "multipart/form-data; boundary=x",
                 "Content-Length": str(MAX_MULTIPART_BYTES + 1)},
        content=b"--x--",
    )  # fmt: skip
    assert oversized.status_code == 413


# --- Security headers ----------------------------------------------------------------------------
async def test_api_responses_cannot_run_or_be_framed(client: httpx.AsyncClient) -> None:
    response = await client.get(f"{API}/categories")
    assert (
        response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-site"
    assert response.headers["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in response.headers  # development/test: plain HTTP

    docs = await client.get("/docs")
    assert docs.status_code == 200 and "Content-Security-Policy" not in docs.headers


async def test_hsts_in_production(settings: Any, database: Any, token_verifier: Any) -> None:
    prod = settings.model_copy(update={"app_env": "production"})
    app = create_app(prod, db=database, token_verifier=token_verifier)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        response = await c.get(f"{API}/health")
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
