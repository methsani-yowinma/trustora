from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_anon_db, get_storage, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.core.errors import ValidationAppError
from app.core.rate_limit import rate_limit
from app.core.storage import StorageClient
from app.core.uploads import (
    DOCUMENT_KINDS,
    IMAGE_KINDS,
    MAX_DOCUMENT_BYTES,
    MAX_IMAGE_BYTES,
    read_upload,
)
from app.smes import admin_service, service
from app.smes.schemas import (
    AdminSocialAccountItem,
    AdminVerificationDetail,
    AdminVerificationListItem,
    OwnSocialAccountOut,
    PublicStoreOut,
    SmeCreate,
    SmeOut,
    SmeUpdate,
    SocialAccountCreate,
    SocialDecisionIn,
    VerificationDecisionIn,
    VerificationOut,
)

UPLOAD_LIMIT = Depends(rate_limit("30/minute", scope="uploads"))

sme_user = require_role(UserRole.SME)
admin_user = require_role(UserRole.ADMIN)

Db = Annotated[AsyncConnection, Depends(get_user_db)]
Storage = Annotated[StorageClient, Depends(get_storage)]
SmeUser = Annotated[CurrentUser, Depends(sme_user)]
AdminUser = Annotated[CurrentUser, Depends(admin_user)]

# --- SME owner ----------------------------------------------------------------------
router = APIRouter(prefix="/smes", tags=["smes"])


@router.post("", response_model=SmeOut, status_code=status.HTTP_201_CREATED)
async def register_sme(data: SmeCreate, user: SmeUser, conn: Db, storage: Storage) -> SmeOut:
    return await service.register_sme(conn, storage, user, data)


@router.get("/me", response_model=SmeOut)
async def read_own_sme(user: SmeUser, conn: Db, storage: Storage) -> SmeOut:
    return await service.get_own_sme(conn, storage, user)


@router.patch("/me", response_model=SmeOut)
async def update_own_sme(changes: SmeUpdate, user: SmeUser, conn: Db, storage: Storage) -> SmeOut:
    return await service.update_own_sme(conn, storage, user, changes)


@router.post("/me/logo", response_model=SmeOut, dependencies=[UPLOAD_LIMIT])
async def upload_logo(
    user: SmeUser, conn: Db, storage: Storage, file: Annotated[UploadFile, File()]
) -> SmeOut:
    validated = await read_upload(file, allowed=IMAGE_KINDS, max_bytes=MAX_IMAGE_BYTES)
    return await service.update_logo(conn, storage, user, validated)


@router.post(
    "/me/social-accounts", response_model=OwnSocialAccountOut, status_code=status.HTTP_201_CREATED
)
async def add_social_account(
    data: SocialAccountCreate, user: SmeUser, conn: Db
) -> OwnSocialAccountOut:
    return await service.add_social_account(conn, user, data)


@router.delete("/me/social-accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_social_account(account_id: UUID, user: SmeUser, conn: Db) -> Response:
    await service.delete_social_account(conn, user, str(account_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/verification", response_model=list[VerificationOut])
async def list_own_verifications(
    user: SmeUser, conn: Db, storage: Storage
) -> list[VerificationOut]:
    return await service.list_own_verifications(conn, storage, user)


@router.post(
    "/me/verification",
    response_model=VerificationOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[UPLOAD_LIMIT],
)
async def submit_verification(
    user: SmeUser,
    conn: Db,
    storage: Storage,
    business_reg_number: Annotated[str, Form(pattern=r"^[A-Za-z0-9/ -]{3,40}$")],
    registered_name: Annotated[str, Form(min_length=2, max_length=160)],
    documents: Annotated[list[UploadFile], File()],
) -> VerificationOut:
    if not 1 <= len(documents) <= service.MAX_VERIFICATION_DOCUMENTS:
        raise ValidationAppError(
            f"Attach between 1 and {service.MAX_VERIFICATION_DOCUMENTS} documents",
            code="document_count",
        )
    # Validate every file before storing any of them.
    files = [
        await read_upload(doc, allowed=DOCUMENT_KINDS, max_bytes=MAX_DOCUMENT_BYTES)
        for doc in documents
    ]
    return await service.submit_verification(
        conn,
        storage,
        user,
        business_reg_number=business_reg_number.strip(),
        registered_name=registered_name.strip(),
        files=files,
    )


# --- Public storefront ---------------------------------------------------------------
public_router = APIRouter(prefix="/stores", tags=["stores"])


@public_router.get("/{slug}", response_model=PublicStoreOut)
async def read_public_store(
    slug: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{3,40}$")],
    conn: Annotated[AsyncConnection, Depends(get_anon_db)],
    storage: Storage,
) -> PublicStoreOut:
    return await service.get_public_store(conn, storage, slug)


# --- Admin ------------------------------------------------------------------------------
admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/verifications", response_model=list[AdminVerificationListItem])
async def admin_list_verifications(
    _: AdminUser,
    conn: Db,
    status_filter: Annotated[
        Literal["SUBMITTED", "APPROVED", "REJECTED"] | None, Query(alias="status")
    ] = "SUBMITTED",
) -> list[AdminVerificationListItem]:
    return await admin_service.list_verifications(conn, status_filter)


@admin_router.get("/verifications/{verification_id}", response_model=AdminVerificationDetail)
async def admin_get_verification(
    verification_id: UUID, _: AdminUser, conn: Db, storage: Storage
) -> AdminVerificationDetail:
    return await admin_service.get_verification(conn, storage, str(verification_id))


@admin_router.post(
    "/verifications/{verification_id}/decision", response_model=AdminVerificationDetail
)
async def admin_decide_verification(
    verification_id: UUID,
    decision: VerificationDecisionIn,
    admin: AdminUser,
    conn: Db,
    storage: Storage,
) -> AdminVerificationDetail:
    return await admin_service.decide_verification(
        conn, storage, admin, str(verification_id), decision
    )


@admin_router.get("/social-accounts", response_model=list[AdminSocialAccountItem])
async def admin_list_social_accounts(
    _: AdminUser, conn: Db, pending: bool = True
) -> list[AdminSocialAccountItem]:
    return await admin_service.list_social_accounts(conn, pending_only=pending)


@admin_router.post("/social-accounts/{account_id}/decision", response_model=AdminSocialAccountItem)
async def admin_decide_social_account(
    account_id: UUID, decision: SocialDecisionIn, admin: AdminUser, conn: Db
) -> AdminSocialAccountItem:
    return await admin_service.decide_social_account(conn, admin, str(account_id), decision)
