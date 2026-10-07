"""Persistence of AI analyses (privileged writes; admins read)."""

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.ai.output import AiAnalysisOut
from app.core.db import Database


async def save(
    conn: AsyncConnection,
    *,
    kind: str,
    target_id: str,
    sme_id: str,
    model: str,
    prompt_version: str,
    status: str,
    output: dict[str, Any] | None = None,
    error_code: str | None = None,
    locale: str | None = None,
    input_hash: str | None = None,
) -> str:
    async with Database.privileged(conn):
        return str(
            (
                await conn.execute(
                    text(
                        "insert into public.ai_analyses (kind, target_id, sme_id, locale, input_hash, model, "
                        "prompt_version, status, output, error_code) values "
                        "(cast(:kind as public.ai_analysis_kind), :target, :sme, :locale, :hash, :model, :version, "
                        "cast(:status as public.ai_analysis_status), cast(:output as jsonb), :error) returning id"
                    ),
                    {
                        "kind": kind, "target": target_id, "sme": sme_id, "locale": locale, "hash": input_hash,
                        "model": model, "version": prompt_version, "status": status,
                        "output": json.dumps(output) if output is not None else None, "error": error_code,
                    },
                )
            ).scalar_one()
        )  # fmt: skip


def to_out(row: Mapping[str, Any]) -> AiAnalysisOut:
    output = row["output"]
    checks = None
    if row["kind"] == "DOCUMENT" and output:
        # Documents store the model's extraction and Trustora's own checks side by side.
        output, checks = output.get("extraction"), output.get("checks")
    return AiAnalysisOut(
        id=str(row["id"]),
        kind=row["kind"],
        status=row["status"],
        model=row["model"],
        output=output,
        checks=checks,
        error_code=row["error_code"],
        created_at=row["created_at"],
    )


async def latest(
    conn: AsyncConnection, kind: str, target_ids: list[str]
) -> dict[str, Mapping[str, Any]]:
    """Latest analysis per target. Caller must be authorized (admin) — reads run privileged."""
    if not target_ids:
        return {}
    async with Database.privileged(conn):
        rows = (
            (
                await conn.execute(
                    text(
                        "select distinct on (target_id) id, kind, target_id, status, model, output, error_code, "
                        "created_at from public.ai_analyses where kind = cast(:kind as public.ai_analysis_kind) "
                        "and target_id in :ids order by target_id, created_at desc"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"kind": kind, "ids": target_ids},
                )
            )
            .mappings()
            .all()
        )
    return {str(r["target_id"]): r for r in rows}
