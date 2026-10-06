from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_anon_db, get_storage, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.complaints import service
from app.complaints.schemas import (
    ComplaintCategory,
    ComplaintDecisionIn,
    ComplaintOut,
    ComplaintStatus,
    ComplaintSummaryItem,
    Description,
    PublicComplaintSummary,
    SmeResponseIn,
)
from app.core.errors import ValidationAppError
from app.core.rate_limit import rate_limit
from app.core.storage import StorageClient
from app.core.uploads import DOCUMENT_KINDS, MAX_DOCUMENT_BYTES, ValidatedFile, read_upload

MAX_FILES_PER_UPLOAD = 3
UPLOAD_LIMIT = Depends(rate_limit("30/minute", scope="uploads"))

Db = Annotated[AsyncConnection, Depends(get_user_db)]
AnonDb = Annotated[AsyncConnection, Depends(get_anon_db)]
Storage = Annotated[StorageClient, Depends(get_storage)]
Customer = Annotated[CurrentUser, Depends(require_role(UserRole.CUSTOMER))]
Sme = Annotated[CurrentUser, Depends(require_role(UserRole.SME))]
Admin = Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))]
EvidenceNote = Annotated[str | None, Form(max_length=500)]


async def _read_files(
    files: list[UploadFile] | None, *, required: bool = False
) -> list[ValidatedFile]:
    files = files or []
    if len(files) > MAX_FILES_PER_UPLOAD or (required and not files):
        raise ValidationAppError(
            f"Attach up to {MAX_FILES_PER_UPLOAD} files", code="document_count"
        )
    return [
        await read_upload(f, allowed=DOCUMENT_KINDS, max_bytes=MAX_DOCUMENT_BYTES) for f in files
    ]


# --- Customer ----------------------------------------------------------------------------------
router = APIRouter(tags=["complaints"])


@router.post(
    "/orders/{order_id}/complaints",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[UPLOAD_LIMIT],
)
async def create_complaint(
    order_id: UUID,
    user: Customer,
    conn: Db,
    storage: Storage,
    category: Annotated[ComplaintCategory, Form()],
    description: Annotated[Description, Form()],
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> ComplaintOut:
    validated = await _read_files(files)
    return await service.create(
        conn,
        storage,
        user,
        str(order_id),
        category=category,
        description=description,
        files=validated,
    )


@router.get("/complaints", response_model=list[ComplaintSummaryItem])
async def list_my_complaints(user: Customer, conn: Db) -> list[ComplaintSummaryItem]:
    return await service.list_for_customer(conn, user)


@router.get("/complaints/{complaint_id}", response_model=ComplaintOut)
async def get_my_complaint(
    complaint_id: UUID, user: Customer, conn: Db, storage: Storage
) -> ComplaintOut:
    return await service.get_for_customer(conn, storage, user, str(complaint_id))


@router.post("/complaints/{complaint_id}/resolve", response_model=ComplaintOut)
async def resolve(complaint_id: UUID, user: Customer, conn: Db, storage: Storage) -> ComplaintOut:
    """The customer is satisfied with the outcome."""
    return await service.customer_transition(conn, storage, user, str(complaint_id), "resolve")


@router.post("/complaints/{complaint_id}/escalate", response_model=ComplaintOut)
async def escalate(complaint_id: UUID, user: Customer, conn: Db, storage: Storage) -> ComplaintOut:
    """Ask Trustora to review the complaint."""
    return await service.customer_transition(conn, storage, user, str(complaint_id), "escalate")


@router.post(
    "/complaints/{complaint_id}/evidence", response_model=ComplaintOut, dependencies=[UPLOAD_LIMIT]
)
async def customer_add_evidence(
    complaint_id: UUID,
    user: Customer,
    conn: Db,
    storage: Storage,
    files: Annotated[list[UploadFile], File()],
    description: EvidenceNote = None,
) -> ComplaintOut:
    validated = await _read_files(files, required=True)
    return await service.customer_add_evidence(
        conn, storage, user, str(complaint_id), validated, description
    )


# --- Public ------------------------------------------------------------------------------------
public_router = APIRouter(tags=["stores"])


@public_router.get("/stores/{slug}/complaints/summary", response_model=PublicComplaintSummary)
async def complaint_summary(
    slug: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{3,40}$")], conn: AnonDb
) -> PublicComplaintSummary:
    return await service.public_summary(conn, slug)


# --- SME ----------------------------------------------------------------------------------------
sme_router = APIRouter(prefix="/sme/complaints", tags=["sme-complaints"])


@sme_router.get("", response_model=list[ComplaintSummaryItem])
async def sme_list(
    user: Sme, conn: Db, status: ComplaintStatus | None = None
) -> list[ComplaintSummaryItem]:
    return await service.list_for_sme(conn, user, status)


@sme_router.get("/{complaint_id}", response_model=ComplaintOut)
async def sme_get(complaint_id: UUID, user: Sme, conn: Db, storage: Storage) -> ComplaintOut:
    return await service.get_for_sme(conn, storage, user, str(complaint_id))


@sme_router.post("/{complaint_id}/response", response_model=ComplaintOut)
async def sme_respond(
    complaint_id: UUID, body: SmeResponseIn, user: Sme, conn: Db, storage: Storage
) -> ComplaintOut:
    return await service.sme_respond(conn, storage, user, str(complaint_id), body.response)


@sme_router.post(
    "/{complaint_id}/evidence", response_model=ComplaintOut, dependencies=[UPLOAD_LIMIT]
)
async def sme_add_evidence(
    complaint_id: UUID,
    user: Sme,
    conn: Db,
    storage: Storage,
    files: Annotated[list[UploadFile], File()],
    description: EvidenceNote = None,
) -> ComplaintOut:
    validated = await _read_files(files, required=True)
    return await service.sme_add_evidence(
        conn, storage, user, str(complaint_id), validated, description
    )


# --- Admin ------------------------------------------------------------------------------------
admin_router = APIRouter(prefix="/admin/complaints", tags=["admin"])


@admin_router.get("", response_model=list[ComplaintSummaryItem])
async def admin_list(
    _: Admin, conn: Db, status: ComplaintStatus | None = "UNDER_REVIEW"
) -> list[ComplaintSummaryItem]:
    return await service.list_for_admin(conn, status)


@admin_router.get("/{complaint_id}", response_model=ComplaintOut)
async def admin_get(complaint_id: UUID, _: Admin, conn: Db, storage: Storage) -> ComplaintOut:
    return await service.get_for_admin(conn, storage, str(complaint_id))


@admin_router.post("/{complaint_id}/decision", response_model=ComplaintOut)
async def admin_decide(
    complaint_id: UUID, decision: ComplaintDecisionIn, admin: Admin, conn: Db, storage: Storage
) -> ComplaintOut:
    return await service.admin_decide(conn, storage, admin, str(complaint_id), decision)
