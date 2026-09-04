"""Reusable safe HTTP errors and FastAPI exception handlers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("backend_api")


class NotFoundError(LookupError):
    def __init__(self, resource: str, identifier: str | int) -> None:
        self.resource = resource
        self.identifier = str(identifier)
        super().__init__(f"{resource} was not found")


def correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unavailable")


def error_response(request: Request, status_code: int, code: str, message: str, **details: Any) -> JSONResponse:
    cid = correlation_id(request)
    body: dict[str, Any] = {
        "error": {"code": code, "message": message, **details},
        "correlation_id": cid,
    }
    return JSONResponse(status_code=status_code, content=body, headers={"X-Correlation-ID": cid})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        missing_fields = sorted(
            {
                str(error["loc"][-1])
                for error in exc.errors()
                if error.get("type") == "missing" and error.get("loc")
            }
        )
        details: dict[str, Any] = {}
        if missing_fields:
            details["missing_fields"] = missing_fields
        return error_response(request, 400, "invalid_request", "Request validation failed", **details)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return error_response(
            request,
            404,
            "not_found",
            f"{exc.resource} was not found",
            resource=exc.resource,
            identifier=exc.identifier,
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled application error correlation_id=%s path=%s error_type=%s",
            correlation_id(request),
            request.url.path,
            type(exc).__name__,
        )
        return error_response(request, 500, "internal_error", "An unexpected error occurred")
