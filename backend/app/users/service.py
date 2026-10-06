from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.errors import NotFoundError
from app.users.schemas import ProfileOut, ProfileUpdate

_PROFILE_COLUMNS = "id, role, status, full_name, phone, preferred_locale, created_at"


async def get_profile(conn: AsyncConnection, user: CurrentUser) -> ProfileOut:
    row = (
        (
            await conn.execute(
                text(f"select {_PROFILE_COLUMNS} from public.profiles where id = :id"),  # noqa: S608
                {"id": user.id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Profile not found")
    return ProfileOut(**{**row, "id": str(row["id"]), "email": user.email})


async def update_profile(
    conn: AsyncConnection, user: CurrentUser, changes: ProfileUpdate
) -> ProfileOut:
    # Column names come only from the ProfileUpdate model, never from client keys.
    values = changes.model_dump(exclude_unset=True)
    if values:
        assignments = ", ".join(f"{column} = :{column}" for column in values)
        await conn.execute(
            text(f"update public.profiles set {assignments} where id = :id"),  # noqa: S608
            {**values, "id": user.id},
        )
        # Which fields changed, never their values (personal data stays out of the audit trail).
        await audit.record(conn, actor=user, action="profile.updated", target_type="profile",
                           target_id=user.id, metadata={"fields": sorted(values)})  # fmt: skip
    return await get_profile(conn, user)
