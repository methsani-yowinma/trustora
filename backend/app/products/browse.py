"""Public product and store browsing. Runs as Postgres role ``anon``: RLS limits results to ACTIVE
products of published, active stores, and trust data of public stores."""

from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.errors import NotFoundError
from app.core.storage import PUBLIC_BUCKET, StorageClient
from app.products.schemas import (
    ProductCard,
    ProductImageOut,
    ProductPage,
    PublicProductDetail,
    StoreBadge,
    StoreCard,
    StorePage,
)

ProductSort = Literal["newest", "price_asc", "price_desc", "trust"]
MAX_QUANTITY_PER_LINE = 10

_ORDER_BY: dict[str, str] = {
    "newest": "p.created_at desc",
    "price_asc": "p.price_lkr asc, p.created_at desc",
    "price_desc": "p.price_lkr desc, p.created_at desc",
    "trust": "coalesce(t.overall_score, 0) desc, p.created_at desc",
}


def _like(term: str) -> str:
    """ILIKE pattern with user wildcards escaped."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _badge(row: Any) -> StoreBadge:
    return StoreBadge(
        id=str(row["sme_id"]),
        slug=row["store_slug"],
        name=row["store_name"],
        verification_status=row["verification_status"],
        trust_level=row["trust_level"],
        trust_score=row["trust_score"],
    )


_PRODUCT_FROM = (
    "from public.products p join public.smes s on s.id = p.sme_id "
    "left join public.trust_scores t on t.sme_id = s.id "
)
_PRODUCT_COLUMNS = (
    "p.id, p.category_id, p.name_i18n, p.description_i18n, p.price_lkr, p.stock, "
    "p.authenticity_status, p.sme_id, s.slug as store_slug, s.name as store_name, "
    "s.verification_status, t.level as trust_level, t.overall_score as trust_score, "
    "(select storage_path from public.product_images i where i.product_id = p.id "
    " order by sort_order limit 1) as image_path "
)


async def search_products(
    conn: AsyncConnection,
    storage: StorageClient,
    *,
    q: str | None,
    category_id: int | None,
    verified_only: bool,
    store_slug: str | None,
    sort: ProductSort,
    page: int,
    page_size: int,
) -> ProductPage:
    conditions = ["p.status = 'ACTIVE'"]
    params: dict[str, Any] = {}
    if q:
        conditions.append(
            "((p.name_i18n ->> 'en') ilike :q or (p.name_i18n ->> 'si') ilike :q or s.name ilike :q)"
        )
        params["q"] = _like(q)
    if category_id:
        conditions.append("p.category_id = :category")
        params["category"] = category_id
    if verified_only:
        conditions.append("p.authenticity_status in ('VERIFIED', 'PARTIALLY_VERIFIED')")
    if store_slug:
        conditions.append("s.slug = :store")
        params["store"] = store_slug.lower()
    where = "where " + " and ".join(conditions) + " "

    total = (
        await conn.execute(text("select count(*) " + _PRODUCT_FROM + where), params)
    ).scalar_one()  # noqa: S608
    rows = (
        (
            await conn.execute(
                text(
                    "select "
                    + _PRODUCT_COLUMNS
                    + _PRODUCT_FROM
                    + where  # noqa: S608 — fixed fragments
                    + f"order by {_ORDER_BY[sort]} limit :limit offset :offset"
                ),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
        )
        .mappings()
        .all()
    )

    return ProductPage(
        items=[
            ProductCard(
                id=str(r["id"]),
                category_id=r["category_id"],
                name_i18n=r["name_i18n"],
                price_lkr=r["price_lkr"],
                in_stock=r["stock"] > 0,
                authenticity_status=r["authenticity_status"],
                image_url=storage.public_url(PUBLIC_BUCKET, r["image_path"])
                if r["image_path"]
                else None,
                store=_badge(r),
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get_product(
    conn: AsyncConnection, storage: StorageClient, product_id: str
) -> PublicProductDetail:
    row = (
        (
            await conn.execute(
                text(
                    "select "
                    + _PRODUCT_COLUMNS
                    + _PRODUCT_FROM
                    + "where p.id = :id and p.status = 'ACTIVE'"
                ),  # noqa: S608
                {"id": product_id},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise NotFoundError("Product not found")
    images = (
        (
            await conn.execute(
                text(
                    "select id, storage_path, sort_order from public.product_images "
                    "where product_id = :id order by sort_order, created_at"
                ),
                {"id": product_id},
            )
        )
        .mappings()
        .all()
    )
    return PublicProductDetail(
        id=str(row["id"]),
        category_id=row["category_id"],
        name_i18n=row["name_i18n"],
        description_i18n=row["description_i18n"],
        price_lkr=row["price_lkr"],
        in_stock=row["stock"] > 0,
        authenticity_status=row["authenticity_status"],
        images=[
            ProductImageOut(
                id=str(i["id"]),
                url=storage.public_url(PUBLIC_BUCKET, i["storage_path"]),
                sort_order=i["sort_order"],
            )
            for i in images
        ],
        store=_badge(row),
        # Lets the UI cap quantity without revealing exact stock beyond the per-line limit.
        max_quantity=min(row["stock"], MAX_QUANTITY_PER_LINE),
    )


_STORE_COLUMNS = (
    "s.id, s.slug, s.name, s.logo_path, s.description_i18n, s.verification_status, "
    "t.level as trust_level, t.overall_score as trust_score, "
    "(select count(*) from public.products p where p.sme_id = s.id and p.status = 'ACTIVE') "
    "as product_count "
)


async def list_stores(
    conn: AsyncConnection,
    storage: StorageClient,
    *,
    q: str | None,
    verified_only: bool,
    page: int,
    page_size: int,
) -> StorePage:
    conditions = ["true"]
    params: dict[str, Any] = {}
    if q:
        conditions.append("s.name ilike :q")
        params["q"] = _like(q)
    if verified_only:
        conditions.append("s.verification_status = 'VERIFIED'")
    where = "where " + " and ".join(conditions) + " "
    base = "from public.smes s left join public.trust_scores t on t.sme_id = s.id "

    total = (await conn.execute(text("select count(*) " + base + where), params)).scalar_one()  # noqa: S608
    order = (
        "order by coalesce(t.overall_score, 0) desc, s.created_at desc limit :limit offset :offset"
    )
    sql = "select " + _STORE_COLUMNS + base + where + order  # noqa: S608 — fixed fragments only
    rows = (
        (
            await conn.execute(
                text(sql), {**params, "limit": page_size, "offset": (page - 1) * page_size}
            )
        )
        .mappings()
        .all()
    )
    return StorePage(
        items=[
            StoreCard(
                id=str(r["id"]),
                slug=r["slug"],
                name=r["name"],
                logo_url=storage.public_url(PUBLIC_BUCKET, r["logo_path"])
                if r["logo_path"]
                else None,
                description_i18n=r["description_i18n"],
                verification_status=r["verification_status"],
                trust_level=r["trust_level"],
                trust_score=r["trust_score"],
                product_count=r["product_count"],
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
