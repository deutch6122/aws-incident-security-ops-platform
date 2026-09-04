"""HTTP error type and JSON response helpers for the Portal_API.

The handler returns API Gateway HTTP API v2 proxy responses (statusCode + JSON
body). No secret, token, or credential value is placed in any response body.
"""

from __future__ import annotations

import json
from typing import Any


class ApiError(Exception):
    """An error carrying an HTTP status code and a safe client message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def not_found(message: str = "not found") -> ApiError:
    return ApiError(404, message)


def json_response(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False, default=str),
    }


def error_response(status_code: int, message: str) -> dict[str, Any]:
    return json_response(status_code, {"error": message})
