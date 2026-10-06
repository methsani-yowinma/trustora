import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import APIRouter, Depends

from app.auth.dependencies import require_role
from app.auth.models import CurrentUser, UserRole
from app.core.errors import UnauthorizedError
from app.core.security import TokenVerifier
from tests.conftest import ISSUER, FakeJWKS, bearer


def _error_code(response: httpx.Response) -> str:
    return response.json()["error"]["code"]


async def test_missing_token_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert _error_code(response) == "unauthorized"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b.c"])
async def test_malformed_token_is_rejected(client: httpx.AsyncClient, token: str) -> None:
    response = await client.get("/api/v1/me", headers=bearer(token))
    assert response.status_code == 401


async def test_token_signed_by_other_key_is_rejected(
    client: httpx.AsyncClient, create_user: Any
) -> None:
    user = await create_user()
    now = int(time.time())
    forged = jwt.encode(
        {
            "sub": user.id,
            "role": "authenticated",
            "aud": "authenticated",
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
        },
        ec.generate_private_key(ec.SECP256R1()),
        algorithm="ES256",
    )
    response = await client.get("/api/v1/me", headers=bearer(forged))
    assert response.status_code == 401


async def test_expired_token_is_rejected(
    client: httpx.AsyncClient, create_user: Any, make_token: Any
) -> None:
    user = await create_user()
    past = int(time.time()) - 7200
    token = make_token(user.id, iat=past, exp=past + 60)
    response = await client.get("/api/v1/me", headers=bearer(token))
    assert response.status_code == 401
    assert _error_code(response) == "token_expired"


@pytest.mark.parametrize(
    "override",
    [
        {"aud": "something-else"},
        {"iss": "https://attacker.supabase.co/auth/v1"},
        {"role": "service_role"},
        {"role": "anon"},
    ],
)
async def test_wrong_claims_are_rejected(
    client: httpx.AsyncClient, create_user: Any, make_token: Any, override: dict[str, str]
) -> None:
    user = await create_user()
    response = await client.get("/api/v1/me", headers=bearer(make_token(user.id, **override)))
    assert response.status_code == 401


def _verifier(signing_key: Any, secret: str | None = None) -> TokenVerifier:
    return TokenVerifier(
        issuer=ISSUER, jwks_client=FakeJWKS(signing_key.public_key()), hs256_secret=secret
    )


def test_unsigned_alg_none_token_is_rejected(signing_key: Any) -> None:
    token = jwt.encode(
        {"sub": "x", "aud": "authenticated", "iss": ISSUER}, key=None, algorithm="none"
    )
    with pytest.raises(UnauthorizedError):
        _verifier(signing_key).verify(token)


def _hs256_token(secret: str) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "role": "authenticated",
            "aud": "authenticated",
            "iss": ISSUER,
            "iat": now,
            "exp": now + 60,
        },
        secret,
        algorithm="HS256",
    )


def test_hs256_rejected_without_configured_secret(signing_key: Any) -> None:
    with pytest.raises(UnauthorizedError):
        _verifier(signing_key).verify(_hs256_token("x" * 40))


def test_hs256_accepted_only_with_matching_secret(signing_key: Any) -> None:
    secret = "legacy-secret-" + "x" * 32
    verifier = _verifier(signing_key, secret)
    assert verifier.verify(_hs256_token(secret)).user_id.endswith("0001")
    with pytest.raises(UnauthorizedError):
        verifier.verify(_hs256_token("wrong-" + "y" * 40))


async def test_valid_token_without_profile_is_forbidden(
    client: httpx.AsyncClient, make_token: Any
) -> None:
    token = make_token("11111111-1111-1111-1111-111111111111")
    response = await client.get("/api/v1/me", headers=bearer(token))
    assert response.status_code == 403
    assert _error_code(response) == "profile_missing"


async def test_suspended_account_is_forbidden(
    client: httpx.AsyncClient, create_user: Any, make_token: Any
) -> None:
    user = await create_user(status="SUSPENDED")
    response = await client.get("/api/v1/me", headers=bearer(make_token(user.id)))
    assert response.status_code == 403
    assert _error_code(response) == "account_suspended"


# --- RBAC -----------------------------------------------------------------
@pytest.fixture
async def rbac_client(app: Any) -> Any:
    router = APIRouter()

    @router.get("/_test/admin-only")
    async def admin_only(
        user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    ) -> dict[str, str]:
        return {"role": user.role}

    @router.get("/_test/sme-or-admin")
    async def sme_or_admin(
        user: CurrentUser = Depends(require_role(UserRole.SME, UserRole.ADMIN)),
    ) -> dict[str, str]:
        return {"role": user.role}

    app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        yield c


@pytest.mark.parametrize(
    ("role", "path", "expected"),
    [
        ("CUSTOMER", "/_test/admin-only", 403),
        ("SME", "/_test/admin-only", 403),
        ("ADMIN", "/_test/admin-only", 200),
        ("CUSTOMER", "/_test/sme-or-admin", 403),
        ("SME", "/_test/sme-or-admin", 200),
        ("ADMIN", "/_test/sme-or-admin", 200),
    ],
)
async def test_require_role(
    rbac_client: httpx.AsyncClient,
    create_user: Any,
    make_token: Any,
    role: str,
    path: str,
    expected: int,
) -> None:
    user = await create_user(role=role)
    response = await rbac_client.get(path, headers=bearer(make_token(user.id)))
    assert response.status_code == expected
