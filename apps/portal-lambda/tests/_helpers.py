"""Shared test helpers: fake-backed PortalApi and HTTP API v2 event builders.

These keep the tests free of AWS/Docker/moto by wiring the in-memory stores from
``app.stores`` into ``app.handler.PortalApi``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import PortalSettings
from app.handler import PortalApi
from app.stores import (
    InMemoryPageViewLogStore,
    InMemoryPublicStatusStore,
    InMemoryReportMetadataStore,
)


def build_stores(
    status_items: list[dict[str, Any]] | None = None,
    reports: list[dict[str, Any]] | None = None,
) -> tuple[InMemoryPublicStatusStore, InMemoryReportMetadataStore, InMemoryPageViewLogStore]:
    status = InMemoryPublicStatusStore()
    for item in status_items or []:
        status.seed(item)
    report_store = InMemoryReportMetadataStore()
    for report in reports or []:
        report_store.seed(report)
    return status, report_store, InMemoryPageViewLogStore()


def build_api(
    status: InMemoryPublicStatusStore,
    reports: InMemoryReportMetadataStore,
    views: InMemoryPageViewLogStore,
    settings: PortalSettings | None = None,
) -> PortalApi:
    return PortalApi(status, reports, views, settings or PortalSettings())


def event(
    method: str,
    path: str,
    *,
    claims: dict[str, Any] | None = None,
    use_route_key: bool = True,
) -> dict[str, Any]:
    """Build a minimal API Gateway HTTP API v2 (payload 2.0) event.

    When ``claims`` is None, no jwt authorizer context is attached (simulating a
    missing/failed authorizer). Note: no Authorization header or token value is
    ever constructed here.
    """
    evt: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"http": {"method": method, "path": path}},
    }
    if use_route_key:
        evt["routeKey"] = f"{method} {path}"
    if claims is not None:
        evt["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    return evt


VALID_CLAIMS = {"sub": "viewer-123", "cognito:username": "viewer-one"}
