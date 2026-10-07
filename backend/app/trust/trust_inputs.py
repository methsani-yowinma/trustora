"""Collects TrustInputs for one SME from the database.

Runs privileged (inside the caller's transaction): trust is computed from all of an SME's
evidence, including private documents, but only aggregates and signals are ever exposed.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.trust.models import ProductEvidence, TransactionStats, TrustInputs

SOCIAL_REVIEW_SOURCE = "SOCIAL_OWNERSHIP_REVIEW"
POLICY_KEYS = ("returns", "refunds", "delivery")


async def collect_inputs(conn: AsyncConnection, sme_id: str) -> tuple[TrustInputs, dict[str, Any]]:
    """Returns the engine inputs and an aggregate evidence summary for the passport."""
    sme = (
        (
            await conn.execute(
                text(
                    "select status, verification_status, contact_verified, logo_path, "
                    "description_i18n, policies_i18n, created_at from public.smes where id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .one()
    )

    evidence_rows = (
        (
            await conn.execute(
                text(
                    "select id, type, provenance, source, product_id, verification_id, review_status, "
                    "flagged_misleading from public.evidence where sme_id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .all()
    )

    confirmed_social = (
        await conn.execute(
            text(
                "select count(*) from public.sme_social_accounts "
                "where sme_id = :id and ownership_verified"
            ),
            {"id": sme_id},
        )
    ).scalar_one()

    products = (
        (
            await conn.execute(
                text(
                    "select id, status from public.products where sme_id = :id and status <> 'REMOVED'"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .all()
    )

    upheld_authenticity = dict(
        (
            await conn.execute(
                text(
                    "select i.product_id, count(distinct c.id) from public.complaints c "
                    "join public.order_items i on i.order_id = c.order_id "
                    "where c.sme_id = :id and c.status = 'UPHELD' "
                    "and c.category = 'PRODUCT_AUTHENTICITY' group by i.product_id"
                ),
                {"id": sme_id},
            )
        ).all()
    )

    by_product: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    verification_ids, social_ids, misleading_ids = [], [], []
    for e in evidence_rows:
        eid = str(e["id"])
        if e["flagged_misleading"]:
            misleading_ids.append(eid)
        if e["type"] == "VERIFICATION_RESULT" and e["review_status"] == "ACCEPTED":
            if e["source"] == SOCIAL_REVIEW_SOURCE:
                social_ids.append(eid)
            elif e["verification_id"] is not None:
                verification_ids.append(eid)
        if e["product_id"] is not None:
            bucket = by_product[str(e["product_id"])]
            if e["flagged_misleading"]:
                bucket["misleading"].append(eid)
            elif e["review_status"] == "ACCEPTED" and e["type"] == "PRODUCT_DOCUMENT":
                bucket["documents"].append(eid)
            elif e["review_status"] == "ACCEPTED" and e["type"] == "PRODUCT_IMAGE":
                bucket["images"].append(eid)

    policies = sme["policies_i18n"] or {}
    age = datetime.now(UTC) - sme["created_at"]

    inputs = TrustInputs(
        sme_status=sme["status"],
        verification_status=sme["verification_status"],
        verification_evidence_ids=tuple(verification_ids),
        contact_verified=sme["contact_verified"],
        confirmed_social_accounts=confirmed_social,
        social_evidence_ids=tuple(social_ids),
        published_policies=tuple(k for k in POLICY_KEYS if policies.get(k)),
        has_logo=sme["logo_path"] is not None,
        has_description=bool(sme["description_i18n"]),
        account_age_days=max(0, age.days),
        misleading_evidence_ids=tuple(misleading_ids),
        products=tuple(
            ProductEvidence(
                product_id=str(p["id"]),
                accepted_document_ids=tuple(by_product[str(p["id"])]["documents"]),
                accepted_image_ids=tuple(by_product[str(p["id"])]["images"]),
                misleading_ids=tuple(by_product[str(p["id"])]["misleading"]),
                upheld_authenticity_complaints=upheld_authenticity.get(p["id"], 0),
                active=p["status"] == "ACTIVE",
            )
            for p in products
        ),
        transactions=await _transaction_stats(conn, sme_id),
    )
    return inputs, _evidence_summary(evidence_rows)


async def _transaction_stats(conn: AsyncConnection, sme_id: str) -> TransactionStats:
    """Order, delivery, complaint and verified-review outcomes."""
    row = (
        (
            await conn.execute(
                text(
                    "select "
                    "count(*) filter (where o.status in ('DELIVERED', 'COMPLETED')) as completed, "
                    "count(*) filter (where o.status = 'DELIVERY_FAILED') as failed, "
                    "count(*) filter (where o.status = 'CANCELLED' and o.cancelled_by = 'SME') as seller_cancelled, "
                    "count(*) filter (where d.delivered_at is not null and "
                    "  ((d.delivered_at + interval '5 hours 30 minutes') at time zone 'UTC')::date "
                    "  > d.estimated_delivery_date) as late "  # Sri Lanka time: fixed UTC+05:30
                    "from public.orders o join public.deliveries d on d.order_id = o.id "
                    "where o.sme_id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .one()
    )
    complaints = (
        (
            await conn.execute(
                text(
                    "select "
                    "count(*) filter (where status = 'UPHELD') as upheld, "
                    "count(*) filter (where status = 'UPHELD' and decided_at > now() - interval '90 days') "
                    "  as upheld_90d, "
                    # No seller response within 14 days.
                    "count(*) filter (where status = 'SUBMITTED' and created_at < now() - interval '14 days') "
                    "  as overdue, "
                    "count(*) filter (where status in ('SUBMITTED', 'SME_RESPONDED', 'UNDER_REVIEW')) as open "
                    "from public.complaints where sme_id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .one()
    )
    reviews = (
        (
            await conn.execute(
                text(
                    "select count(*) as n, avg(rating)::float as average from public.reviews where sme_id = :id"
                ),
                {"id": sme_id},
            )
        )
        .mappings()
        .one()
    )
    return TransactionStats(
        completed_orders=row["completed"],
        failed_deliveries=row["failed"],
        late_deliveries=row["late"],
        seller_cancellations=row["seller_cancelled"],
        upheld_complaints=complaints["upheld"],
        upheld_complaints_90d=complaints["upheld_90d"],
        overdue_unresolved_complaints=complaints["overdue"],
        open_complaints=complaints["open"],
        verified_review_count=reviews["n"],
        verified_review_average=reviews["average"],
    )


def _evidence_summary(rows: Any) -> dict[str, Any]:
    """Counts only — safe to show publicly."""
    by_provenance: dict[str, int] = defaultdict(int)
    by_review: dict[str, int] = defaultdict(int)
    for row in rows:
        by_review[row["review_status"]] += 1
        if row["review_status"] != "REJECTED":
            by_provenance[row["provenance"]] += 1
    return {
        "total": len(rows),
        "accepted": by_review["ACCEPTED"],
        "pending": by_review["PENDING"],
        "rejected": by_review["REJECTED"],
        "by_provenance": dict(by_provenance),
    }
