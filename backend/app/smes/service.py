"""SME registration, storefront, social accounts and verification submission (owner side)."""

import json
import secrets
import string
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.db import Database
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, is_unique_violation
from app.core.storage import PRIVATE_BUCKET, PUBLIC_BUCKET, StorageClient, delete_quietly
from app.core.uploads import ValidatedFile
from app.evidence import service as evidence
from app.smes.schemas import (
    OwnSocialAccountOut,
    PublicStoreOut,
    SmeCreate,
    SmeOut,
    SmeUpdate,
    SocialAccountCreate,
    SocialAccountOut,
    VerificationOut,
    VerificationSummary,
)

MAX_SOCIAL_ACCOUNTS = 10
MAX_VERIFICATION_DOCUMENTS = 5

SME_COLUMNS = (
    "id, owner_id, slug, name, logo_path, description_i18n, policies_i18n, contact_email, "
    "contact_phone, contact_verified, verification_status, verified_at, is_published, status, "
    "created_at"
)
_SOCIAL_COLUMNS = (
    "id, platform, handle, url, ownership_verified, verified_at, verification_code, created_at"
)
VERIFICATION_COLUMNS = (
    "id, status, business_reg_number, registered_name, submitted_at, reviewed_at, decision_note"
)
_JSONB_COLUMNS = {"description_i18n", "policies_i18n"}


# --- Mapping helpers ------------------------------------------------------------
def logo_url(storage: StorageClient, logo_path: str | None) -> str | None:
    return storage.public_url(PUBLIC_BUCKET, logo_path) if logo_path else None


def to_verification_summary(row: Mapping[str, Any]) -> VerificationSummary:
    return VerificationSummary(**{**row, "id": str(row["id"])})


def _social_out(row: Mapping[str, Any]) -> OwnSocialAccountOut:
    return OwnSocialAccountOut(
        **{k: v for k, v in row.items() if k != "created_at"} | {"id": str(row["id"])}
    )


async def build_sme_out(
    conn: AsyncConnection, storage: StorageClient, row: Mapping[str, Any]
) -> SmeOut:
    sme_id = row["id"]
    counts = (
        await conn.execute(
            text("select status, count(*) from public.products where sme_id = :id group by status"),
            {"id": sme_id},
        )
    ).all()
    socials = (
        (
            await conn.execute(
                text(
                    f"select {_SOCIAL_COLUMNS} from public.sme_social_accounts "  # noqa: S608
                    "where sme_id = :id order by created_at"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .all()
    )
    latest = (
        (
            await conn.execute(
                text(
                    f"select {VERIFICATION_COLUMNS} from public.business_verifications "  # noqa: S608
                    "where sme_id = :id order by submitted_at desc limit 1"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .first()
    )

    return SmeOut(
        id=str(sme_id),
        slug=row["slug"],
        name=row["name"],
        logo_url=logo_url(storage, row["logo_path"]),
        description_i18n=row["description_i18n"],
        policies_i18n=row["policies_i18n"],
        contact_email=row["contact_email"],
        contact_phone=row["contact_phone"],
        contact_verified=row["contact_verified"],
        verification_status=row["verification_status"],
        verified_at=row["verified_at"],
        is_published=row["is_published"],
        status=row["status"],
        created_at=row["created_at"],
        product_counts={str(status): count for status, count in counts},
        social_accounts=[_social_out(s) for s in socials],
        latest_verification=to_verification_summary(latest) if latest else None,
    )


# --- Owner lookups --------------------------------------------------------------
async def find_own_sme(conn: AsyncConnection, user: CurrentUser) -> Mapping[str, Any] | None:
    return (
        (
            await conn.execute(
                text(f"select {SME_COLUMNS} from public.smes where owner_id = :uid"),  # noqa: S608
                {"uid": user.id},
            )
        )
        .mappings()
        .first()
    )


async def require_own_sme(
    conn: AsyncConnection, user: CurrentUser, *, active: bool = False
) -> Mapping[str, Any]:
    row = await find_own_sme(conn, user)
    if row is None:
        raise NotFoundError("Register your business first", code="sme_not_registered")
    if active and row["status"] != "ACTIVE":
        raise ForbiddenError("This business account is suspended", code="sme_suspended")
    return row


# --- Registration & storefront --------------------------------------------------
async def register_sme(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, data: SmeCreate
) -> SmeOut:
    if await find_own_sme(conn, user) is not None:
        raise ConflictError("This account already has a registered business", code="sme_exists")
    try:
        row = (
            (
                await conn.execute(
                    text(
                        "insert into public.smes (owner_id, slug, name, description_i18n, "  # noqa: S608 — fixed column list, values are bound
                        "contact_email, contact_phone) values (:owner, :slug, :name, "
                        f"cast(:description as jsonb), :email, :phone) returning {SME_COLUMNS}"
                    ),
                    {
                        "owner": user.id,
                        "slug": data.slug,
                        "name": data.name,
                        "description": json.dumps(data.description_i18n)
                        if data.description_i18n
                        else None,
                        "email": data.contact_email,
                        "phone": data.contact_phone,
                    },
                )
            )
            .mappings()
            .one()
        )
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise ConflictError("This store address is already taken", code="slug_taken") from exc
        raise

    await audit.record(
        conn,
        actor=user,
        action="sme.registered",
        target_type="sme",
        target_id=str(row["id"]),
        metadata={"slug": data.slug},
    )
    return await build_sme_out(conn, storage, row)


async def update_own_sme(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, changes: SmeUpdate
) -> SmeOut:
    current = await require_own_sme(conn, user, active=True)
    values: dict[str, Any] = {}
    for field in changes.model_fields_set:
        value = getattr(changes, field)
        if field == "policies_i18n":
            value = (
                json.dumps(changes.policies_i18n.model_dump(exclude_none=True)) if value else "{}"
            )
        elif field in _JSONB_COLUMNS:
            value = json.dumps(value) if value is not None else None
        values[field] = value

    if values:
        # Column names come only from the SmeUpdate model.
        assignments = ", ".join(
            f"{col} = cast(:{col} as jsonb)" if col in _JSONB_COLUMNS else f"{col} = :{col}"
            for col in values
        )
        await conn.execute(
            text(f"update public.smes set {assignments} where id = :id"),  # noqa: S608
            {**values, "id": current["id"]},
        )
        await audit.record(
            conn,
            actor=user,
            action="sme.updated",
            target_type="sme",
            target_id=str(current["id"]),
            metadata={"fields": sorted(values)},
        )

    return await build_sme_out(conn, storage, await require_own_sme(conn, user))


async def update_logo(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, file: ValidatedFile
) -> SmeOut:
    current = await require_own_sme(conn, user, active=True)
    path = f"smes/{current['id']}/logo-{file.storage_name()}"
    await storage.upload(PUBLIC_BUCKET, path, file.data, file.kind.mime)
    try:
        async with Database.privileged(conn):
            await conn.execute(
                text("update public.smes set logo_path = :path where id = :id"),
                {"path": path, "id": current["id"]},
            )
        await audit.record(
            conn,
            actor=user,
            action="sme.logo_updated",
            target_type="sme",
            target_id=str(current["id"]),
            metadata={"sha256": file.sha256},
        )
    except Exception:
        await delete_quietly(storage, PUBLIC_BUCKET, [path])
        raise

    if current["logo_path"]:
        await delete_quietly(storage, PUBLIC_BUCKET, [current["logo_path"]])
    return await build_sme_out(conn, storage, await require_own_sme(conn, user))


async def get_own_sme(conn: AsyncConnection, storage: StorageClient, user: CurrentUser) -> SmeOut:
    return await build_sme_out(conn, storage, await require_own_sme(conn, user))


# --- Social accounts --------------------------------------------------------------
def _new_verification_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "TRUSTORA-" + "".join(secrets.choice(alphabet) for _ in range(6))


async def add_social_account(
    conn: AsyncConnection, user: CurrentUser, data: SocialAccountCreate
) -> OwnSocialAccountOut:
    sme = await require_own_sme(conn, user, active=True)
    count = (
        await conn.execute(
            text("select count(*) from public.sme_social_accounts where sme_id = :id"),
            {"id": sme["id"]},
        )
    ).scalar_one()
    if count >= MAX_SOCIAL_ACCOUNTS:
        raise ConflictError("Social account limit reached", code="limit_reached")

    try:
        async with Database.privileged(conn):
            row = (
                (
                    await conn.execute(
                        text(
                            "insert into public.sme_social_accounts "  # noqa: S608 — fixed column list, values are bound
                            "(sme_id, platform, handle, url, verification_code) values "
                            "(:sme, cast(:platform as public.social_platform), :handle, :url, :code) "
                            f"returning {_SOCIAL_COLUMNS}"
                        ),
                        {
                            "sme": sme["id"],
                            "platform": data.platform.value,
                            "handle": data.handle,
                            "url": data.url,
                            "code": _new_verification_code(),
                        },
                    )
                )
                .mappings()
                .one()
            )
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise ConflictError("This account is already linked", code="social_exists") from exc
        raise

    await audit.record(
        conn,
        actor=user,
        action="social_account.added",
        target_type="social_account",
        target_id=str(row["id"]),
        metadata={"platform": data.platform.value, "handle": data.handle},
    )
    return _social_out(row)


async def delete_social_account(conn: AsyncConnection, user: CurrentUser, account_id: str) -> None:
    await require_own_sme(conn, user)
    result = await conn.execute(
        text("delete from public.sme_social_accounts where id = :id returning platform, handle"),
        {"id": account_id},
    )
    removed = result.mappings().first()
    if removed is None:
        raise NotFoundError("Social account not found")
    await audit.record(
        conn,
        actor=user,
        action="social_account.removed",
        target_type="social_account",
        target_id=account_id,
        metadata=dict(removed),
    )


# --- Verification (owner side) ----------------------------------------------------
async def list_own_verifications(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser
) -> list[VerificationOut]:
    sme = await require_own_sme(conn, user)
    rows = (
        (
            await conn.execute(
                text(
                    f"select {VERIFICATION_COLUMNS} from public.business_verifications "  # noqa: S608
                    "where sme_id = :id order by submitted_at desc"
                ),
                {"id": sme["id"]},
            )
        )
        .mappings()
        .all()
    )
    result = []
    for row in rows:
        documents = await evidence.list_evidence(
            conn,
            storage,
            where="verification_id = :vid",
            params={"vid": row["id"]},
            with_download_urls=False,
        )
        result.append(
            VerificationOut(**to_verification_summary(row).model_dump(), documents=documents)
        )
    return result


async def submit_verification(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    *,
    business_reg_number: str,
    registered_name: str,
    files: list[ValidatedFile],
) -> VerificationOut:
    sme = await require_own_sme(conn, user, active=True)
    if sme["verification_status"] == "VERIFIED":
        raise ConflictError("This business is already verified", code="already_verified")

    try:
        async with Database.privileged(conn):
            verification_id = str(
                (
                    await conn.execute(
                        text(
                            "insert into public.business_verifications "
                            "(sme_id, business_reg_number, registered_name, submitted_by) "
                            "values (:sme, :reg, :name, :uid) returning id"
                        ),
                        {
                            "sme": sme["id"],
                            "reg": business_reg_number,
                            "name": registered_name,
                            "uid": user.id,
                        },
                    )
                ).scalar_one()
            )
    except IntegrityError as exc:
        if is_unique_violation(exc):
            raise ConflictError(
                "A verification request is already awaiting review", code="verification_pending"
            ) from exc
        raise

    uploaded: list[str] = []
    try:
        for file in files:
            stored = await evidence.store_private_file(storage, str(sme["id"]), file)
            uploaded.append(stored.path)
            await evidence.insert_file_evidence(
                conn,
                stored=stored,
                evidence_type="BUSINESS_DOCUMENT",
                provenance="SELLER_CLAIM",
                sme_id=str(sme["id"]),
                created_by=user.id,
                verification_id=verification_id,
                description="Business verification document",
            )
        async with Database.privileged(conn):
            await conn.execute(
                text("update public.smes set verification_status = 'PENDING' where id = :id"),
                {"id": sme["id"]},
            )
        await audit.record(
            conn,
            actor=user,
            action="verification.submitted",
            target_type="business_verification",
            target_id=verification_id,
            metadata={"sme_id": str(sme["id"]), "documents": [f.sha256 for f in files]},
        )
    except Exception:
        await delete_quietly(storage, PRIVATE_BUCKET, uploaded)
        raise

    return (await list_own_verifications(conn, storage, user))[0]


# --- Public storefront ------------------------------------------------------------
async def get_public_store(
    conn: AsyncConnection, storage: StorageClient, slug: str
) -> PublicStoreOut:
    """Runs in an anon transaction: RLS only exposes published, active stores."""
    row = (
        (
            await conn.execute(
                text(
                    "select id, slug, name, logo_path, description_i18n, policies_i18n, contact_email, "
                    "contact_phone, contact_verified, verification_status, verified_at, created_at "
                    "from public.smes where slug = :slug"
                ),
                {"slug": slug.lower()},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Store not found")

    socials = (
        (
            await conn.execute(
                text(
                    "select id, platform, handle, url, ownership_verified, verified_at "
                    "from public.sme_social_accounts where sme_id = :id order by platform"
                ),
                {"id": row["id"]},
            )
        )
        .mappings()
        .all()
    )

    return PublicStoreOut(
        id=str(row["id"]),
        slug=row["slug"],
        name=row["name"],
        logo_url=logo_url(storage, row["logo_path"]),
        description_i18n=row["description_i18n"],
        policies_i18n=row["policies_i18n"],
        contact_email=row["contact_email"],
        contact_phone=row["contact_phone"],
        contact_verified=row["contact_verified"],
        verification_status=row["verification_status"],
        verified_at=row["verified_at"],
        member_since=row["created_at"],
        social_accounts=[SocialAccountOut(**{**s, "id": str(s["id"])}) for s in socials],
    )
