"""Test fixtures.

Integration tests run against a real, throwaway PostgreSQL 16 (via ``pgserver``) with a
minimal Supabase shim + the real migrations applied, so RLS policies are exercised for real.
JWTs are signed with a locally generated ES256 key served by a fake JWKS resolver.
"""

import json
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import jwt
import pgserver
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.core.db import Database, create_engine
from app.core.rate_limit import reset_rate_limits
from app.core.security import TokenVerifier
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
SHIM = Path(__file__).parent / "sql" / "supabase_shim.sql"

SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def postgres_uri() -> Any:
    data_dir = tempfile.mkdtemp(prefix="trustora-pg-")
    server = pgserver.get_server(data_dir, cleanup_mode="delete")
    database = f"trustora_test_{uuid.uuid4().hex[:8]}"
    server.psql(f"create database {database};")
    uri = server.get_uri(database)
    yield uri
    server.cleanup()


async def _apply_sql_files(engine: AsyncEngine, files: list[Path]) -> None:
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        for path in files:
            await raw.driver_connection.execute(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
async def engine(postgres_uri: str) -> AsyncIterator[AsyncEngine]:
    url = postgres_uri.replace("postgresql://", "postgresql+asyncpg://", 1)
    eng = create_engine(url)
    await _apply_sql_files(eng, [SHIM, *MIGRATIONS])
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def database(engine: AsyncEngine) -> Database:
    return Database(engine)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@dataclass
class _Key:
    key: Any


class FakeJWKS:
    def __init__(self, public_key: Any) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str) -> _Key:
        return _Key(self.public_key)


@pytest.fixture(scope="session")
def signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="session")
def token_verifier(signing_key: ec.EllipticCurvePrivateKey) -> TokenVerifier:
    return TokenVerifier(issuer=ISSUER, jwks_client=FakeJWKS(signing_key.public_key()))


TokenFactory = Callable[..., str]


@pytest.fixture(scope="session")
def make_token(signing_key: ec.EllipticCurvePrivateKey) -> TokenFactory:
    def _make(user_id: str, *, email: str | None = None, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": user_id,
            "email": email,
            "role": "authenticated",
            "aud": "authenticated",
            "iss": ISSUER,
            "iat": now,
            "exp": now + 3600,
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, signing_key, algorithm="ES256")

    return _make


@dataclass
class SeedUser:
    id: str
    email: str


UserFactory = Callable[..., Any]


@pytest.fixture
def create_user(engine: AsyncEngine) -> UserFactory:
    """Simulates Supabase sign-up: inserting into auth.users fires the profile trigger."""

    async def _create(
        metadata: dict[str, Any] | None = None,
        *,
        role: str | None = None,
        status: str | None = None,
    ) -> SeedUser:
        user_id = str(uuid.uuid4())
        email = f"{user_id[:8]}@example.test"
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "insert into auth.users (id, email, raw_user_meta_data) "
                    "values (:id, :email, cast(:meta as jsonb))"
                ),
                {"id": user_id, "email": email, "meta": json.dumps(metadata or {})},
            )
            # Privileged changes (as a DB admin would do, e.g. bootstrapping an ADMIN).
            if role:
                await conn.execute(
                    text(
                        "update public.profiles set role = cast(:r as public.user_role) where id = :id"
                    ),
                    {"r": role, "id": user_id},
                )
            if status:
                await conn.execute(
                    text(
                        "update public.profiles set status = cast(:s as public.account_status) "
                        "where id = :id"
                    ),
                    {"s": status, "id": user_id},
                )
        return SeedUser(id=user_id, email=email)

    return _create


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def settings(postgres_uri: str) -> Settings:
    return Settings(
        app_env="test",
        supabase_url=SUPABASE_URL,
        database_url=postgres_uri,
        cors_origins="http://localhost:3000",
    )


@pytest.fixture
def app(settings: Settings, database: Database, token_verifier: TokenVerifier) -> Any:
    reset_rate_limits()
    return create_app(settings, db=database, token_verifier=token_verifier)


@pytest.fixture
async def client(app: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
