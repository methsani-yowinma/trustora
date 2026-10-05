"""Append-only audit trail. Call inside the same transaction as the action being recorded.

Clients cannot write audit_logs (no grant to anon/authenticated), so the insert runs
privileged even when called from an RLS-scoped user transaction.
Never put secrets, tokens or full documents in ``metadata``.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.models import CurrentUser
from app.core.db import Database


async def record(
    conn: AsyncConnection,
    *,
    actor: CurrentUser | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    async with Database.privileged(conn):
        await _insert(conn, actor, action, target_type, target_id, metadata)


async def _insert(
    conn: AsyncConnection,
    actor: CurrentUser | None,
    action: str,
    target_type: str,
    target_id: str | None,
    metadata: dict[str, Any] | None,
) -> None:
    await conn.execute(
        text(
            "insert into public.audit_logs "
            "(actor_id, actor_role, action, target_type, target_id, metadata) "
            "values (:actor_id, cast(:actor_role as public.user_role), :action, "
            ":target_type, :target_id, cast(:metadata as jsonb))"
        ),
        {
            "actor_id": actor.id if actor else None,
            "actor_role": actor.role.value if actor else None,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "metadata": json.dumps(metadata or {}, default=str),
        },
    )
