"""Supabase Storage access (server-side only, with the service-role key).

Buckets (created by migration):
* ``public-media``     — logos and product images; readable by public URL.
* ``private-evidence`` — verification and authenticity documents; served only through
  short-lived signed URLs issued after an authorization check.
"""

import logging
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.errors import AppError

logger = logging.getLogger("trustora.storage")

PUBLIC_BUCKET = "public-media"
PRIVATE_BUCKET = "private-evidence"
SIGNED_URL_SECONDS = 300


class StorageError(AppError):
    status_code = 502
    code = "storage_unavailable"


class StorageClient(Protocol):
    async def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, bucket: str, paths: list[str]) -> None: ...

    async def signed_url(
        self, bucket: str, path: str, expires_in: int = SIGNED_URL_SECONDS
    ) -> str: ...

    def public_url(self, bucket: str, path: str) -> str: ...


class SupabaseStorage:
    def __init__(self, base_url: str, service_key: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._http = http
        # Works with both the legacy service_role JWT and the newer secret API keys.
        self._headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    @staticmethod
    def _object(path: str) -> str:
        return quote(path, safe="/")

    async def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        response = await self._http.post(
            f"{self._base}/object/{bucket}/{self._object(path)}",
            content=data,
            headers={
                **self._headers,
                "Content-Type": content_type,
                "x-upsert": "false",
                "Cache-Control": "max-age=31536000",
            },
        )
        self._raise_for_status(response, "upload")

    async def delete(self, bucket: str, paths: list[str]) -> None:
        if not paths:
            return
        response = await self._http.request(
            "DELETE",
            f"{self._base}/object/{bucket}",
            json={"prefixes": paths},
            headers=self._headers,
        )
        self._raise_for_status(response, "delete")

    async def signed_url(self, bucket: str, path: str, expires_in: int = SIGNED_URL_SECONDS) -> str:
        response = await self._http.post(
            f"{self._base}/object/sign/{bucket}/{self._object(path)}",
            json={"expiresIn": expires_in},
            headers=self._headers,
        )
        self._raise_for_status(response, "sign")
        return f"{self._base}{response.json()['signedURL']}"

    def public_url(self, bucket: str, path: str) -> str:
        return f"{self._base}/object/public/{bucket}/{self._object(path)}"

    @staticmethod
    def _raise_for_status(response: httpx.Response, operation: str) -> None:
        if response.is_success:
            return
        # Log status only: storage error bodies can echo request details.
        logger.error("Storage %s failed", operation, extra={"status": response.status_code})
        raise StorageError("File storage is temporarily unavailable")


class UnconfiguredStorage(SupabaseStorage):
    """Used when SUPABASE_SERVICE_ROLE_KEY is not set: reads of public URLs work, writes fail clearly."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    async def upload(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        raise StorageError("File storage is not configured", code="storage_not_configured")

    async def delete(self, bucket: str, paths: list[str]) -> None:
        raise StorageError("File storage is not configured", code="storage_not_configured")

    async def signed_url(self, bucket: str, path: str, expires_in: int = SIGNED_URL_SECONDS) -> str:
        raise StorageError("File storage is not configured", code="storage_not_configured")


async def signed_url_or_none(storage: StorageClient, bucket: str, path: str) -> str | None:
    """For lists: one missing or unsignable object must not break the whole response."""
    try:
        return await storage.signed_url(bucket, path)
    except Exception:  # noqa: BLE001
        logger.warning("Could not sign storage URL", extra={"bucket": bucket})
        return None


async def delete_quietly(storage: StorageClient, bucket: str, paths: list[str]) -> None:
    """Best-effort cleanup of objects whose database write failed or was rolled back."""
    try:
        await storage.delete(bucket, paths)
    except Exception:  # noqa: BLE001
        logger.warning("Orphaned storage objects could not be deleted", extra={"paths": paths})
