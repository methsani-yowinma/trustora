"""Trust engine orchestration: inputs → rules → calculation → persistence → history → audit.

``recalculate`` is called by the services whose changes affect trust (verification, social
accounts, storefront, products, evidence review). It runs inside the caller's transaction so a
score is never out of step with the change that caused it. Gemini is not involved.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.db import Database
from app.trust.models import TrustResult
from app.trust.trust_calculator import calculate
from app.trust.trust_inputs import collect_inputs

_SCORE_FIELDS = (
    "overall_score",
    "level",
    "business_score",
    "product_score",
    "transaction_score",
    "rules_version",
)
_SELECT_PREVIOUS = (
    "select overall_score, level, business_score, product_score, transaction_score, "
    "rules_version from public.trust_scores where sme_id = :id"
)


def _score_row(result: TrustResult) -> dict[str, Any]:
    return {
        "overall_score": result.overall,
        "level": result.level,
        "business_score": result.business.score,
        "product_score": result.product.score,
        "transaction_score": result.transaction.score,
        "rules_version": result.rules_version,
    }


async def recalculate(
    conn: AsyncConnection, sme_id: str, *, trigger: str, actor: CurrentUser | None = None
) -> TrustResult:
    async with Database.privileged(conn):
        # Serialize recalculations per SME (e.g. two first views of a passport at once), so the
        # second sees the first's result and history never records the same change twice.
        await conn.execute(
            text("select 1 from public.smes where id = :id for update"), {"id": sme_id}
        )
        previous = (await conn.execute(text(_SELECT_PREVIOUS), {"id": sme_id})).mappings().first()
        inputs, evidence_summary = await collect_inputs(conn, sme_id)
        result = calculate(inputs)
        authenticity_changes = await _sync_product_authenticity(conn, sme_id, result)
        row = _score_row(result)

        await conn.execute(
            text(
                "insert into public.trust_scores (sme_id, overall_score, level, business_score, "
                "product_score, transaction_score, rules_version, evidence_summary, computed_at) "
                "values (:id, :overall_score, cast(:level as public.trust_level), :business_score, "
                ":product_score, :transaction_score, :rules_version, cast(:summary as jsonb), now()) "
                "on conflict (sme_id) do update set overall_score = excluded.overall_score, "
                "level = excluded.level, business_score = excluded.business_score, "
                "product_score = excluded.product_score, "
                "transaction_score = excluded.transaction_score, "
                "rules_version = excluded.rules_version, "
                "evidence_summary = excluded.evidence_summary, computed_at = excluded.computed_at"
            ),
            {**row, "id": sme_id, "summary": json.dumps(evidence_summary)},
        )

        await conn.execute(
            text("delete from public.trust_signals where sme_id = :id"), {"id": sme_id}
        )
        if result.signals:
            await conn.execute(
                text(
                    "insert into public.trust_signals (sme_id, dimension, kind, code, points, "
                    "provenance, params, evidence_ids) values (:id, "
                    "cast(:dimension as public.trust_dimension), "
                    "cast(:kind as public.trust_signal_kind), :code, :points, "
                    "cast(:provenance as public.evidence_provenance), cast(:params as jsonb), "
                    "cast(:evidence_ids as uuid[]))"
                ),
                [
                    {
                        "id": sme_id,
                        "dimension": s.dimension,
                        "kind": s.kind,
                        "code": s.code,
                        "points": s.points,
                        "provenance": s.provenance,
                        "params": json.dumps(s.params),
                        "evidence_ids": list(s.evidence_ids),
                    }
                    for s in result.signals
                ],
            )

        changed = previous is None or any(previous[f] != row[f] for f in _SCORE_FIELDS)
        if changed:
            await conn.execute(
                text(
                    "insert into public.trust_score_history (sme_id, overall_score, level, "
                    "business_score, product_score, transaction_score, rules_version, trigger) "
                    "values (:id, :overall_score, cast(:level as public.trust_level), "
                    ":business_score, :product_score, :transaction_score, :rules_version, :trigger)"
                ),
                {**row, "id": sme_id, "trigger": trigger[:60]},
            )

    if changed:
        await audit.record(
            conn,
            actor=actor,
            action="trust.score_changed",
            target_type="sme",
            target_id=sme_id,
            metadata={
                "trigger": trigger,
                "from": {k: previous[k] for k in ("overall_score", "level")} if previous else None,
                "to": {"overall_score": result.overall, "level": result.level},
                "rules_version": result.rules_version,
            },
        )
    for product_id, (old, new) in authenticity_changes.items():
        await audit.record(
            conn,
            actor=actor,
            action="product.authenticity_changed",
            target_type="product",
            target_id=product_id,
            metadata={"from": old, "to": new, "trigger": trigger},
        )
    return result


async def _sync_product_authenticity(
    conn: AsyncConnection, sme_id: str, result: TrustResult
) -> dict[str, tuple[str, str]]:
    """Writes derived authenticity statuses; returns {product_id: (old, new)} for changes."""
    current = {
        str(r["id"]): r["authenticity_status"]
        for r in (
            await conn.execute(
                text(
                    "select id, authenticity_status from public.products "
                    "where sme_id = :id and status <> 'REMOVED'"
                ),
                {"id": sme_id},
            )
        ).mappings()
    }
    changes = {
        pid: (current[pid], status)
        for pid, status in result.product_authenticity.items()
        if current.get(pid) not in (None, status)
    }
    for pid, (_, status) in changes.items():
        await conn.execute(
            text(
                "update public.products set authenticity_status = "
                "cast(:status as public.authenticity_status) where id = :id"
            ),
            {"status": status, "id": pid},
        )
    return changes
