from typing import Any

import httpx

from app.core.db import Database
from app.main import create_app


async def test_health_reports_database_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_reports_degraded_when_database_down(
    settings: Any, token_verifier: Any
) -> None:
    class DownDatabase(Database):
        def __init__(self) -> None:
            pass

        async def ping(self) -> bool:
            raise ConnectionError("db down")

    app = create_app(settings, db=DownDatabase(), token_verifier=token_verifier)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        response = await c.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "database": "unavailable"}


async def test_security_headers_and_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_unsafe_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "bad id;injected"})
    assert response.headers["X-Request-ID"] != "bad id;injected"
    assert len(response.headers["X-Request-ID"]) == 32


async def test_cors_allows_configured_origin_only(client: httpx.AsyncClient) -> None:
    preflight = {"Access-Control-Request-Method": "GET"}
    ok = await client.options(
        "/api/v1/me", headers={"Origin": "http://localhost:3000", **preflight}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"

    blocked = await client.options(
        "/api/v1/me", headers={"Origin": "https://evil.example", **preflight}
    )
    assert "access-control-allow-origin" not in blocked.headers


async def test_docs_hidden_in_production(settings: Any, database: Any, token_verifier: Any) -> None:
    prod = settings.model_copy(update={"app_env": "production"})
    app = create_app(prod, db=database, token_verifier=token_verifier)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/docs")).status_code == 404
        assert (await c.get("/openapi.json")).status_code == 404


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


async def test_rate_limit_returns_429(client: httpx.AsyncClient) -> None:
    statuses = [(await client.get("/api/v1/me")).status_code for _ in range(125)]
    assert statuses[0] == 401
    assert statuses[-1] == 429
