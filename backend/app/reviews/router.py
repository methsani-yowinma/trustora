from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_anon_db, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.reviews import service
from app.reviews.schemas import ReviewCreate, ReviewOut, ReviewPage, ReviewResponseIn, SmeReviewOut

Db = Annotated[AsyncConnection, Depends(get_user_db)]
AnonDb = Annotated[AsyncConnection, Depends(get_anon_db)]

router = APIRouter(tags=["reviews"])


@router.post(
    "/orders/{order_id}/review", response_model=ReviewOut, status_code=status.HTTP_201_CREATED
)
async def create_review(
    order_id: UUID,
    data: ReviewCreate,
    user: Annotated[CurrentUser, Depends(require_role(UserRole.CUSTOMER))],
    conn: Db,
) -> ReviewOut:
    return await service.create_review(conn, user, str(order_id), data)


@router.get("/stores/{slug}/reviews", response_model=ReviewPage)
async def public_reviews(
    slug: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{3,40}$")],
    conn: AnonDb,
    page: Annotated[int, Query(ge=1, le=500)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ReviewPage:
    return await service.public_reviews(conn, slug, page, page_size)


sme_router = APIRouter(prefix="/sme/reviews", tags=["sme-reviews"])
Sme = Annotated[CurrentUser, Depends(require_role(UserRole.SME))]


@sme_router.get("", response_model=list[SmeReviewOut])
async def sme_reviews(user: Sme, conn: Db) -> list[SmeReviewOut]:
    return await service.sme_reviews(conn, user)


@sme_router.post("/{review_id}/response", response_model=SmeReviewOut)
async def respond(review_id: UUID, body: ReviewResponseIn, user: Sme, conn: Db) -> SmeReviewOut:
    return await service.respond(conn, user, str(review_id), body.response)
