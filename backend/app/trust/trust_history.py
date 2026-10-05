"""Trust score history: time series and "changed from X to Y over N days" summaries."""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.trust.schemas import HistoryChange, HistoryOut, HistoryPoint


async def load_history(conn: AsyncConnection, sme_id: str, days: int) -> HistoryOut:
    """RLS applies: callers only see history of stores they are allowed to see."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        (
            await conn.execute(
                text(
                    "select overall_score, level, created_at from public.trust_score_history "
                    "where sme_id = :id and created_at >= :since order by created_at"
                ),
                {"id": sme_id, "since": since},
            )
        )
        .mappings()
        .all()
    )
    # The last score before the window is the baseline the window's changes start from.
    baseline = (
        (
            await conn.execute(
                text(
                    "select overall_score, level, created_at from public.trust_score_history "
                    "where sme_id = :id and created_at < :since order by created_at desc limit 1"
                ),
                {"id": sme_id, "since": since},
            )
        )
        .mappings()
        .first()
    )
    return summarize(rows, baseline, days)


def summarize(rows: Any, baseline: Any, days: int) -> HistoryOut:
    points = [
        HistoryPoint(at=r["created_at"], overall_score=r["overall_score"], level=r["level"])
        for r in rows
    ]
    # Start = score in effect when the window opened (or the first score inside it).
    start = baseline or (rows[0] if rows else None)
    end = rows[-1] if rows else baseline
    change = None
    if start is not None and end is not None:
        change = HistoryChange(
            from_score=start["overall_score"],
            to_score=end["overall_score"],
            from_level=start["level"],
            to_level=end["level"],
            days=days,
        )
    return HistoryOut(
        days=days,
        baseline=HistoryPoint(
            at=baseline["created_at"],
            overall_score=baseline["overall_score"],
            level=baseline["level"],
        )
        if baseline
        else None,
        points=points,
        change=change,
    )
