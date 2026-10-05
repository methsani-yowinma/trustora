from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Path, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.dependencies import get_anon_db, get_storage, get_user_db, require_role
from app.auth.models import CurrentUser, UserRole
from app.core.rate_limit import rate_limit
from app.core.storage import StorageClient
from app.core.uploads import (
    DOCUMENT_KINDS,
    IMAGE_KINDS,
    MAX_DOCUMENT_BYTES,
    MAX_IMAGE_BYTES,
    read_upload,
)
from app.products import service
from app.products.schemas import (
    CategoryOut,
    EvidenceDescription,
    ProductCreate,
    ProductDetailOut,
    ProductEvidenceType,
    ProductOut,
    ProductUpdate,
    PublicProductOut,
)

UPLOAD_LIMIT = Depends(rate_limit("30/minute", scope="uploads"))

Db = Annotated[AsyncConnection, Depends(get_user_db)]
AnonDb = Annotated[AsyncConnection, Depends(get_anon_db)]
Storage = Annotated[StorageClient, Depends(get_storage)]
SmeUser = Annotated[CurrentUser, Depends(require_role(UserRole.SME))]

# --- SME product management ------------------------------------------------------------
router = APIRouter(prefix="/sme/products", tags=["sme-products"])


@router.get("", response_model=list[ProductOut])
async def list_products(user: SmeUser, conn: Db, storage: Storage) -> list[ProductOut]:
    return await service.list_own_products(conn, storage, user)


@router.post("", response_model=ProductDetailOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    data: ProductCreate, user: SmeUser, conn: Db, storage: Storage
) -> ProductDetailOut:
    return await service.create_product(conn, storage, user, data)


@router.get("/{product_id}", response_model=ProductDetailOut)
async def get_product(
    product_id: UUID, user: SmeUser, conn: Db, storage: Storage
) -> ProductDetailOut:
    return await service.get_own_product(conn, storage, user, str(product_id))


@router.patch("/{product_id}", response_model=ProductDetailOut)
async def update_product(
    product_id: UUID, changes: ProductUpdate, user: SmeUser, conn: Db, storage: Storage
) -> ProductDetailOut:
    return await service.update_product(conn, storage, user, str(product_id), changes)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_product(product_id: UUID, user: SmeUser, conn: Db) -> Response:
    await service.remove_product(conn, user, str(product_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{product_id}/images", response_model=ProductDetailOut, dependencies=[UPLOAD_LIMIT])
async def add_image(
    product_id: UUID,
    user: SmeUser,
    conn: Db,
    storage: Storage,
    file: Annotated[UploadFile, File()],
) -> ProductDetailOut:
    validated = await read_upload(file, allowed=IMAGE_KINDS, max_bytes=MAX_IMAGE_BYTES)
    return await service.add_image(conn, storage, user, str(product_id), validated)


@router.delete("/{product_id}/images/{image_id}", response_model=ProductDetailOut)
async def delete_image(
    product_id: UUID, image_id: UUID, user: SmeUser, conn: Db, storage: Storage
) -> ProductDetailOut:
    return await service.delete_image(conn, storage, user, str(product_id), str(image_id))


@router.post("/{product_id}/evidence", response_model=ProductDetailOut, dependencies=[UPLOAD_LIMIT])
async def add_evidence(
    product_id: UUID,
    user: SmeUser,
    conn: Db,
    storage: Storage,
    evidence_type: Annotated[ProductEvidenceType, Form()],
    description: Annotated[EvidenceDescription, Form()],
    file: Annotated[UploadFile, File()],
) -> ProductDetailOut:
    validated = await read_upload(file, allowed=DOCUMENT_KINDS, max_bytes=MAX_DOCUMENT_BYTES)
    return await service.add_evidence(
        conn,
        storage,
        user,
        str(product_id),
        evidence_type=evidence_type,
        description=description,
        file=validated,
    )


# --- Public ---------------------------------------------------------------------------------
public_router = APIRouter(tags=["stores"])


@public_router.get("/categories", response_model=list[CategoryOut])
async def list_categories(conn: AnonDb) -> list[CategoryOut]:
    return await service.list_categories(conn)


@public_router.get("/stores/{slug}/products", response_model=list[PublicProductOut])
async def list_store_products(
    slug: Annotated[str, Path(pattern=r"^[A-Za-z0-9-]{3,40}$")], conn: AnonDb, storage: Storage
) -> list[PublicProductOut]:
    return await service.list_public_store_products(conn, storage, slug)
