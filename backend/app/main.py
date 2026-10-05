import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings, get_settings
from app.core.db import Database, create_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.core.rate_limit import DEFAULT_LIMIT, rate_limit
from app.core.security import TokenVerifier
from app.users.router import router as users_router

logger = logging.getLogger("trustora")

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    db: Database | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.db.dispose()

    app = FastAPI(
        title="Trustora API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.db = db or Database(create_engine(settings.async_database_url))
    app.state.token_verifier = token_verifier or TokenVerifier.from_settings(settings)

    register_error_handlers(app)

    # Order: last added runs first. CORS must wrap everything so error responses carry headers.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # auth uses Bearer tokens, not cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # Health checks are not rate limited; every other API route gets the default limit.
    health_router = APIRouter(prefix=API_PREFIX)
    api = APIRouter(prefix=API_PREFIX, dependencies=[Depends(rate_limit(DEFAULT_LIMIT))])

    @health_router.get("/health", tags=["health"])
    async def health(request: Request) -> dict[str, str]:
        try:
            await request.app.state.db.ping()
            database = "ok"
        except Exception:  # noqa: BLE001 — health must report, not raise
            logger.warning("Database health check failed", exc_info=True)
            database = "unavailable"
        return {"status": "ok" if database == "ok" else "degraded", "database": database}

    api.include_router(users_router)
    app.include_router(health_router)
    app.include_router(api)
    return app
