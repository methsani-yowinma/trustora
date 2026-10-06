"""Consistent error envelope: {"error": {"code": ..., "message": ..., "details"?: ...}}.

Internal details (stack traces, SQL, tokens) are never returned to clients.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("trustora.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


def is_unique_violation(exc: BaseException) -> bool:
    """True if a SQLAlchemy/asyncpg error is a Postgres unique violation (SQLSTATE 23505)."""
    orig = getattr(exc, "orig", None)
    return (
        getattr(orig, "sqlstate", None) == "23505"
        or getattr(getattr(orig, "__cause__", None), "sqlstate", None) == "23505"
    )


def _envelope(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


_HTTP_CODES = {
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "file_too_large",
    429: "rate_limited",
}


security_logger = logging.getLogger("trustora.security")

# Denied or throttled requests are security events worth monitoring (OWASP A09).
_SECURITY_STATUSES = {401, 403, 429}


def _log_security_event(request: Request, status_code: int, code: str) -> None:
    if status_code in _SECURITY_STATUSES:
        # Never the token or request body; the request id links to the access log line.
        security_logger.warning(
            "request denied",
            extra={
                "status": status_code,
                "code": code,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else None,
                "request_id": getattr(request.state, "request_id", None),
            },
        )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        _log_security_event(request, exc.status_code, exc.code)
        return _envelope(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        _log_security_event(request, exc.status_code, code)
        message = exc.detail if isinstance(exc.detail, str) else code
        return _envelope(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Echo field locations and messages only — never the submitted input.
        details = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _envelope(422, "validation_error", "Invalid request", details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled error",
            extra={
                "path": request.url.path,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        return _envelope(500, "internal_error", "An unexpected error occurred")
