"""Database-level security: what a browser could do directly through Supabase's REST API
with the anon key or a user's JWT. These must hold even if the backend is bypassed."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.audit import service as audit
from app.auth.models import CurrentUser, UserRole
from app.core.db import Database
from app.core.security import AuthClaims


@asynccontextmanager
async def as_role(
    engine: AsyncEngine, role: str, user_id: str | None = None, *, via_api: bool = True
) -> AsyncIterator[AsyncConnection]:
    """A transaction as `role`, like the backend's (default) or a direct Data API client."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        claims = json.dumps({"sub": user_id, "role": role}) if user_id else ""
        await conn.execute(
            text(
                "select set_config('request.jwt.claims', :c, true), "
                "set_config('trustora.api', :api, true), set_config('role', :r, true)"
            ),
            {"c": claims, "r": role, "api": "on" if via_api else ""},
        )
        try:
            yield conn
        finally:
            await trans.rollback()


async def _visible_profile_ids(conn: AsyncConnection) -> set[str]:
    rows = (await conn.execute(text("select id from public.profiles"))).scalars().all()
    return {str(r) for r in rows}


async def test_user_sees_only_own_profile(engine: AsyncEngine, create_user: Any) -> None:
    alice, bob = await create_user(), await create_user()
    async with as_role(engine, "authenticated", alice.id) as conn:
        visible = await _visible_profile_ids(conn)
    assert alice.id in visible
    assert bob.id not in visible


async def test_admin_sees_all_profiles(engine: AsyncEngine, create_user: Any) -> None:
    admin, other = await create_user(role="ADMIN"), await create_user()
    async with as_role(engine, "authenticated", admin.id) as conn:
        visible = await _visible_profile_ids(conn)
    assert {admin.id, other.id} <= visible


async def test_suspended_admin_loses_admin_visibility(
    engine: AsyncEngine, create_user: Any
) -> None:
    admin = await create_user(role="ADMIN", status="SUSPENDED")
    other = await create_user()
    async with as_role(engine, "authenticated", admin.id) as conn:
        assert other.id not in await _visible_profile_ids(conn)


async def test_anon_cannot_read_profiles(engine: AsyncEngine, create_user: Any) -> None:
    await create_user()
    async with as_role(engine, "anon") as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("select * from public.profiles"))


@pytest.mark.parametrize("assignment", ["role = 'ADMIN'", "role = 'SME'", "status = 'SUSPENDED'"])
async def test_user_cannot_change_own_role_or_status(
    engine: AsyncEngine, create_user: Any, assignment: str
) -> None:
    user = await create_user()
    async with as_role(engine, "authenticated", user.id) as conn:
        with pytest.raises(DBAPIError, match="Only administrators"):
            await conn.execute(
                text(f"update public.profiles set {assignment} where id = :id"),  # noqa: S608
                {"id": user.id},
            )


async def test_user_cannot_update_another_profile(engine: AsyncEngine, create_user: Any) -> None:
    alice, bob = await create_user(), await create_user({"full_name": "Bob"})
    async with as_role(engine, "authenticated", alice.id) as conn:
        result = await conn.execute(
            text("update public.profiles set full_name = 'hacked' where id = :id"), {"id": bob.id}
        )
        assert result.rowcount == 0


async def test_user_cannot_insert_or_delete_profiles(engine: AsyncEngine, create_user: Any) -> None:
    user = await create_user()
    async with as_role(engine, "authenticated", user.id) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("delete from public.profiles where id = :id"), {"id": user.id})
    async with as_role(engine, "authenticated", user.id) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(text("insert into public.profiles (id) values (gen_random_uuid())"))


async def test_admin_can_suspend_user(engine: AsyncEngine, create_user: Any) -> None:
    admin, target = await create_user(role="ADMIN"), await create_user()
    async with as_role(engine, "authenticated", admin.id) as conn:
        result = await conn.execute(
            text("update public.profiles set status = 'SUSPENDED' where id = :id"),
            {"id": target.id},
        )
        assert result.rowcount == 1


# --- audit_logs ----------------------------------------------------------------
async def test_clients_cannot_write_audit_logs(engine: AsyncEngine, create_user: Any) -> None:
    admin = await create_user(role="ADMIN")
    for role, uid in (("anon", None), ("authenticated", admin.id)):
        async with as_role(engine, role, uid) as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(
                    text(
                        "insert into public.audit_logs (action, target_type) "
                        "values ('fake.entry', 'x')"
                    )
                )


async def test_audit_record_from_user_transaction(
    engine: AsyncEngine, database: Database, create_user: Any
) -> None:
    user, admin = await create_user(), await create_user(role="ADMIN")
    actor = CurrentUser(id=user.id, email=None, role=UserRole.CUSTOMER)
    marker = f"target-{user.id}"

    async with database.user_transaction(AuthClaims(user.id, None, {})) as conn:
        await audit.record(
            conn,
            actor=actor,
            action="profile.updated",
            target_type="profile",
            target_id=marker,
            metadata={"fields": ["full_name"]},
        )
        # RLS role is restored after the privileged insert.
        assert (await conn.execute(text("select current_user"))).scalar_one() == "authenticated"

    # Regular users cannot read audit logs; admins can.
    async with as_role(engine, "authenticated", user.id) as conn:
        count = await conn.execute(
            text("select count(*) from public.audit_logs where target_id = :t"), {"t": marker}
        )
        assert count.scalar_one() == 0
    async with as_role(engine, "authenticated", admin.id) as conn:
        row = (
            await conn.execute(
                text(
                    "select actor_role, action, metadata from public.audit_logs where target_id = :t"
                ),
                {"t": marker},
            )
        ).one()
        assert row.actor_role == "CUSTOMER"
        assert row.action == "profile.updated"
        assert row.metadata == {"fields": ["full_name"]}


async def test_audit_logs_are_append_only_even_for_privileged_role(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into public.audit_logs (action, target_type) values ('test.entry', 'x')")
        )
    for statement in (
        "update public.audit_logs set action = 'x.y'",
        "delete from public.audit_logs",
    ):
        async with engine.begin() as conn:
            with pytest.raises(DBAPIError, match="append-only"):
                await conn.execute(text(statement))
