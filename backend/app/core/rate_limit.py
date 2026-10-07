"""Per-client rate limiting as a FastAPI dependency (``limits`` library, in-memory).

In-memory and per-process: suitable for the single-instance MVP. Behind a reverse proxy, run
uvicorn with --proxy-headers / --forwarded-allow-ips so request.client is the real client IP.
"""

from fastapi import Request
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter

from app.core.errors import AppError

DEFAULT_LIMIT = "120/minute"

_storage = MemoryStorage()
_limiter = MovingWindowRateLimiter(_storage)


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


def rate_limit(limit: str, *, scope: str = "default"):  # noqa: ANN201 — FastAPI dependency
    parsed = parse(limit)

    async def _dependency(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        if not _limiter.hit(parsed, scope, client):
            raise RateLimitedError("Too many requests. Please try again shortly.")

    return _dependency


def reset_rate_limits() -> None:
    _storage.reset()
