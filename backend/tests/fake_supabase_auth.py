"""TEST-ONLY stand-in for Supabase Auth (GoTrue), so browser tests can sign in.

Implements just what the frontend uses: password sign-in, refresh, current user, sign-out and the
JWKS endpoint. Tokens are ES256 JWTs with Supabase's claim layout, verified by the real backend
`TokenVerifier` and by supabase-js `getClaims()` (WebCrypto, via the JWKS endpoint).

Never used outside `tests/e2e_server.py`.
"""

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

KID = "trustora-e2e"
TOKEN_SECONDS = 3600


@dataclass(frozen=True)
class FakeUser:
    id: str
    email: str
    password: str


class FakeAuth:
    def __init__(self, *, issuer: str, users: list[FakeUser], cors_origin: str) -> None:
        self.issuer = issuer
        self._users = {u.email: u for u in users}
        self._by_id = {u.id: u for u in users}
        self._refresh: dict[str, str] = {}  # refresh token → user id
        self._key = ec.generate_private_key(ec.SECP256R1())
        jwk = json.loads(ECAlgorithm.to_jwk(self._key.public_key()))
        self.jwks = {
            "keys": [{**jwk, "kid": KID, "alg": "ES256", "use": "sig", "key_ops": ["verify"]}]
        }
        self.app = Starlette(
            routes=[
                Route("/.well-known/jwks.json", self._jwks),
                Route("/token", self._token, methods=["POST"]),
                Route("/user", self._user),
                Route("/logout", self._logout, methods=["POST"]),
                Route("/signup", self._signup, methods=["POST"]),
            ],
            middleware=[
                Middleware(
                    CORSMiddleware,
                    allow_origins=[cors_origin],
                    allow_methods=["*"],
                    allow_headers=["*"],
                ),
            ],  # fmt: skip
        )

    # Used by the backend's TokenVerifier instead of fetching the JWKS over HTTP.
    def get_signing_key_from_jwt(self, token: str) -> Any:
        return _Key(self._key.public_key())

    def _session(self, user: FakeUser) -> dict[str, Any]:
        now = int(time.time())
        claims = {
            "sub": user.id, "aud": "authenticated", "role": "authenticated", "email": user.email,
            "iss": self.issuer, "iat": now, "exp": now + TOKEN_SECONDS, "aal": "aal1",
            "session_id": secrets.token_hex(8), "is_anonymous": False,
        }  # fmt: skip
        access = jwt.encode(claims, self._key, algorithm="ES256", headers={"kid": KID})
        refresh = secrets.token_urlsafe(24)
        self._refresh[refresh] = user.id
        return {
            "access_token": access,
            "token_type": "bearer",
            "expires_in": TOKEN_SECONDS,
            "expires_at": now + TOKEN_SECONDS,
            "refresh_token": refresh,
            "user": self._user_json(user),
        }

    @staticmethod
    def _user_json(user: FakeUser) -> dict[str, Any]:
        return {
            "id": user.id, "aud": "authenticated", "role": "authenticated", "email": user.email,
            "email_confirmed_at": "2026-01-01T00:00:00Z", "app_metadata": {"provider": "email"},
            "user_metadata": {}, "created_at": "2026-01-01T00:00:00Z",
        }  # fmt: skip

    async def _jwks(self, _: Request) -> Response:
        return JSONResponse(self.jwks)

    async def _token(self, request: Request) -> Response:
        body = await request.json()
        grant = request.query_params.get("grant_type")
        if grant == "password":
            user = self._users.get(str(body.get("email", "")).lower())
            if user is None or not secrets.compare_digest(
                user.password, str(body.get("password", ""))
            ):
                return _error(400, "invalid_credentials", "Invalid login credentials")
            return JSONResponse(self._session(user))
        if grant == "refresh_token":
            user_id = self._refresh.pop(str(body.get("refresh_token", "")), None)
            if user_id is None:
                return _error(400, "refresh_token_not_found", "Invalid Refresh Token")
            return JSONResponse(self._session(self._by_id[user_id]))
        return _error(400, "unsupported_grant_type", "Unsupported grant type")

    async def _user(self, request: Request) -> Response:
        token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        try:
            claims = jwt.decode(token, self._key.public_key(), algorithms=["ES256"],
                                audience="authenticated", issuer=self.issuer)  # fmt: skip
        except jwt.PyJWTError:
            return _error(401, "bad_jwt", "invalid JWT")
        return JSONResponse(self._user_json(self._by_id[claims["sub"]]))

    async def _logout(self, _: Request) -> Response:
        return Response(status_code=204)

    async def _signup(self, _: Request) -> Response:
        # Sign-up needs email confirmation in Supabase; e2e tests use seeded accounts instead.
        return _error(422, "signup_disabled", "Signups not allowed for this instance")


@dataclass(frozen=True)
class _Key:
    key: Any


def _error(status: int, code: str, message: str) -> Response:
    return JSONResponse({"code": status, "error_code": code, "msg": message}, status_code=status)
