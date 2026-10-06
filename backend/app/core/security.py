"""Verification of Supabase Auth access tokens (JWT).

Asymmetric tokens (ES256/RS256) are verified against the project's JWKS endpoint.
Legacy HS256 tokens are accepted only when SUPABASE_JWT_SECRET is configured.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.errors import AppError, UnauthorizedError

ASYMMETRIC_ALGORITHMS = ("ES256", "RS256")
AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthClaims:
    user_id: str
    email: str | None
    raw: dict[str, Any]


class SigningKeyResolver(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class TokenVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        jwks_client: SigningKeyResolver,
        hs256_secret: str | None = None,
    ) -> None:
        self._issuer = issuer
        self._jwks_client = jwks_client
        self._hs256_secret = hs256_secret

    @classmethod
    def from_settings(cls, settings: Settings) -> "TokenVerifier":
        secret = settings.supabase_jwt_secret
        return cls(
            issuer=settings.jwt_issuer,
            jwks_client=PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=600, timeout=5),
            hs256_secret=secret.get_secret_value() if secret else None,
        )

    def verify(self, token: str) -> AuthClaims:
        """Blocking (may fetch JWKS); call from a worker thread."""
        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
            if algorithm in ASYMMETRIC_ALGORITHMS:
                key = self._jwks_client.get_signing_key_from_jwt(token).key
            elif algorithm == "HS256" and self._hs256_secret:
                key = self._hs256_secret
            else:
                raise UnauthorizedError("Unsupported token")

            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "aud", "iss"]},
                leeway=10,
            )
        except UnauthorizedError:
            raise
        except jwt.PyJWKClientConnectionError as exc:
            raise AppError(
                "Authentication service unavailable", code="auth_unavailable", status_code=503
            ) from exc
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("Session expired", code="token_expired") from exc
        except (jwt.PyJWTError, ValueError) as exc:
            raise UnauthorizedError("Invalid token") from exc

        if claims.get("role") != AUDIENCE:
            raise UnauthorizedError("Invalid token")

        return AuthClaims(user_id=str(claims["sub"]), email=claims.get("email"), raw=claims)
