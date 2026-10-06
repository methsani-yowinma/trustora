import hashlib
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.conftest import JPEG_BYTES, PDF_BYTES, FakeStorage

API = "/api/v1"


def _submission(*files: tuple[str, bytes, str]) -> dict[str, Any]:
    return {
        "data": {"business_reg_number": "PV 00123456", "registered_name": "Lanka Crafts (Pvt) Ltd"},
        "files": [("documents", f) for f in files]
        or [("documents", ("br.pdf", PDF_BYTES, "application/pdf"))],
    }


async def _submit(
    client: httpx.AsyncClient, owner: Any, *files: tuple[str, bytes, str]
) -> httpx.Response:
    return await client.post(
        f"{API}/smes/me/verification", headers=owner.headers, **_submission(*files)
    )


async def test_submit_verification_stores_hashed_evidence(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    response = await _submit(
        client,
        owner,
        ("br.pdf", PDF_BYTES, "application/pdf"),
        ("utility.jpg", JPEG_BYTES, "image/jpeg"),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "SUBMITTED"
    docs = body["documents"]
    assert {d["sha256"] for d in docs} == {
        hashlib.sha256(PDF_BYTES).hexdigest(),
        hashlib.sha256(JPEG_BYTES).hexdigest(),
    }
    assert all(d["type"] == "BUSINESS_DOCUMENT" and d["provenance"] == "SELLER_CLAIM" for d in docs)
    assert all(d["review_status"] == "PENDING" for d in docs)
    assert len(storage.paths("private-evidence")) == 2
    assert storage.paths("public-media") == []

    me = (await client.get(f"{API}/smes/me", headers=owner.headers)).json()
    assert me["verification_status"] == "PENDING"


async def test_cannot_resubmit_while_pending(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    assert (await _submit(client, owner)).status_code == 201
    again = await _submit(client, owner)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "verification_pending"
    assert len(storage.paths("private-evidence")) == 1  # nothing stored for the rejected attempt


async def test_invalid_document_stores_nothing(
    client: httpx.AsyncClient, make_store: Any, storage: FakeStorage
) -> None:
    owner, _ = await make_store()
    response = await _submit(
        client,
        owner,
        ("br.pdf", PDF_BYTES, "application/pdf"),
        ("evil.pdf", b"<script>", "application/pdf"),
    )
    assert response.status_code == 415
    assert storage.objects == {}
    me = (await client.get(f"{API}/smes/me", headers=owner.headers)).json()
    assert me["verification_status"] == "UNVERIFIED"


async def test_document_count_limits(client: httpx.AsyncClient, make_store: Any) -> None:
    owner, _ = await make_store()
    too_many = [("documents", (f"d{i}.pdf", PDF_BYTES, "application/pdf")) for i in range(6)]
    response = await client.post(
        f"{API}/smes/me/verification",
        headers=owner.headers,
        data={"business_reg_number": "PV 1", "registered_name": "Name"},
        files=too_many,
    )
    assert response.status_code == 422


async def test_admin_approves_verification(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, engine: AsyncEngine
) -> None:
    owner, store = await make_store(contact_phone="+94 71 000 0000")
    admin = await make_actor("ADMIN")
    verification = (await _submit(client, owner)).json()

    queue = (await client.get(f"{API}/admin/verifications", headers=admin.headers)).json()
    assert verification["id"] in [item["id"] for item in queue]

    detail = (
        await client.get(f"{API}/admin/verifications/{verification['id']}", headers=admin.headers)
    ).json()
    assert detail["sme"]["slug"] == store["slug"]
    assert detail["documents"][0]["download_url"].startswith(
        "https://storage.test/sign/private-evidence/"
    )

    response = await client.post(
        f"{API}/admin/verifications/{verification['id']}/decision",
        headers=admin.headers,
        json={"decision": "APPROVED", "contact_verified": True, "note": "BR matches registry"},
    )
    assert response.status_code == 200, response.text
    decided = response.json()
    assert decided["status"] == "APPROVED"
    assert decided["sme"]["verification_status"] == "VERIFIED"
    assert decided["sme"]["contact_verified"] is True
    assert all(
        d["review_status"] == "ACCEPTED"
        for d in decided["documents"]
        if d["type"] == "BUSINESS_DOCUMENT"
    )
    results = [d for d in decided["documents"] if d["type"] == "VERIFICATION_RESULT"]
    assert results and results[0]["provenance"] == "VERIFIED_FACT"

    # Deciding twice is refused.
    again = await client.post(
        f"{API}/admin/verifications/{verification['id']}/decision",
        headers=admin.headers,
        json={"decision": "REJECTED", "note": "x"},
    )
    assert again.status_code == 409

    async with engine.connect() as conn:
        actions = (
            (
                await conn.execute(
                    text("select action from public.audit_logs where target_id = :id order by id"),
                    {"id": verification["id"]},
                )
            )
            .scalars()
            .all()
        )
    assert actions == ["verification.submitted", "verification.approved"]

    # Changing contact details after verification clears the contact confirmation.
    me = (
        await client.patch(
            f"{API}/smes/me", headers=owner.headers, json={"contact_phone": "+94 77 999 9999"}
        )
    ).json()
    assert me["verification_status"] == "VERIFIED"
    assert me["contact_verified"] is False


async def test_rejection_requires_note_and_allows_resubmission(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, _ = await make_store()
    admin = await make_actor("ADMIN")
    verification = (await _submit(client, owner)).json()
    url = f"{API}/admin/verifications/{verification['id']}/decision"

    assert (
        await client.post(url, headers=admin.headers, json={"decision": "REJECTED"})
    ).status_code == 422
    response = await client.post(
        url, headers=admin.headers, json={"decision": "REJECTED", "note": "Document is not legible"}
    )
    assert response.status_code == 200
    assert response.json()["sme"]["verification_status"] == "REJECTED"

    history = (await client.get(f"{API}/smes/me/verification", headers=owner.headers)).json()
    assert history[0]["decision_note"] == "Document is not legible"
    assert (await _submit(client, owner)).status_code == 201


async def test_verified_business_cannot_resubmit(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any
) -> None:
    owner, _ = await make_store()
    admin = await make_actor("ADMIN")
    verification = (await _submit(client, owner)).json()
    await client.post(
        f"{API}/admin/verifications/{verification['id']}/decision",
        headers=admin.headers,
        json={"decision": "APPROVED"},
    )
    response = await _submit(client, owner)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_verified"


@pytest.mark.parametrize("role", ["SME", "CUSTOMER"])
async def test_non_admins_cannot_access_admin_endpoints(
    client: httpx.AsyncClient, make_store: Any, make_actor: Any, role: str
) -> None:
    owner, _ = await make_store()
    verification = (await _submit(client, owner)).json()
    actor = owner if role == "SME" else await make_actor("CUSTOMER")
    assert (
        await client.get(f"{API}/admin/verifications", headers=actor.headers)
    ).status_code == 403
    decision = await client.post(
        f"{API}/admin/verifications/{verification['id']}/decision",
        headers=actor.headers,
        json={"decision": "APPROVED"},
    )
    assert decision.status_code == 403


async def test_sme_sees_only_own_verifications(client: httpx.AsyncClient, make_store: Any) -> None:
    owner_a, _ = await make_store()
    owner_b, _ = await make_store()
    await _submit(client, owner_a)
    assert (await client.get(f"{API}/smes/me/verification", headers=owner_b.headers)).json() == []
