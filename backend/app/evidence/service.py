"""Evidence records: integrity-hashed, provenance-labelled, written only by the backend.

Clients have no insert grant on public.evidence, so writes run privileged *after* the caller's
authorization has been checked by the calling service.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db import Database
from app.core.storage import PRIVATE_BUCKET, StorageClient, signed_url_or_none
from app.core.uploads import ValidatedFile
from app.evidence.schemas import EvidenceFileOut

_COLUMNS = (
    "id, type, provenance, description, mime_type, size_bytes, sha256, review_status, "
    "created_at, storage_path"
)


@dataclass(frozen=True)
class StoredFile:
    path: str
    file: ValidatedFile


async def store_private_file(
    storage: StorageClient, sme_id: str, file: ValidatedFile
) -> StoredFile:
    path = f"smes/{sme_id}/{file.storage_name()}"
    await storage.upload(PRIVATE_BUCKET, path, file.data, file.kind.mime)
    return StoredFile(path=path, file=file)


async def insert_file_evidence(
    conn: AsyncConnection,
    *,
    stored: StoredFile,
    evidence_type: str,
    provenance: str,
    sme_id: str,
    created_by: str,
    description: str | None = None,
    product_id: str | None = None,
    verification_id: str | None = None,
) -> str:
    async with Database.privileged(conn):
        return str(
            (
                await conn.execute(
                    text(
                        "insert into public.evidence (type, provenance, sme_id, product_id, "
                        "verification_id, description, source, storage_path, mime_type, "
                        "size_bytes, sha256, created_by) values (cast(:type as public.evidence_type), "
                        "cast(:provenance as public.evidence_provenance), :sme_id, :product_id, "
                        ":verification_id, :description, 'UPLOAD', :path, :mime, :size, :sha256, "
                        ":created_by) returning id"
                    ),
                    {
                        "type": evidence_type,
                        "provenance": provenance,
                        "sme_id": sme_id,
                        "product_id": product_id,
                        "verification_id": verification_id,
                        "description": description,
                        "path": stored.path,
                        "mime": stored.file.kind.mime,
                        "size": stored.file.size,
                        "sha256": stored.file.sha256,
                        "created_by": created_by,
                    },
                )
            ).scalar_one()
        )


async def insert_record_evidence(
    conn: AsyncConnection,
    *,
    evidence_type: str,
    provenance: str,
    sme_id: str,
    source: str,
    description: str,
    created_by: str | None,
    verification_id: str | None = None,
    review_status: str = "ACCEPTED",
) -> str:
    """Evidence without a file (e.g. a verification result recorded by the platform)."""
    async with Database.privileged(conn):
        return str(
            (
                await conn.execute(
                    text(
                        "insert into public.evidence (type, provenance, sme_id, verification_id, "
                        "description, source, review_status, reviewed_by, reviewed_at, created_by) "
                        "values (cast(:type as public.evidence_type), "
                        "cast(:provenance as public.evidence_provenance), :sme_id, :verification_id, "
                        ":description, :source, cast(:review as public.evidence_review_status), "
                        ":created_by, now(), :created_by) returning id"
                    ),
                    {
                        "type": evidence_type,
                        "provenance": provenance,
                        "sme_id": sme_id,
                        "verification_id": verification_id,
                        "description": description,
                        "source": source,
                        "review": review_status,
                        "created_by": created_by,
                    },
                )
            ).scalar_one()
        )


async def list_evidence(
    conn: AsyncConnection,
    storage: StorageClient,
    *,
    where: str,
    params: dict[str, object],
    with_download_urls: bool,
) -> list[EvidenceFileOut]:
    """Lists evidence visible to the caller (RLS applies). ``where`` is a fixed SQL fragment."""
    rows = (
        (
            await conn.execute(
                text(f"select {_COLUMNS} from public.evidence where {where} order by created_at"),  # noqa: S608
                params,
            )
        )
        .mappings()
        .all()
    )

    items = []
    for row in rows:
        url = None
        if with_download_urls and row["storage_path"]:
            url = await signed_url_or_none(storage, PRIVATE_BUCKET, row["storage_path"])
        items.append(
            EvidenceFileOut(
                **{k: v for k, v in row.items() if k not in ("id", "storage_path")},
                id=str(row["id"]),
                download_url=url,
            )
        )
    return items
