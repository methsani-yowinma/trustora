"""Database access.

Two kinds of transactions:

* ``user_transaction`` — runs as Postgres role ``authenticated`` with the caller's JWT
  claims, so Supabase Row Level Security applies to every query (defence in depth on top
  of service-layer authorization).
* ``system_transaction`` — runs as the connection's own (privileged) role. Only for
  trusted backend work: audit writes, trust recalculation, storage bookkeeping.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.core.security import AuthClaims


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        # Compatible with Supabase's pooler (no server-side prepared statement reuse).
        connect_args={"statement_cache_size": 0},
    )


class Database:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    @asynccontextmanager
    async def user_transaction(self, claims: AuthClaims) -> AsyncIterator[AsyncConnection]:
        jwt_claims = json.dumps(
            {"sub": claims.user_id, "role": "authenticated", "email": claims.email}
        )
        async with self.engine.begin() as conn:
            # Both settings are transaction-local (is_local = true) and reset on commit/rollback.
            await conn.execute(
                text(
                    "select set_config('request.jwt.claims', :claims, true), "
                    "set_config('role', 'authenticated', true)"
                ),
                {"claims": jwt_claims},
            )
            yield conn

    @staticmethod
    @asynccontextmanager
    async def privileged(conn: AsyncConnection) -> AsyncIterator[AsyncConnection]:
        """Temporarily leave the RLS role inside the current transaction.

        For backend-only writes that must be atomic with the user's action (e.g. audit logs).
        Authorization must already have been checked by the caller.
        """
        previous = (await conn.execute(text("select current_user"))).scalar_one()
        await conn.execute(text("set local role none"))
        try:
            yield conn
        finally:
            if previous == "authenticated":
                await conn.execute(text("set local role authenticated"))

    @asynccontextmanager
    async def system_transaction(self) -> AsyncIterator[AsyncConnection]:
        async with self.engine.begin() as conn:
            yield conn

    async def ping(self) -> bool:
        async with self.engine.connect() as conn:
            await conn.execute(text("select 1"))
        return True

    async def dispose(self) -> None:
        await self.engine.dispose()
