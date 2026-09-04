"""Fail-closed internal bearer authentication and correlation-ID middleware."""

from __future__ import annotations

import hmac
import re
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from pydantic import SecretStr

_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Task 7 protected prefix retained for backward compatibility with existing tests.
PROTECTED_PREFIX = "/_contracts"

# Task 8 business API prefixes are also authentication-required (Req 2.3).
BUSINESS_PROTECTED_PREFIXES: tuple[str, ...] = (
    "/dashboard",
    "/incidents",
    "/findings",
    "/summaries",
)

# All request-time protected prefixes (Task 7 contract routes + Task 8 business routes).
PROTECTED_PREFIXES: tuple[str, ...] = (PROTECTED_PREFIX,) + BUSINESS_PROTECTED_PREFIXES

# Paths that remain publicly reachable (health probes and OpenAPI/Swagger docs, Req 26.2).
PUBLIC_PATHS: frozenset[str] = frozenset(
    {"/", "/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
)

bearer_scheme = HTTPBearer(auto_error=False)


def choose_correlation_id(candidate: str | None) -> str:
    if candidate is not None and _CORRELATION_ID.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _token_matches(configured: SecretStr | None, supplied: str) -> bool:
    if configured is None:
        return False
    expected = configured.get_secret_value().encode("utf-8")
    provided = supplied.encode("utf-8")
    return hmac.compare_digest(expected, provided)


def parse_authorization(header: str | None) -> str | None:
    if header is None:
        return None
    scheme, separator, credential = header.partition(" ")
    if not separator or scheme.lower() != "bearer" or not credential or " " in credential:
        return None
    return credential


def unauthorized_response(correlation_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": {"code": "unauthorized", "message": "Bearer authentication is required"},
            "correlation_id": correlation_id,
        },
        headers={"WWW-Authenticate": "Bearer", "X-Correlation-ID": correlation_id},
    )


async def require_bearer_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    """OpenAPI security dependency; middleware already enforces it before validation."""

    token = credentials.credentials if credentials is not None else ""
    if credentials is None or credentials.scheme.lower() != "bearer" or not _token_matches(
        request.app.state.settings.internal_bearer_token, token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )


def is_public_path(path: str) -> bool:
    """Explicit allowlist of endpoints that never require authentication."""

    return path in PUBLIC_PATHS


def is_protected_path(path: str) -> bool:
    """True when a request path must present valid bearer credentials.

    Covers the Task 7 ``/_contracts`` routes and the Task 8 business API
    prefixes (``/dashboard``, ``/incidents``, ``/findings``, ``/summaries``).
    Public health/docs endpoints are never treated as protected.
    """

    if is_public_path(path):
        return False
    return any(path == prefix or path.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES)
