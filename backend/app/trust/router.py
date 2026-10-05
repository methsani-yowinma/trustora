from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_anon_db, get_storage, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.core.storage import StorageClient
from app.trust import service
from app.trust.schemas import (
    AdminEvidenceItem,
    EvidenceReviewIn,
    HistoryOut,
    PassportOut,
    SmeTrustOut,
    TrustScoreOut,
)

Db = Annotated[AsyncConnection, Depends(get_user_db)]
AnonDb = Annotated[AsyncConnection, Depends(get_anon_db)]
Storage = Annotated[StorageClient, Depends(get_storage)]
Slug = Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{3,40}$")]

# --- Public ------------------------------------------------------------------------------
public_router = APIRouter(prefix="/stores", tags=["trust"])


@public_router.get("/{slug}/passport", response_model=PassportOut)
async def read_passport(slug: Slug, conn: AnonDb, storage: Storage) -> PassportOut:
    return await service.public_passport(conn, storage, slug)


@public_router.get("/{slug}/trust/history", response_model=HistoryOut)
async def read_history(
    slug: Slug, conn: AnonDb, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> HistoryOut:
    return await service.public_history(conn, slug, days)


# --- SME -----------------------------------------------------------------------------------
sme_router = APIRouter(prefix="/sme", tags=["trust"])


@sme_router.get("/trust", response_model=SmeTrustOut)
async def read_own_trust(
    user: Annotated[CurrentUser, Depends(require_role(UserRole.SME))], conn: Db, storage: Storage
) -> SmeTrustOut:
    return await service.own_trust(conn, storage, user)


# --- Admin -------------------------------------------------------------------------------
admin_router = APIRouter(prefix="/admin", tags=["admin"])
AdminUser = Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))]


@admin_router.get("/evidence", response_model=list[AdminEvidenceItem])
async def admin_list_evidence(
    _: AdminUser,
    conn: Db,
    storage: Storage,
    status: Literal["PENDING", "ACCEPTED", "REJECTED"] = "PENDING",
) -> list[AdminEvidenceItem]:
    return await service.admin_list_evidence(conn, storage, status)


@admin_router.post("/evidence/{evidence_id}/review", response_model=AdminEvidenceItem)
async def admin_review_evidence(
    evidence_id: UUID, review: EvidenceReviewIn, admin: AdminUser, conn: Db, storage: Storage
) -> AdminEvidenceItem:
    return await service.admin_review_evidence(conn, storage, admin, str(evidence_id), review)


@admin_router.post("/smes/{sme_id}/trust/recalculate", response_model=TrustScoreOut)
async def admin_recalculate(sme_id: UUID, admin: AdminUser, conn: Db) -> TrustScoreOut:
    return await service.admin_recalculate(conn, admin, str(sme_id))
