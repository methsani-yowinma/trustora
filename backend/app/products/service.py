"""Product management (SME owner) and public product listing."""

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.audit import service as audit
from app.auth.models import CurrentUser
from app.core.db import Database
from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.storage import PRIVATE_BUCKET, PUBLIC_BUCKET, StorageClient, delete_quietly
from app.core.uploads import ValidatedFile
from app.evidence import service as evidence
from app.products.schemas import (
    CategoryOut,
    ProductCreate,
    ProductDetailOut,
    ProductEvidenceType,
    ProductImageOut,
    ProductOut,
    ProductUpdate,
    PublicProductOut,
)
from app.smes.service import require_own_sme

MAX_IMAGES_PER_PRODUCT = 8
MAX_EVIDENCE_PER_PRODUCT = 10

_PRODUCT_COLUMNS = (
    "id, category_id, name_i18n, description_i18n, price_lkr, stock, status, "
    "authenticity_status, created_at, updated_at"
)
_JSONB_COLUMNS = {"name_i18n", "description_i18n"}


async def list_categories(conn: AsyncConnection) -> list[CategoryOut]:
    rows = (
        (
            await conn.execute(
                text("select id, slug, name_i18n from public.categories order by sort_order")
            )
        )
        .mappings()
        .all()
    )
    return [CategoryOut(**r) for r in rows]


async def _images_by_product(
    conn: AsyncConnection, storage: StorageClient, product_ids: Sequence[Any]
) -> dict[str, list[ProductImageOut]]:
    if not product_ids:
        return {}
    rows = (
        (
            await conn.execute(
                text(
                    "select id, product_id, storage_path, sort_order from public.product_images "
                    "where product_id in :ids order by sort_order, created_at"
                ).bindparams(bindparam("ids", expanding=True)),
                {"ids": list(product_ids)},
            )
        )
        .mappings()
        .all()
    )
    grouped: dict[str, list[ProductImageOut]] = defaultdict(list)
    for r in rows:
        grouped[str(r["product_id"])].append(
            ProductImageOut(
                id=str(r["id"]),
                url=storage.public_url(PUBLIC_BUCKET, r["storage_path"]),
                sort_order=r["sort_order"],
            )
        )
    return grouped


def _product_out(row: Mapping[str, Any], images: list[ProductImageOut]) -> ProductOut:
    return ProductOut(**{**row, "id": str(row["id"]), "images": images})


async def _require_category(conn: AsyncConnection, category_id: int) -> None:
    exists = (
        await conn.execute(
            text("select 1 from public.categories where id = :id"), {"id": category_id}
        )
    ).first()
    if exists is None:
        raise ValidationAppError("Unknown category", code="unknown_category")


async def _require_own_product(
    conn: AsyncConnection, user: CurrentUser, product_id: str, *, active_sme: bool = False
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Returns (sme, product). Another SME's product is indistinguishable from a missing one."""
    sme = await require_own_sme(conn, user, active=active_sme)
    product = (
        (
            await conn.execute(
                text(
                    f"select {_PRODUCT_COLUMNS} from public.products "  # noqa: S608
                    "where id = :id and sme_id = :sme and status <> 'REMOVED'"
                ),
                {"id": product_id, "sme": sme["id"]},
            )
        )
        .mappings()
        .first()
    )
    if product is None:
        raise NotFoundError("Product not found")
    return sme, product


# --- Owner -------------------------------------------------------------------------
async def list_own_products(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser
) -> list[ProductOut]:
    sme = await require_own_sme(conn, user)
    rows = (
        (
            await conn.execute(
                text(
                    f"select {_PRODUCT_COLUMNS} from public.products "  # noqa: S608
                    "where sme_id = :sme and status <> 'REMOVED' order by created_at desc"
                ),
                {"sme": sme["id"]},
            )
        )
        .mappings()
        .all()
    )
    images = await _images_by_product(conn, storage, [r["id"] for r in rows])
    return [_product_out(r, images.get(str(r["id"]), [])) for r in rows]


async def get_own_product(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, product_id: str
) -> ProductDetailOut:
    _, product = await _require_own_product(conn, user, product_id)
    images = await _images_by_product(conn, storage, [product["id"]])
    files = await evidence.list_evidence(
        conn,
        storage,
        where="product_id = :pid",
        params={"pid": product["id"]},
        with_download_urls=True,
    )
    return ProductDetailOut(
        **_product_out(product, images.get(str(product["id"]), [])).model_dump(), evidence=files
    )


async def create_product(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, data: ProductCreate
) -> ProductDetailOut:
    sme = await require_own_sme(conn, user, active=True)
    await _require_category(conn, data.category_id)
    product_id = str(
        (
            await conn.execute(
                text(
                    "insert into public.products (sme_id, category_id, name_i18n, description_i18n, "
                    "price_lkr, stock, status) values (:sme, :category, cast(:name as jsonb), "
                    "cast(:description as jsonb), :price, :stock, "
                    "cast(:status as public.product_status)) returning id"
                ),
                {
                    "sme": sme["id"],
                    "category": data.category_id,
                    "name": json.dumps(data.name_i18n),
                    "description": json.dumps(data.description_i18n)
                    if data.description_i18n
                    else None,
                    "price": data.price_lkr,
                    "stock": data.stock,
                    "status": data.status,
                },
            )
        ).scalar_one()
    )
    await audit.record(
        conn,
        actor=user,
        action="product.created",
        target_type="product",
        target_id=product_id,
        metadata={"sme_id": str(sme["id"]), "price_lkr": str(data.price_lkr)},
    )
    return await get_own_product(conn, storage, user, product_id)


async def update_product(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    product_id: str,
    changes: ProductUpdate,
) -> ProductDetailOut:
    _, product = await _require_own_product(conn, user, product_id, active_sme=True)
    values: dict[str, Any] = {}
    for field in changes.model_fields_set:
        value = getattr(changes, field)
        values[field] = (
            json.dumps(value) if field in _JSONB_COLUMNS and value is not None else value
        )
    if "category_id" in values:
        await _require_category(conn, values["category_id"])

    if values:
        casts = {"status": "public.product_status"}
        assignments = ", ".join(
            f"{col} = cast(:{col} as jsonb)"
            if col in _JSONB_COLUMNS
            else f"{col} = cast(:{col} as {casts[col]})"
            if col in casts
            else f"{col} = :{col}"
            for col in values
        )
        await conn.execute(
            text(f"update public.products set {assignments} where id = :id"),  # noqa: S608
            {**values, "id": product["id"]},
        )
        metadata: dict[str, Any] = {"fields": sorted(values)}
        if "price_lkr" in values:
            metadata["price_lkr"] = {
                "from": str(product["price_lkr"]),
                "to": str(values["price_lkr"]),
            }
        await audit.record(
            conn,
            actor=user,
            action="product.updated",
            target_type="product",
            target_id=product_id,
            metadata=metadata,
        )
    return await get_own_product(conn, storage, user, product_id)


async def remove_product(conn: AsyncConnection, user: CurrentUser, product_id: str) -> None:
    """Soft delete: the product disappears everywhere but stays referencable by past orders."""
    _, product = await _require_own_product(conn, user, product_id)
    await conn.execute(
        text("update public.products set status = 'REMOVED' where id = :id"), {"id": product["id"]}
    )
    await audit.record(
        conn, actor=user, action="product.removed", target_type="product", target_id=product_id
    )


# --- Images ------------------------------------------------------------------------
async def add_image(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    product_id: str,
    file: ValidatedFile,
) -> ProductDetailOut:
    _, product = await _require_own_product(conn, user, product_id, active_sme=True)
    count, next_order = (
        await conn.execute(
            text(
                "select count(*), coalesce(max(sort_order) + 1, 0) from public.product_images "
                "where product_id = :id"
            ),
            {"id": product["id"]},
        )
    ).one()
    if count >= MAX_IMAGES_PER_PRODUCT:
        raise ConflictError(
            f"A product can have at most {MAX_IMAGES_PER_PRODUCT} images", code="limit_reached"
        )

    path = f"products/{product['id']}/{file.storage_name()}"
    await storage.upload(PUBLIC_BUCKET, path, file.data, file.kind.mime)
    try:
        async with Database.privileged(conn):
            await conn.execute(
                text(
                    "insert into public.product_images (product_id, storage_path, sha256, sort_order) "
                    "values (:pid, :path, :sha, :order)"
                ),
                {"pid": product["id"], "path": path, "sha": file.sha256, "order": next_order},
            )
        await audit.record(
            conn,
            actor=user,
            action="product_image.added",
            target_type="product",
            target_id=product_id,
            metadata={"sha256": file.sha256},
        )
    except Exception:
        await delete_quietly(storage, PUBLIC_BUCKET, [path])
        raise
    return await get_own_product(conn, storage, user, product_id)


async def delete_image(
    conn: AsyncConnection, storage: StorageClient, user: CurrentUser, product_id: str, image_id: str
) -> ProductDetailOut:
    _, product = await _require_own_product(conn, user, product_id, active_sme=True)
    async with Database.privileged(conn):
        path = (
            await conn.execute(
                text(
                    "delete from public.product_images where id = :id and product_id = :pid "
                    "returning storage_path"
                ),
                {"id": image_id, "pid": product["id"]},
            )
        ).scalar_one_or_none()
    if path is None:
        raise NotFoundError("Image not found")
    await audit.record(
        conn,
        actor=user,
        action="product_image.removed",
        target_type="product",
        target_id=product_id,
    )
    await delete_quietly(storage, PUBLIC_BUCKET, [path])
    return await get_own_product(conn, storage, user, product_id)


# --- Authenticity evidence ------------------------------------------------------------
async def add_evidence(
    conn: AsyncConnection,
    storage: StorageClient,
    user: CurrentUser,
    product_id: str,
    *,
    evidence_type: ProductEvidenceType,
    description: str,
    file: ValidatedFile,
) -> ProductDetailOut:
    sme, product = await _require_own_product(conn, user, product_id, active_sme=True)
    count = (
        await conn.execute(
            text("select count(*) from public.evidence where product_id = :id"),
            {"id": product["id"]},
        )
    ).scalar_one()
    if count >= MAX_EVIDENCE_PER_PRODUCT:
        raise ConflictError("Evidence limit reached for this product", code="limit_reached")

    stored = await evidence.store_private_file(storage, str(sme["id"]), file)
    try:
        evidence_id = await evidence.insert_file_evidence(
            conn,
            stored=stored,
            evidence_type=evidence_type.value,
            provenance="SELLER_CLAIM",
            sme_id=str(sme["id"]),
            product_id=str(product["id"]),
            created_by=user.id,
            description=description,
        )
        await audit.record(
            conn,
            actor=user,
            action="evidence.created",
            target_type="evidence",
            target_id=evidence_id,
            metadata={"product_id": product_id, "type": evidence_type.value, "sha256": file.sha256},
        )
    except Exception:
        await delete_quietly(storage, PRIVATE_BUCKET, [stored.path])
        raise
    return await get_own_product(conn, storage, user, product_id)


# --- Public ------------------------------------------------------------------------
async def list_public_store_products(
    conn: AsyncConnection, storage: StorageClient, slug: str
) -> list[PublicProductOut]:
    """Anon transaction: RLS only returns ACTIVE products of published, active stores."""
    store = (
        await conn.execute(
            text("select id from public.smes where slug = :slug"), {"slug": slug.lower()}
        )
    ).scalar_one_or_none()
    if store is None:
        raise NotFoundError("Store not found")

    rows = (
        (
            await conn.execute(
                text(
                    "select id, category_id, name_i18n, description_i18n, price_lkr, stock, "
                    "authenticity_status from public.products where sme_id = :sme "
                    "order by created_at desc limit 200"
                ),
                {"sme": store},
            )
        )
        .mappings()
        .all()
    )
    images = await _images_by_product(conn, storage, [r["id"] for r in rows])
    return [
        PublicProductOut(
            id=str(r["id"]),
            category_id=r["category_id"],
            name_i18n=r["name_i18n"],
            description_i18n=r["description_i18n"],
            price_lkr=r["price_lkr"],
            in_stock=r["stock"] > 0,
            authenticity_status=r["authenticity_status"],
            images=images.get(str(r["id"]), []),
        )
        for r in rows
    ]
