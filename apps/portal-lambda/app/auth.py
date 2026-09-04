"""JWT claim verification for the Portal_API (Requirement 9.3).

An API Gateway Cognito JWT Authorizer (Task 14) sits in front of the Lambda and
validates token signatures/expiry. This module does NOT re-verify signatures; it
performs a fail-closed check on the claims the authorizer forwards inside the
HTTP API v2 event (``requestContext.authorizer.jwt.claims``).

Policy: if the claims are missing, empty, or malformed, treat the request as
unauthenticated and return 401 (fail closed). Valid claims identify the caller as
a Viewer. No token, header, or credential value is ever logged or echoed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class Unauthorized(Exception):
    """Raised when a request has no usable authenticated Viewer identity."""


@dataclass(frozen=True, slots=True)
class Viewer:
    """The authenticated Viewer derived from JWT claims."""

    subject: str


# Claim keys that can carry a stable subject identifier, in preference order.
_SUBJECT_CLAIMS = ("sub", "cognito:username", "username", "email")


def extract_viewer(event: dict[str, Any]) -> Viewer:
    """Return the Viewer for a request or raise Unauthorized (fail closed).

    The event is API Gateway HTTP API v2 (payload format 2.0). Claims live at
    ``requestContext.authorizer.jwt.claims``. Anything missing or malformed on
    that path means "not a valid authenticated Viewer" -> 401.
    """

    if not isinstance(event, dict):
        raise Unauthorized("missing request context")

    request_context = event.get("requestContext")
    if not isinstance(request_context, dict):
        raise Unauthorized("missing request context")

    authorizer = request_context.get("authorizer")
    if not isinstance(authorizer, dict):
        raise Unauthorized("missing authorizer context")

    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        raise Unauthorized("missing jwt authorizer context")

    claims = jwt.get("claims")
    if not isinstance(claims, dict) or not claims:
        raise Unauthorized("missing jwt claims")

    for key in _SUBJECT_CLAIMS:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return Viewer(subject=value.strip())

    raise Unauthorized("jwt claims do not identify a subject")
