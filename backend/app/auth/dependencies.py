"""Authentication and role-based authorization dependencies.

Every protected route resolves, per request:
  bearer token → verified claims → RLS-scoped DB transaction → active profile (role, status).
"""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.models import CurrentUser, UserRole
from app.core.db import Database
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import AuthClaims, TokenVerifier
from app.core.storage import StorageClient

_bearer = HTTPBearer(auto_error=False)


def get_database(request: Request) -> Database:
    return request.app.state.db


def get_storage(request: Request) -> StorageClient:
    return request.app.state.storage


async def get_auth_claims(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthClaims:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Authentication required")
    verifier: TokenVerifier = request.app.state.token_verifier
    return await run_in_threadpool(verifier.verify, credentials.credentials)


async def get_user_db(
    claims: AuthClaims = Depends(get_auth_claims),
    db: Database = Depends(get_database),
) -> AsyncIterator[AsyncConnection]:
    """One RLS-scoped transaction per request, committed when the route succeeds.

    Always declare it with ``scope="function"`` so the commit happens *before* the response is
    sent: commit errors reach the client, and background tasks only ever see committed data.
    """
    async with db.user_transaction(claims) as conn:
        yield conn


async def get_anon_db(db: Database = Depends(get_database)) -> AsyncIterator[AsyncConnection]:
    """Transaction for public endpoints; public RLS policies apply."""
    async with db.anon_transaction() as conn:
        yield conn


async def get_current_user(
    claims: AuthClaims = Depends(get_auth_claims),
    conn: AsyncConnection = Depends(get_user_db, scope="function"),
) -> CurrentUser:
    row = (
        (
            await conn.execute(
                text("select id, role, status from public.profiles where id = :id"),
                {"id": claims.user_id},
            )
        )
        .mappings()
        .first()
    )

    if row is None:
        raise ForbiddenError("No Trustora profile exists for this account", code="profile_missing")
    if row["status"] != "ACTIVE":
        raise ForbiddenError("This account is suspended", code="account_suspended")

    return CurrentUser(id=str(row["id"]), email=claims.email, role=UserRole(row["role"]))


def require_role(
    *allowed: UserRole,
) -> Callable[..., Coroutine[Any, Any, CurrentUser]]:
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise ForbiddenError("You do not have permission to perform this action")
        return user

    return _check


async def get_optional_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Database = Depends(get_database),
) -> tuple[CurrentUser, AuthClaims] | None:
    """For endpoints that also serve visitors. A token, if sent, must be valid and active.

    Uses its own short transaction, so long-running handlers (e.g. AI chat) hold no connection.
    """
    if credentials is None or not credentials.credentials:
        return None
    claims = await get_auth_claims(request, credentials)
    async with db.user_transaction(claims) as conn:
        user = await get_current_user(claims, conn)
    return user, claims
