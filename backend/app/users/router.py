from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_current_user, get_user_db
from app.auth.models import CurrentUser
from app.users import service
from app.users.schemas import ProfileOut, ProfileUpdate

router = APIRouter(tags=["users"])


@router.get("/me", response_model=ProfileOut)
async def read_me(
    user: CurrentUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_user_db),
) -> ProfileOut:
    return await service.get_profile(conn, user)


@router.patch("/me", response_model=ProfileOut)
async def update_me(
    changes: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_user_db),
) -> ProfileOut:
    return await service.update_profile(conn, user, changes)
