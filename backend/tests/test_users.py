from typing import Any

import httpx
import pytest

from tests.conftest import bearer


@pytest.mark.parametrize(
    ("metadata", "expected_role", "expected_locale"),
    [
        ({}, "CUSTOMER", "en"),
        ({"role": "SME", "locale": "si"}, "SME", "si"),
        ({"role": "ADMIN"}, "CUSTOMER", "en"),  # ADMIN can never be self-assigned at signup
        ({"role": "CUSTOMER", "locale": "fr"}, "CUSTOMER", "en"),
    ],
)
async def test_signup_creates_profile_with_safe_role(
    client: httpx.AsyncClient,
    create_user: Any,
    make_token: Any,
    metadata: dict[str, str],
    expected_role: str,
    expected_locale: str,
) -> None:
    user = await create_user(metadata)
    token = make_token(user.id, email=user.email)
    response = await client.get("/api/v1/me", headers=bearer(token))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user.id
    assert body["email"] == user.email
    assert body["role"] == expected_role
    assert body["status"] == "ACTIVE"
    assert body["preferred_locale"] == expected_locale


async def test_update_own_profile(
    client: httpx.AsyncClient, create_user: Any, make_token: Any
) -> None:
    user = await create_user({"full_name": "Nimal"})
    response = await client.patch(
        "/api/v1/me",
        headers=bearer(make_token(user.id)),
        json={
            "full_name": "  නිමල් පෙරේරා  ",
            "preferred_locale": "si",
            "phone": "+94 77 123 4567",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "නිමල් පෙරේරා"
    assert body["preferred_locale"] == "si"
    assert body["phone"] == "+94 77 123 4567"


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "ADMIN"},
        {"status": "ACTIVE"},
        {"id": "00000000-0000-0000-0000-000000000000"},
        {"preferred_locale": "ta"},
        {"phone": "call me maybe"},
        {"full_name": ""},
    ],
)
async def test_update_rejects_privileged_or_invalid_fields(
    client: httpx.AsyncClient, create_user: Any, make_token: Any, payload: dict[str, str]
) -> None:
    user = await create_user()
    headers = bearer(make_token(user.id))
    response = await client.patch("/api/v1/me", headers=headers, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"

    me = (await client.get("/api/v1/me", headers=headers)).json()
    assert me["role"] == "CUSTOMER"


async def test_validation_errors_do_not_echo_input(
    client: httpx.AsyncClient, create_user: Any, make_token: Any
) -> None:
    user = await create_user()
    response = await client.patch(
        "/api/v1/me",
        headers=bearer(make_token(user.id)),
        json={"phone": "<script>secret</script>"},
    )
    assert response.status_code == 422
    assert "<script>" not in response.text
