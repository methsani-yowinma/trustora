"""Phase 9: input hardening — image metadata removal, social links, strict request bodies."""

import hashlib
import struct
import zlib
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.core.image_metadata import MalformedImageError, strip_metadata
from app.core.uploads import IMAGE_KINDS, MAX_IMAGE_BYTES, validate_bytes
from app.smes.schemas import SocialAccountCreate
from tests.conftest import JPEG_BYTES, PNG_BYTES

GPS = b"GPSLatitude 6.9271 N GPSLongitude 79.8612 E"


# --- Image metadata ------------------------------------------------------------------------------
def _jpeg_with_metadata() -> bytes:
    exif = b"Exif\x00\x00" + GPS
    xmp = b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>" + GPS + b"</x:xmpmeta>"
    iptc = b"Photoshop 3.0\x00" + GPS
    comment = b"taken at home " + GPS

    def segment(marker: int, payload: bytes) -> bytes:
        return bytes((0xFF, marker)) + struct.pack(">H", len(payload) + 2) + payload

    return (
        JPEG_BYTES[:2]
        + segment(0xE1, exif)
        + JPEG_BYTES[2:20]  # APP0 (JFIF) is kept
        + segment(0xE1, xmp)
        + segment(0xED, iptc)
        + segment(0xFE, comment)
        + JPEG_BYTES[20:]
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = struct.pack(">I", zlib.crc32(kind + payload))
    return struct.pack(">I", len(payload)) + kind + payload + crc


def _png_with_metadata() -> bytes:
    iend = _png_chunk(b"IEND", b"")
    body = PNG_BYTES[: -len(iend)]
    return (
        body[:33]  # signature + IHDR
        + _png_chunk(b"eXIf", b"MM\x00*" + GPS)
        + _png_chunk(b"tEXt", b"Comment\x00" + GPS)
        + _png_chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + GPS)
        + body[33:]
        + iend
    )


def _webp(chunks: list[tuple[bytes, bytes]]) -> bytes:
    body = b""
    for kind, payload in chunks:
        body += (
            kind
            + struct.pack("<I", len(payload))
            + payload
            + (b"\x00" if len(payload) % 2 else b"")
        )
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


VP8X_FLAGS = 0x08 | 0x04 | 0x10  # EXIF, XMP and alpha
WEBP_WITH_METADATA = _webp([
    (b"VP8X", bytes((VP8X_FLAGS, 0, 0, 0)) + b"\x00" * 6),
    (b"VP8L", b"\x2f\x00\x00\x00\x00"),
    (b"EXIF", b"MM\x00*" + GPS),
    (b"XMP ", b"<x:xmpmeta>" + GPS + b"</x:xmpmeta>"),
])  # fmt: skip


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (_jpeg_with_metadata(), "image/jpeg"),
        (_png_with_metadata(), "image/png"),
        (WEBP_WITH_METADATA, "image/webp"),
    ],
)
def test_location_metadata_is_removed(data: bytes, mime: str) -> None:
    assert GPS in data
    cleaned = strip_metadata(data, mime)
    assert GPS not in cleaned
    assert strip_metadata(cleaned, mime) == cleaned  # idempotent: nothing else is touched


def test_images_without_metadata_are_unchanged() -> None:
    assert strip_metadata(JPEG_BYTES, "image/jpeg") == JPEG_BYTES
    assert strip_metadata(PNG_BYTES, "image/png") == PNG_BYTES
    assert _jpeg_with_metadata().count(b"JFIF") == strip_metadata(
        _jpeg_with_metadata(), "image/jpeg"
    ).count(b"JFIF")


def test_webp_header_is_kept_consistent() -> None:
    cleaned = strip_metadata(WEBP_WITH_METADATA, "image/webp")
    (riff_size,) = struct.unpack("<I", cleaned[4:8])
    assert riff_size + 8 == len(cleaned)
    assert cleaned[20] == 0x10  # VP8X: EXIF/XMP flags cleared, alpha kept
    assert b"EXIF" not in cleaned and b"XMP " not in cleaned


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (b"\xff\xd8\xff\xe1\xff\xff" + b"\x00" * 8, "image/jpeg"),  # segment longer than file
        (b"\xff\xd8\xff\xd9", "image/jpeg"),  # no image data
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png"),  # no IEND
        (b"RIFF\xff\xff\x00\x00WEBPVP8 ", "image/webp"),  # size beyond file
    ],
)
def test_malformed_images_are_rejected(data: bytes, mime: str) -> None:
    with pytest.raises(MalformedImageError):
        strip_metadata(data, mime)


def test_uploads_store_and_hash_the_cleaned_image() -> None:
    validated = validate_bytes(
        _jpeg_with_metadata(), "photo.jpg", allowed=IMAGE_KINDS, max_bytes=MAX_IMAGE_BYTES
    )
    assert GPS not in validated.data
    assert validated.sha256 == hashlib.sha256(validated.data).hexdigest()


async def test_uploaded_logo_has_no_location(
    client: httpx.AsyncClient, make_store: Any, storage: Any
) -> None:
    owner, _ = await make_store()
    response = await client.post(
        "/api/v1/smes/me/logo",
        headers=owner.headers,
        files={"file": ("logo.jpg", _jpeg_with_metadata(), "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    [(data, _)] = storage.objects.values()
    assert GPS not in data and data.startswith(b"\xff\xd8")


# --- Social links --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example\\@facebook.com/x",  # browsers go to evil.example
        "https://evil.example%5C@facebook.com/",
        "https://user:pw@facebook.com/x",
        "https://facebook.com.evil.example/",
        "https://facebook.com:8443/x",
        "https://face\tbook.com/x",
        "http://facebook.com/x",
        "javascript://facebook.com/%0aalert(1)",
    ],
)
def test_social_links_that_could_point_elsewhere_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        SocialAccountCreate(platform="FACEBOOK", handle="lanka", url=url)


def test_social_links_are_stored_in_canonical_form() -> None:
    account = SocialAccountCreate(
        platform="FACEBOOK", handle="lanka", url="https://WWW.Facebook.com/lanka?ref=1#frag"
    )
    assert account.url == "https://www.facebook.com/lanka?ref=1"


# --- Request bodies ------------------------------------------------------------------------------
def _body_models(app: Any) -> set[type[BaseModel]]:
    found: set[type[BaseModel]] = set()

    def collect(annotation: Any) -> None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation in found:
                return
            found.add(annotation)
            for field in annotation.model_fields.values():
                collect(field.annotation)
        for arg in getattr(annotation, "__args__", ()) or ():
            collect(arg)

    for route in app.routes:
        for ctx in getattr(route, "effective_route_contexts", lambda: [])():
            for param in ctx.dependant.body_params:
                collect(param.field_info.annotation)
    return found


def test_every_request_body_rejects_unknown_fields(app: Any) -> None:
    """Mass assignment protection: no request model silently accepts extra fields."""
    models = _body_models(app)
    assert len(models) >= 20
    lenient = sorted(m.__name__ for m in models if m.model_config.get("extra") != "forbid")
    assert lenient == []
