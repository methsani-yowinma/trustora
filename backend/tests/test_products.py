from typing import Any

import httpx
import pytest

from tests.conftest import JPEG_BYTES, PDF_BYTES, PNG_BYTES, FakeStorage

API = "/api/v1"

PRODUCT = {
    "category_id": 1,
    "name_i18n": {"en": "Handloom saree", "si": "අත්යන්ත්‍ර සාරිය"},
    "description_i18n": {"en": "Pure cotton, made in Dumbara"},
    "price_lkr": "12500.00",
    "stock": 4,
}


async def _create(client: httpx.AsyncClient, owner: Any, **overrides: Any) -> dict[str, Any]:
    response = await client.post(
        f"{API}/sme/products", headers=owner.headers, json={**PRODUCT, **overrides}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_categories_are_public_and_localized(client: httpx.AsyncClient) -> None:
    categories = (await client.get(f"{API}/categories")).json()
    assert categories[0]["name_i18n"]["si"]
    assert {c["slug"] for c in categories} >= {"fashion", "beauty", "electronics"}


async def test_create_update_and_remove_product(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, _ = await make_store()
    product = await _create(client, owner)
    assert product["authenticity_status"] == "UNVERIFIED"
    assert product["price_lkr"] == "12500.00"
    assert product["status"] == "ACTIVE"

    updated = await client.patch(
        f"{API}/sme/products/{product['id']}",
        headers=owner.headers,
        json={"price_lkr": "11999.50", "stock": 0, "status": "HIDDEN"},
    )
    assert updated.status_code == 200
    assert updated.json()["price_lkr"] == "11999.50"
    assert updated.json()["status"] == "HIDDEN"

    removed = await client.delete(f"{API}/sme/products/{product['id']}", headers=owner.headers)
    assert removed.status_code == 204
    assert (
        await client.get(f"{API}/sme/products/{product['id']}", headers=owner.headers)
    ).status_code == 404
    assert (await client.get(f"{API}/sme/products", headers=owner.headers)).json() == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"price_lkr": "0"},
        {"price_lkr": "-5"},
        {"price_lkr": "10.999"},
        {"price_lkr": "20000000"},
        {"stock": -1},
        {"category_id": 9999},
        {"name_i18n": {}},
        {"name_i18n": {"en": "  "}},
        {"status": "REMOVED"},
        {"authenticity_status": "VERIFIED"},
        {"sme_id": "00000000-0000-0000-0000-000000000000"},
    ],
)
async def test_invalid_product_payloads(
    client: httpx.AsyncClient, make_store: Any, overrides: dict[str, Any]
) -> None:
    owner, _ = await make_store()
    response = await client.post(
        f"{API}/sme/products", headers=owner.headers, json={**PRODUCT, **overrides}
    )
    assert response.status_code == 422


async def test_sme_isolation(client: httpx.AsyncClient, make_store: Any) -> None:
    """SME A cannot read, change, remove or attach files to SME B's products."""
    owner_a, _ = await make_store()
    owner_b, _ = await make_store()
    product = await _create(client, owner_a)
    url = f"{API}/sme/products/{product['id']}"

    assert (await client.get(url, headers=owner_b.headers)).status_code == 404
    assert (
        await client.patch(url, headers=owner_b.headers, json={"price_lkr": "1.00"})
    ).status_code == 404
    assert (await client.delete(url, headers=owner_b.headers)).status_code == 404
    image = await client.post(
        f"{url}/images", headers=owner_b.headers, files={"file": ("x.png", PNG_BYTES, "image/png")}
    )
    assert image.status_code == 404
    assert product["id"] not in [
        p["id"] for p in (await client.get(f"{API}/sme/products", headers=owner_b.headers)).json()
    ]

    unchanged = (await client.get(url, headers=owner_a.headers)).json()
    assert unchanged["price_lkr"] == "12500.00"


async def test_customers_cannot_manage_products(client: httpx.AsyncClient, make_actor: Any) -> None:
    customer = await make_actor("CUSTOMER")
    assert (
        await client.post(f"{API}/sme/products", headers=customer.headers, json=PRODUCT)
    ).status_code == 403
    assert (await client.get(f"{API}/sme/products", headers=customer.headers)).status_code == 403


async def test_product_images(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    product = await _create(client, owner)
    url = f"{API}/sme/products/{product['id']}/images"

    first = await client.post(
        url, headers=owner.headers, files={"file": ("a.png", PNG_BYTES, "image/png")}
    )
    second = await client.post(
        url, headers=owner.headers, files={"file": ("b.jpg", JPEG_BYTES, "image/jpeg")}
    )
    assert first.status_code == second.status_code == 200
    images = second.json()["images"]
    assert [i["sort_order"] for i in images] == [0, 1]

    deleted = await client.delete(f"{url}/{images[0]['id']}", headers=owner.headers)
    assert deleted.status_code == 200
    assert len(deleted.json()["images"]) == 1
    assert len(storage.paths("public-media")) == 1


async def test_image_limit(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, _ = await make_store()
    product = await _create(client, owner)
    url = f"{API}/sme/products/{product['id']}/images"
    for _ in range(8):
        assert (
            await client.post(
                url, headers=owner.headers, files={"file": ("a.png", PNG_BYTES, "image/png")}
            )
        ).status_code == 200
    ninth = await client.post(
        url, headers=owner.headers, files={"file": ("a.png", PNG_BYTES, "image/png")}
    )
    assert ninth.status_code == 409


async def test_authenticity_evidence_is_private_and_pending(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    product = await _create(client, owner)
    response = await client.post(
        f"{API}/sme/products/{product['id']}/evidence",
        headers=owner.headers,
        data={
            "evidence_type": "PRODUCT_DOCUMENT",
            "description": "Supplier invoice from distributor",
        },
        files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    evidence = body["evidence"][0]
    assert evidence["provenance"] == "SELLER_CLAIM"
    assert evidence["review_status"] == "PENDING"
    assert evidence["download_url"].startswith("https://storage.test/sign/private-evidence/")
    # Uploading evidence never changes authenticity by itself.
    assert body["authenticity_status"] == "UNVERIFIED"
    assert storage.paths("public-media") == []


async def test_public_store_lists_only_active_products(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, store = await make_store(published=True)
    visible = await _create(client, owner)
    hidden = await _create(client, owner, status="HIDDEN")
    removed = await _create(client, owner)
    await client.delete(f"{API}/sme/products/{removed['id']}", headers=owner.headers)
    await _create(client, owner, stock=0, name_i18n={"en": "Sold out item"})

    products = (await client.get(f"{API}/stores/{store['slug']}/products")).json()
    ids = {p["id"] for p in products}
    assert visible["id"] in ids
    assert hidden["id"] not in ids and removed["id"] not in ids
    sold_out = next(p for p in products if p["name_i18n"]["en"] == "Sold out item")
    assert sold_out["in_stock"] is False
    assert "stock" not in sold_out


async def test_unpublished_store_products_are_not_public(
    client: httpx.AsyncClient, make_store: Any
) -> None:
    owner, store = await make_store()
    await _create(client, owner)
    assert (await client.get(f"{API}/stores/{store['slug']}/products")).status_code == 404
