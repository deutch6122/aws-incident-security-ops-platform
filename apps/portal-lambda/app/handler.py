"""Portal_API Lambda handler for API Gateway HTTP API v2 (payload format 2.0).

Routing uses ``routeKey`` when present and falls back to ``rawPath`` + method.
Every route requires a valid authenticated Viewer (fail-closed 401 on missing or
malformed JWT claims). page_view_logs is written only on successful status views.

The module exposes:
* ``lambda_handler`` — the AWS entry point. It builds the DynamoDB-backed
  services lazily (no AWS I/O at import time) and delegates to ``PortalApi``.
* ``PortalApi`` — a routing object built from the repository Protocols, so tests
  inject in-memory fakes and never touch AWS.

SEPARATION NOTE: the handler only ever calls Product_B services (status/report).
It never imports or calls anything in Product_A (Backend API/Aurora/ECS/EKS/
Product_A SQS).
"""

from __future__ import annotations

import re
from typing import Any

from app.auth import Unauthorized, extract_viewer
from app.config import PortalSettings
from app.errors import ApiError, error_response, json_response
from app.services import ReportService, StatusService
from app.stores import (
    PageViewLogRepository,
    PublicStatusRepository,
    ReportMetadataRepository,
)

_STATUS_DETAIL_RE = re.compile(r"^/api/status/(?P<id>[^/]+)$")
_REPORT_DETAIL_RE = re.compile(r"^/api/reports/(?P<id>[^/]+)$")


def _method_and_path(event: dict[str, Any]) -> tuple[str, str]:
    """Resolve (method, path) from routeKey, else rawPath + http.method."""
    route_key = event.get("routeKey")
    if isinstance(route_key, str) and route_key not in ("", "$default"):
        parts = route_key.split(" ", 1)
        if len(parts) == 2:
            return parts[0].upper(), parts[1]

    request_context = event.get("requestContext")
    method = ""
    if isinstance(request_context, dict):
        http = request_context.get("http")
        if isinstance(http, dict):
            method = str(http.get("method", ""))
    raw_path = str(event.get("rawPath", ""))
    return method.upper(), raw_path


class PortalApi:
    """Routes authenticated requests to the status and report services."""

    def __init__(
        self,
        status_repo: PublicStatusRepository,
        report_repo: ReportMetadataRepository,
        page_view_repo: PageViewLogRepository,
        settings: PortalSettings,
    ) -> None:
        self._status_service = StatusService(status_repo, page_view_repo, settings)
        self._report_service = ReportService(report_repo)

    def handle(self, event: dict[str, Any]) -> dict[str, Any]:
        # Fail closed: any missing/malformed JWT claim is a 401 and writes
        # nothing (Requirement 9.3).
        try:
            viewer = extract_viewer(event)
        except Unauthorized:
            return error_response(401, "unauthorized")

        method, path = _method_and_path(event)

        try:
            return self._route(viewer, method, path)
        except ApiError as exc:
            return error_response(exc.status_code, exc.message)

    def _route(self, viewer: Any, method: str, path: str) -> dict[str, Any]:
        if method != "GET":
            return error_response(404, "not found")

        if path == "/api/status":
            return json_response(200, {"items": self._status_service.list_status(viewer)})

        status_match = _STATUS_DETAIL_RE.match(path)
        if status_match:
            item = self._status_service.get_status(viewer, status_match.group("id"))
            return json_response(200, item)

        if path == "/api/reports":
            return json_response(200, {"reports": self._report_service.list_reports(viewer)})

        report_match = _REPORT_DETAIL_RE.match(path)
        if report_match:
            report = self._report_service.get_report(viewer, report_match.group("id"))
            return json_response(200, report)

        return error_response(404, "not found")


def _build_api_from_environment() -> PortalApi:
    """Build a DynamoDB-backed PortalApi lazily (no AWS I/O until a table call)."""
    from app.repositories import (
        DynamoPageViewLogRepository,
        DynamoPublicStatusRepository,
        DynamoReportMetadataRepository,
        DynamoResourceProvider,
    )

    settings = PortalSettings.from_env()
    provider = DynamoResourceProvider(settings)
    return PortalApi(
        status_repo=DynamoPublicStatusRepository(provider, settings),
        report_repo=DynamoReportMetadataRepository(provider, settings),
        page_view_repo=DynamoPageViewLogRepository(provider, settings),
        settings=settings,
    )


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entry point. Builds services on invocation, not at import."""
    api = _build_api_from_environment()
    return api.handle(event)
