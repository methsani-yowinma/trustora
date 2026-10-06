import json
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("trustora.http")

_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cache-Control": "no-store",
    # JSON only: nothing from the API may run, load or be framed if opened in a browser.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cross-Origin-Resource-Policy": "same-site",
}
# Production is served over HTTPS only; browsers ignore this header on plain HTTP.
HSTS = "max-age=31536000; includeSubDomains"
# The development API docs page needs its own scripts and styles.
_DOCS_PATHS = ("/docs", "/openapi.json")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, adds security headers and logs one line per request."""

    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id
        docs = request.url.path.startswith(_DOCS_PATHS)
        for header, value in SECURITY_HEADERS.items():
            if not (docs and header == "Content-Security-Policy"):
                response.headers.setdefault(header, value)
        if self._hsts:
            response.headers.setdefault("Strict-Transport-Security", HSTS)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        return response


MB = 1024 * 1024
# Largest legitimate request: a verification with 5 documents of 10 MB each, plus form overhead.
MAX_MULTIPART_BYTES = 52 * MB
MAX_OTHER_BYTES = 1 * MB


class BodySizeLimitMiddleware:
    """Rejects oversized request bodies before they are parsed or buffered (HTTP 413).

    Checks Content-Length up front and also counts streamed bytes, so chunked requests without
    a length cannot bypass the limit. Per-file limits are still enforced by the upload checks.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        content_type = headers.get(b"content-type", b"").lower()
        limit = MAX_MULTIPART_BYTES if content_type.startswith(b"multipart/") else MAX_OTHER_BYTES
        declared = headers.get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await _too_large(send)
            return

        received = 0
        exceeded = False
        responded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal responded
            if exceeded:
                # The framework may turn the aborted read into its own error (e.g. a 400 for an
                # unparsable body); the client always gets the 413 instead.
                if not responded:
                    responded = True
                    await _too_large(send)
                return
            if message["type"] == "http.response.start":
                responded = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            if not responded:
                await _too_large(send)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send: Send) -> None:
    body = json.dumps(
        {"error": {"code": "payload_too_large", "message": "The request is too large"}}
    ).encode()
    await send({"type": "http.response.start", "status": 413, "headers": [
        (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
        (b"connection", b"close"),
    ]})  # fmt: skip
    await send({"type": "http.response.body", "body": body})
