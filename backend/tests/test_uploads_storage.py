import hashlib
import json

import httpx
import pytest

from app.core.errors import PayloadTooLargeError, UnsupportedMediaTypeError, ValidationAppError
from app.core.storage import StorageError, SupabaseStorage
from app.core.uploads import DOCUMENT_KINDS, IMAGE_KINDS, JPEG, PDF, PNG, validate_bytes
from tests.conftest import JPEG_BYTES, PDF_BYTES, PNG_BYTES

# --- Upload validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "filename", "kind"),
    [(PNG_BYTES, "logo.PNG", PNG), (JPEG_BYTES, "photo.jpeg", JPEG), (PDF_BYTES, "br.pdf", PDF)],
)
def test_detects_type_from_content(data: bytes, filename: str, kind: object) -> None:
    result = validate_bytes(data, filename, allowed=DOCUMENT_KINDS, max_bytes=1024)
    assert result.kind is kind
    assert result.sha256 == hashlib.sha256(data).hexdigest()


def test_storage_name_never_uses_client_filename() -> None:
    result = validate_bytes(PNG_BYTES, "../../etc/passwd.png", allowed=IMAGE_KINDS, max_bytes=1024)
    name = result.storage_name()
    assert "passwd" not in name and "/" not in name and name.endswith(".png")


def test_rejects_disguised_file() -> None:
    # A PDF renamed to .png is rejected even though PDFs are allowed here.
    with pytest.raises(ValidationAppError) as exc:
        validate_bytes(PDF_BYTES, "image.png", allowed=DOCUMENT_KINDS, max_bytes=1024)
    assert exc.value.code == "extension_mismatch"


@pytest.mark.parametrize(
    "data",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b"<html><script>alert(1)</script></html>",
        b"MZ\x90\x00 executable",
    ],
)
def test_rejects_unsupported_content(data: bytes) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        validate_bytes(data, "file.png", allowed=IMAGE_KINDS, max_bytes=1024)


def test_pdf_not_allowed_where_only_images_are() -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        validate_bytes(PDF_BYTES, "doc.pdf", allowed=IMAGE_KINDS, max_bytes=1024)


@pytest.mark.parametrize("marker", [b"/JavaScript", b"/Launch", b"/EmbeddedFile", b"/OpenAction"])
def test_rejects_pdf_with_active_content(marker: bytes) -> None:
    data = PDF_BYTES.replace(b"/Catalog", b"/Catalog " + marker)
    with pytest.raises(UnsupportedMediaTypeError):
        validate_bytes(data, "doc.pdf", allowed=DOCUMENT_KINDS, max_bytes=1024)


def test_size_limit_and_empty_file() -> None:
    with pytest.raises(PayloadTooLargeError):
        validate_bytes(PNG_BYTES + b"\x00" * 2048, "a.png", allowed=IMAGE_KINDS, max_bytes=1024)
    with pytest.raises(ValidationAppError):
        validate_bytes(b"", "a.png", allowed=IMAGE_KINDS, max_bytes=1024)


# --- Supabase Storage client -------------------------------------------------------------


def _storage(handler: object) -> SupabaseStorage:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]
    return SupabaseStorage("https://proj.supabase.co/storage/v1", "service-key", http)


async def test_upload_request_shape() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "x"})

    await _storage(handler).upload("private-evidence", "smes/a b/f.pdf", b"data", "application/pdf")
    request = seen[0]
    assert request.method == "POST"
    assert (
        str(request.url)
        == "https://proj.supabase.co/storage/v1/object/private-evidence/smes/a%20b/f.pdf"
    )
    assert request.headers["Authorization"] == "Bearer service-key"
    assert request.headers["apikey"] == "service-key"
    assert request.headers["x-upsert"] == "false"
    assert request.headers["Content-Type"] == "application/pdf"


async def test_signed_url_and_delete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/object/private-evidence"):
            assert request.method == "DELETE"
            assert json.loads(request.content) == {"prefixes": ["a.pdf"]}
            return httpx.Response(200, json=[])
        assert json.loads(request.content) == {"expiresIn": 300}
        return httpx.Response(
            200, json={"signedURL": "/object/sign/private-evidence/a.pdf?token=t"}
        )

    storage = _storage(handler)
    url = await storage.signed_url("private-evidence", "a.pdf")
    assert url == "https://proj.supabase.co/storage/v1/object/sign/private-evidence/a.pdf?token=t"
    await storage.delete("private-evidence", ["a.pdf"])
    assert storage.public_url("public-media", "p/1.png") == (
        "https://proj.supabase.co/storage/v1/object/public/public-media/p/1.png"
    )


async def test_storage_errors_do_not_leak_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "secret internal detail"})

    with pytest.raises(StorageError) as exc:
        await _storage(handler).upload("public-media", "x.png", b"x", "image/png")
    assert "secret" not in exc.value.message
