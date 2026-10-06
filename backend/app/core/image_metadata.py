"""Removes embedded metadata from uploaded images, without re-encoding them.

Phone photos carry EXIF data (GPS location, device, time) and sometimes XMP/IPTC blocks. Product
photos and logos are public, and complaint photos are shown to the other party, so a seller's or
customer's home location could leak. Only metadata containers are dropped; image data, colour
profiles and everything needed to display the image are kept byte-for-byte.

Images whose container structure cannot be parsed are rejected rather than stored unchecked.
"""

import struct

from app.core.errors import UnsupportedMediaTypeError


class MalformedImageError(UnsupportedMediaTypeError):
    def __init__(self) -> None:
        super().__init__("The image file could not be processed", code="invalid_image")


# --- JPEG ---------------------------------------------------------------------------------------
_JPEG_APP1 = 0xE1  # EXIF and XMP
_JPEG_APP13 = 0xED  # IPTC / Photoshop
_JPEG_COM = 0xFE  # comments
_JPEG_DROP = {_JPEG_APP1, _JPEG_APP13, _JPEG_COM}
_JPEG_SOS = 0xDA
_JPEG_STANDALONE = {0x01, *range(0xD0, 0xD8)}  # TEM, RST0–7: no length field


def strip_jpeg(data: bytes) -> bytes:
    if not data.startswith(b"\xff\xd8"):
        raise MalformedImageError
    out = bytearray(b"\xff\xd8")
    i = 2
    while True:
        if i >= len(data) or data[i] != 0xFF:
            raise MalformedImageError
        while i < len(data) and data[i] == 0xFF:  # fill bytes
            i += 1
        if i >= len(data):
            raise MalformedImageError
        marker = data[i]
        i += 1
        if marker in _JPEG_STANDALONE:
            out += bytes((0xFF, marker))
            continue
        if marker == 0xD9:  # EOI before any scan: nothing to display
            raise MalformedImageError
        if i + 2 > len(data):
            raise MalformedImageError
        (length,) = struct.unpack(">H", data[i : i + 2])
        if length < 2 or i + length > len(data):
            raise MalformedImageError
        segment = data[i : i + length]
        i += length
        if marker == _JPEG_SOS:
            # Entropy-coded data follows; metadata segments only appear before the first scan.
            out += bytes((0xFF, marker)) + segment + data[i:]
            return bytes(out)
        if marker not in _JPEG_DROP:
            out += bytes((0xFF, marker)) + segment


# --- PNG ----------------------------------------------------------------------------------------
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_DROP = {b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"}


def strip_png(data: bytes) -> bytes:
    if not data.startswith(_PNG_SIGNATURE):
        raise MalformedImageError
    out = bytearray(_PNG_SIGNATURE)
    i = len(_PNG_SIGNATURE)
    seen_end = False
    while i < len(data):
        if i + 12 > len(data):
            raise MalformedImageError
        (length,) = struct.unpack(">I", data[i : i + 4])
        kind = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > len(data):
            raise MalformedImageError
        if kind not in _PNG_DROP:
            out += data[i:end]
        i = end
        if kind == b"IEND":
            seen_end = True
            break
    if not seen_end:
        raise MalformedImageError
    return bytes(out)


# --- WebP ---------------------------------------------------------------------------------------
_WEBP_DROP = {b"EXIF", b"XMP "}
_VP8X_EXIF_FLAG = 0x08
_VP8X_XMP_FLAG = 0x04


def strip_webp(data: bytes) -> bytes:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise MalformedImageError
    (riff_size,) = struct.unpack("<I", data[4:8])
    if riff_size + 8 > len(data) or riff_size < 4:
        raise MalformedImageError
    body = bytearray()
    i, end = 12, 8 + riff_size
    while i < end:
        if i + 8 > end:
            raise MalformedImageError
        kind = data[i : i + 4]
        (size,) = struct.unpack("<I", data[i + 4 : i + 8])
        chunk_end = i + 8 + size + (size & 1)  # chunks are padded to an even size
        if chunk_end > end:
            raise MalformedImageError
        chunk = bytearray(data[i:chunk_end])
        if kind == b"VP8X" and size >= 1:
            chunk[8] &= ~(_VP8X_EXIF_FLAG | _VP8X_XMP_FLAG) & 0xFF
        if kind not in _WEBP_DROP:
            body += chunk
        i = chunk_end
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + bytes(body)


def strip_metadata(data: bytes, mime: str) -> bytes:
    if mime == "image/jpeg":
        return strip_jpeg(data)
    if mime == "image/png":
        return strip_png(data)
    if mime == "image/webp":
        return strip_webp(data)
    return data
