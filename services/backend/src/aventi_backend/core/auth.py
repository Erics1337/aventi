from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from aventi_backend.core.settings import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AuthenticatedUser:
    id: str
    email: str | None = None
    role: str = "authenticated"
    is_admin: bool = False


@dataclass(slots=True)
class _JwksCacheEntry:
    fetched_at: float
    keys_by_kid: dict[str, dict[str, Any]]


_JWKS_CACHE: dict[str, _JwksCacheEntry] = {}
_JWKS_CACHE_TTL_SECONDS = 300.0


def _resolve_jwks_url(settings: Settings) -> str:
    if settings.supabase_jwks_url:
        return settings.supabase_jwks_url
    if settings.supabase_url:
        return f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Supabase JWKS URL is not configured",
    )


def _resolve_issuer(settings: Settings) -> str | None:
    if settings.supabase_issuer:
        return settings.supabase_issuer
    if settings.supabase_url:
        return f"{settings.supabase_url.rstrip('/')}/auth/v1"
    return None


async def _fetch_jwks(url: str) -> dict[str, dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to fetch Supabase JWKS",
        ) from exc

    keys = payload.get("keys", [])
    if not isinstance(keys, list):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase JWKS payload is invalid",
        )

    keys_by_kid: dict[str, dict[str, Any]] = {}
    for key in keys:
        if isinstance(key, dict) and isinstance(key.get("kid"), str):
            keys_by_kid[key["kid"]] = key
    return keys_by_kid


async def _get_jwks_keys(settings: Settings, *, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
    jwks_url = _resolve_jwks_url(settings)
    cached = _JWKS_CACHE.get(jwks_url)
    if (
        not force_refresh
        and cached is not None
        and (monotonic() - cached.fetched_at) < _JWKS_CACHE_TTL_SECONDS
    ):
        return cached.keys_by_kid

    keys_by_kid = await _fetch_jwks(jwks_url)
    _JWKS_CACHE[jwks_url] = _JwksCacheEntry(fetched_at=monotonic(), keys_by_kid=keys_by_kid)
    return keys_by_kid


def _get_unverified_claims(token: str) -> dict[str, Any]:
    try:
        return jwt.get_unverified_claims(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def _get_unverified_header(token: str) -> dict[str, Any]:
    try:
        return jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header") from exc


async def _decode_and_verify_supabase_token(token: str, settings: Settings) -> dict[str, Any]:
    header = _get_unverified_header(token)
    alg = str(header.get("alg", "RS256"))
    issuer = _resolve_issuer(settings)

    # Try JWKS fetch/caching first when configured, even for local Supabase (which may return empty keys).
    keys_by_kid: dict[str, dict[str, Any]] = {}
    try:
        keys_by_kid = await _get_jwks_keys(settings)
    except HTTPException:
        # For local HS256 Supabase setups, allow explicit shared-secret verification fallback below.
        if not (alg.startswith("HS") and settings.supabase_jwt_secret):
            raise

    kid = header.get("kid")
    if kid and keys_by_kid:
        jwk_key = keys_by_kid.get(kid)
        if jwk_key is None:
            # Refresh once in case of key rotation.
            keys_by_kid = await _get_jwks_keys(settings, force_refresh=True)
            jwk_key = keys_by_kid.get(kid)
        if jwk_key is not None:
            try:
                return jwt.decode(
                    token,
                    jwk_key,
                    algorithms=[alg],
                    audience=settings.supabase_jwt_audience or None,
                    issuer=issuer,
                    options={
                        "verify_aud": bool(settings.supabase_jwt_audience),
                        "verify_iss": bool(issuer),
                    },
                )
            except JWTError as exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token verification failed",
                ) from exc

    if alg.startswith("HS") and settings.supabase_jwt_secret:
        try:
            return jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=[alg],
                audience=settings.supabase_jwt_audience or None,
                issuer=issuer,
                options={
                    "verify_aud": bool(settings.supabase_jwt_audience),
                    "verify_iss": bool(issuer),
                },
            )
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token verification failed",
            ) from exc

    if alg.startswith("HS"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="HS256 Supabase token requires AVENTI_SUPABASE_JWT_SECRET for local verification",
        )

    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing kid")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token signing key")


async def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if credentials is None:
        if settings.auth_dev_bypass and settings.env in {"development", "test"}:
            return AuthenticatedUser(id="dev-user", email="dev@aventi.local")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = credentials.credentials
    claims = await _decode_and_verify_supabase_token(token, settings)
    # Keep a guarded fallback for explicit dev bypass when local tokens are unavailable.
    if not claims and settings.auth_dev_bypass and settings.env in {"development", "test"}:
        claims = _get_unverified_claims(token)

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing sub")

    request.state.user_id = sub
    request.state.auth_claims = claims
    role = _resolve_claim_role(claims)
    return AuthenticatedUser(
        id=sub,
        email=claims.get("email"),
        role=role,
        is_admin=_claims_include_admin(claims),
    )


def _resolve_claim_role(claims: dict[str, Any]) -> str:
    app_metadata = claims.get("app_metadata")
    user_metadata = claims.get("user_metadata")
    for value in (
        claims.get("role"),
        app_metadata.get("role") if isinstance(app_metadata, dict) else None,
        user_metadata.get("role") if isinstance(user_metadata, dict) else None,
    ):
        if isinstance(value, str) and value.strip():
            return value
    return "authenticated"


def _claims_include_admin(claims: dict[str, Any]) -> bool:
    app_metadata = claims.get("app_metadata")
    user_metadata = claims.get("user_metadata")
    candidates: list[Any] = [
        claims.get("role"),
        claims.get("roles"),
        app_metadata.get("role") if isinstance(app_metadata, dict) else None,
        app_metadata.get("roles") if isinstance(app_metadata, dict) else None,
        app_metadata.get("is_admin") if isinstance(app_metadata, dict) else None,
        user_metadata.get("role") if isinstance(user_metadata, dict) else None,
        user_metadata.get("roles") if isinstance(user_metadata, dict) else None,
        user_metadata.get("is_admin") if isinstance(user_metadata, dict) else None,
    ]
    for candidate in candidates:
        if candidate is True:
            return True
        if isinstance(candidate, str) and candidate.lower() in {"admin", "aventi_admin", "owner"}:
            return True
        if isinstance(candidate, list) and any(
            isinstance(item, str) and item.lower() in {"admin", "aventi_admin", "owner"}
            for item in candidate
        ):
            return True
    return False


async def require_admin_user(user: AuthenticatedUser = Depends(require_user)) -> AuthenticatedUser:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return user


def require_internal_api_key(request: Request, settings: Settings = Depends(get_settings)) -> None:
    provided = request.headers.get("x-aventi-internal-key")
    if not settings.internal_api_key or provided != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
