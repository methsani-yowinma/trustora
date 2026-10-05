from typing import Any

import httpx
import pytest

from tests.conftest import PDF_BYTES, PNG_BYTES, FakeStorage

API = "/api/v1"


# --- Registration -------------------------------------------------------------------
async def test_sme_registers_store(client: httpx.AsyncClient, make_actor: Any) -> None:
    owner = await make_actor("SME")
    response = await client.post(
        f"{API}/smes",
        headers=owner.headers,
        json={
            "slug": "Ceylon-Spice-House",
            "name": "  Ceylon Spice House ",
            "description_i18n": {
                "en": "Fresh spices from Matale",
                "si": "මාතලේ නැවුම් කුළුබඩු",
                "ta": "",
            },
            "contact_phone": "+94 77 123 4567",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "ceylon-spice-house"
    assert body["name"] == "Ceylon Spice House"
    assert body["description_i18n"] == {"en": "Fresh spices from Matale", "si": "මාතලේ නැවුම් කුළුබඩු"}
    assert body["verification_status"] == "UNVERIFIED"
    assert body["is_published"] is False
    assert body["contact_verified"] is False


@pytest.mark.parametrize("role", ["CUSTOMER", "ADMIN"])
async def test_only_sme_accounts_can_register(
    client: httpx.AsyncClient, make_actor: Any, role: str
) -> None:
    actor = await make_actor(role)
    response = await client.post(
        f"{API}/smes", headers=actor.headers, json={"slug": "abc-shop", "name": "Shop"}
    )
    assert response.status_code == 403


async def test_one_store_per_account_and_unique_slug(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, store = await make_store()
    again = await client.post(
        f"{API}/smes", headers=owner.headers, json={"slug": "another-one", "name": "X Shop"}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "sme_exists"

    other = await make_actor("SME")
    taken = await client.post(
        f"{API}/smes", headers=other.headers, json={"slug": store["slug"], "name": "Copy"}
    )
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "slug_taken"


@pytest.mark.parametrize(
    "slug", ["ab", "admin", "Bad Slug", "-start", "end-", "a--b", "x" * 41, "සිංහල"]
)
async def test_invalid_or_reserved_slugs(
    client: httpx.AsyncClient, make_actor: Any, slug: str
) -> None:
    owner = await make_actor("SME")
    response = await client.post(
        f"{API}/smes", headers=owner.headers, json={"slug": slug, "name": "Shop"}
    )
    assert response.status_code == 422


async def test_unregistered_sme_gets_clear_error(
    client: httpx.AsyncClient, make_actor: Any
) -> None:
    owner = await make_actor("SME")
    response = await client.get(f"{API}/smes/me", headers=owner.headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "sme_not_registered"


# --- Storefront updates -------------------------------------------------------------
async def test_update_storefront_and_policies(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, _ = await make_store()
    response = await client.patch(
        f"{API}/smes/me",
        headers=owner.headers,
        json={
            "name": "Lanka Crafts & Gifts",
            "policies_i18n": {
                "returns": {"en": "Returns within 7 days", "si": "දින 7ක් ඇතුළත ආපසු"},
                "delivery": {"en": "Island-wide in 3-5 days"},
            },
            "is_published": True,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Lanka Crafts & Gifts"
    assert body["policies_i18n"]["returns"]["si"] == "දින 7ක් ඇතුළත ආපසු"
    assert "refunds" not in body["policies_i18n"]
    assert body["is_published"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"verification_status": "VERIFIED"},
        {"contact_verified": True},
        {"slug": "new-slug"},
        {"status": "ACTIVE"},
        {"name": None},
        {"policies_i18n": {"warranty": {"en": "x"}}},
        {"description_i18n": {"fr": "Bonjour"}},
        {"description_i18n": {"en": "   "}},
    ],
)
async def test_owner_cannot_set_protected_or_invalid_fields(
    client: httpx.AsyncClient, make_store: Any, payload: dict[str, Any]
) -> None:
    owner, _ = await make_store()
    response = await client.patch(f"{API}/smes/me", headers=owner.headers, json=payload)
    assert response.status_code == 422


async def test_logo_upload(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    response = await client.post(
        f"{API}/smes/me/logo",
        headers=owner.headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code == 200, response.text
    first_url = response.json()["logo_url"]
    assert first_url.startswith("https://storage.test/public/public-media/smes/")

    # Replacing the logo removes the old object.
    response = await client.post(
        f"{API}/smes/me/logo",
        headers=owner.headers,
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert response.json()["logo_url"] != first_url
    assert len(storage.paths("public-media")) == 1


async def test_logo_rejects_non_images(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    response = await client.post(
        f"{API}/smes/me/logo",
        headers=owner.headers,
        files={"file": ("logo.pdf", PDF_BYTES, "image/png")},
    )
    assert response.status_code == 415
    assert storage.objects == {}


# --- Social accounts ----------------------------------------------------------------
async def test_add_and_remove_social_account(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, _ = await make_store()
    response = await client.post(
        f"{API}/smes/me/social-accounts",
        headers=owner.headers,
        json={
            "platform": "INSTAGRAM",
            "handle": "@lanka.crafts",
            "url": "https://www.instagram.com/lanka.crafts",
        },
    )
    assert response.status_code == 201, response.text
    account = response.json()
    assert account["handle"] == "lanka.crafts"
    assert account["verification_code"].startswith("TRUSTORA-")
    assert account["ownership_verified"] is False

    duplicate = await client.post(
        f"{API}/smes/me/social-accounts",
        headers=owner.headers,
        json={"platform": "INSTAGRAM", "handle": "lanka.crafts"},
    )
    assert duplicate.status_code == 409

    deleted = await client.delete(
        f"{API}/smes/me/social-accounts/{account['id']}", headers=owner.headers
    )
    assert deleted.status_code == 204
    me = (await client.get(f"{API}/smes/me", headers=owner.headers)).json()
    assert me["social_accounts"] == []


@pytest.mark.parametrize(
    ("platform", "url"),
    [
        ("INSTAGRAM", "https://evil.example/instagram.com"),
        ("INSTAGRAM", "http://instagram.com/shop"),
        ("FACEBOOK", "https://instagram.com/shop"),
        ("WHATSAPP", "javascript:alert(1)"),
        ("TIKTOK", "https://tiktok.com.evil.example/@shop"),
    ],
)
async def test_social_url_must_match_platform(
    client: httpx.AsyncClient, make_store: Any, platform: str, url: str
) -> None:
    owner, _ = await make_store()
    response = await client.post(
        f"{API}/smes/me/social-accounts",
        headers=owner.headers,
        json={"platform": platform, "handle": "shop", "url": url},
    )
    assert response.status_code == 422


async def test_sme_cannot_delete_another_sme_social_account(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner_a, _ = await make_store()
    owner_b, _ = await make_store()
    account = (
        await client.post(
            f"{API}/smes/me/social-accounts",
            headers=owner_a.headers,
            json={"platform": "FACEBOOK", "handle": "shop-a"},
        )
    ).json()
    response = await client.delete(
        f"{API}/smes/me/social-accounts/{account['id']}", headers=owner_b.headers
    )
    assert response.status_code == 404


# --- Public store ----------------------------------------------------------------------
async def test_public_store_visibility(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, store = await make_store()
    assert (await client.get(f"{API}/stores/{store['slug']}")).status_code == 404  # unpublished

    await client.patch(f"{API}/smes/me", headers=owner.headers, json={"is_published": True})
    response = await client.get(f"{API}/stores/{store['slug'].upper()}")
    assert response.status_code == 200
    body = response.json()
    assert body["verification_status"] == "UNVERIFIED"
    assert "owner_id" not in body and "is_published" not in body


async def test_public_store_shows_only_verified_social_accounts(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, store = await make_store(published=True)
    admin = await make_actor("ADMIN")
    ids = []
    for handle in ("verified-one", "unverified-one"):
        ids.append(
            (
                await client.post(
                    f"{API}/smes/me/social-accounts",
                    headers=owner.headers,
                    json={"platform": "TIKTOK", "handle": handle},
                )
            ).json()["id"]
        )
    decision = await client.post(
        f"{API}/admin/social-accounts/{ids[0]}/decision",
        headers=admin.headers,
        json={"verified": True},
    )
    assert decision.status_code == 200
    assert decision.json()["ownership_verified"] is True

    socials = (await client.get(f"{API}/stores/{store['slug']}")).json()["social_accounts"]
    assert [s["handle"] for s in socials] == ["verified-one"]
    assert "verification_code" not in socials[0]


async def test_non_admin_cannot_verify_social_accounts(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, _ = await make_store()
    account = (
        await client.post(
            f"{API}/smes/me/social-accounts",
            headers=owner.headers,
            json={"platform": "TIKTOK", "handle": "myshop"},
        )
    ).json()
    response = await client.post(
        f"{API}/admin/social-accounts/{account['id']}/decision",
        headers=owner.headers,
        json={"verified": True},
    )
    assert response.status_code == 403
