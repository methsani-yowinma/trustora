import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.ai.gemini_client import AiClient, create_ai_client
from app.ai.router import admin_router as ai_admin_router
from app.ai.router import chat_router as ai_chat_router
from app.ai.router import public_router as ai_public_router
from app.complaints.router import admin_router as complaints_admin_router
from app.complaints.router import public_router as complaints_public_router
from app.complaints.router import router as complaints_router
from app.complaints.router import sme_router as complaints_sme_router
from app.core.config import Settings, get_settings
from app.core.db import Database, create_engine
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, RequestContextMiddleware
from app.core.rate_limit import DEFAULT_LIMIT, rate_limit
from app.core.security import TokenVerifier
from app.core.storage import StorageClient, SupabaseStorage, UnconfiguredStorage
from app.orders.router import router as orders_router
from app.orders.router import sme_router as sme_orders_router
from app.products.router import public_router as products_public_router
from app.products.router import router as sme_products_router
from app.reviews.router import router as reviews_router
from app.reviews.router import sme_router as sme_reviews_router
from app.smes.router import admin_router as smes_admin_router
from app.smes.router import public_router as stores_public_router
from app.smes.router import router as smes_router
from app.trust.router import admin_router as trust_admin_router
from app.trust.router import public_router as trust_public_router
from app.trust.router import sme_router as trust_sme_router
from app.users.router import router as users_router

logger = logging.getLogger("trustora")

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    db: Database | None = None,
    token_verifier: TokenVerifier | None = None,
    storage: StorageClient | None = None,
    ai: AiClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await http_client.aclose()
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

    http_client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
    service_key = settings.supabase_service_role_key
    key = settings.gemini_api_key
    app.state.ai = ai or create_ai_client(
        key.get_secret_value() if key else None,
        settings.gemini_model,
        settings.gemini_fallback_list,
    )
    app.state.storage = storage or (
        SupabaseStorage(settings.storage_url, service_key.get_secret_value(), http_client)
        if service_key
        else UnconfiguredStorage(settings.storage_url)
    )

    register_error_handlers(app)

    # Order: last added runs first. CORS must wrap everything so error responses carry headers.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
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
    api.include_router(smes_router)
    api.include_router(sme_products_router)
    api.include_router(stores_public_router)
    api.include_router(products_public_router)
    api.include_router(smes_admin_router)
    api.include_router(trust_public_router)
    api.include_router(trust_sme_router)
    api.include_router(trust_admin_router)
    api.include_router(orders_router)
    api.include_router(sme_orders_router)
    api.include_router(reviews_router)
    api.include_router(sme_reviews_router)
    api.include_router(complaints_router)
    api.include_router(complaints_public_router)
    api.include_router(complaints_sme_router)
    api.include_router(complaints_admin_router)
    api.include_router(ai_public_router)
    api.include_router(ai_admin_router)
    api.include_router(ai_chat_router)
    app.include_router(health_router)
    app.include_router(api)
    return app
