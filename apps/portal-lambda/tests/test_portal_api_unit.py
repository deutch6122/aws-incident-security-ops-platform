"""Task 15.5 Portal_API unit tests (fake-backed, no AWS/Docker/moto).

Covers: JWT missing 401, JWT malformed-claims 401, status list, status detail,
status not-found 404, reports list, report detail, report not-found 404, view
logging, public_status_items body immutability.

Testing substitution note: tasks.md 15.5 lists moto / DynamoDB Local as
optional. Per the execution constraints these tests use the in-memory Portal_DB
stores from app.stores.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests._helpers import VALID_CLAIMS, build_api, build_stores, event

STATUS_ITEMS = [
    {"status_id": "s-1", "title": "API latency", "severity": "high", "state": "investigating"},
    {"status_id": "s-2", "title": "DB failover", "severity": "critical", "state": "resolved"},
]
REPORTS = [
    {
        "report_id": "r-202401",
        "period": "202401",
        "title": "January report",
        "s3_key": "reports/202401/summary.pdf",
    },
    {
        "report_id": "r-202402",
        "period": "202402",
        "title": "February report",
        "s3_key": "reports/202402/summary.pdf",
    },
]


def _api():
    status, reports, views = build_stores(status_items=STATUS_ITEMS, reports=REPORTS)
    return build_api(status, reports, views), status, views


# --- authentication (Requirement 9.3) --------------------------------------
def test_missing_jwt_returns_401_and_writes_no_log() -> None:
    api, _status, views = _api()
    resp = api.handle(event("GET", "/api/status", claims=None))
    assert resp["statusCode"] == 401
    assert views.count() == 0


def test_malformed_claims_returns_401_and_writes_no_log() -> None:
    api, _status, views = _api()
    # Empty claims and non-subject claims are both fail-closed 401.
    for bad in ({}, {"scope": "read"}, {"sub": "   "}):
        resp = api.handle(event("GET", "/api/status", claims=bad))
        assert resp["statusCode"] == 401
    assert views.count() == 0


# --- status list / detail (Requirement 10.1, 10.2) -------------------------
def test_status_list_returns_all_items() -> None:
    api, _status, _views = _api()
    resp = api.handle(event("GET", "/api/status", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 200
    assert '"s-1"' in resp["body"] and '"s-2"' in resp["body"]


def test_status_detail_returns_item() -> None:
    api, _status, _views = _api()
    resp = api.handle(event("GET", "/api/status/s-1", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 200
    assert '"API latency"' in resp["body"]


def test_status_detail_unknown_id_returns_404_and_writes_no_log() -> None:
    api, _status, views = _api()
    resp = api.handle(event("GET", "/api/status/does-not-exist", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 404
    assert views.count() == 0


# --- reports list / detail (Requirement 11.1, 11.2, 11.3) ------------------
def test_reports_list_returns_all_reports() -> None:
    api, _status, _views = _api()
    resp = api.handle(event("GET", "/api/reports", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 200
    assert '"r-202401"' in resp["body"] and '"r-202402"' in resp["body"]


def test_report_detail_returns_meta_and_file_reference() -> None:
    api, _status, _views = _api()
    resp = api.handle(event("GET", "/api/reports/r-202401", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 200
    # Metadata includes the Portal_Storage object reference (no S3 access here).
    assert "reports/202401/summary.pdf" in resp["body"]


def test_report_detail_unknown_id_returns_404() -> None:
    api, _status, _views = _api()
    resp = api.handle(event("GET", "/api/reports/r-nope", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 404


# --- view logging + immutability (Requirement 10.3) ------------------------
def test_view_records_exactly_one_log_per_read() -> None:
    api, _status, views = _api()
    api.handle(event("GET", "/api/status", claims=VALID_CLAIMS))
    assert views.count() == 1
    api.handle(event("GET", "/api/status/s-1", claims=VALID_CLAIMS))
    assert views.count() == 2

    logs = views.all()
    assert {log.view_type for log in logs} == {"status_list", "status_detail"}
    detail_log = next(log for log in logs if log.view_type == "status_detail")
    assert detail_log.target_id == "s-1"
    assert detail_log.viewer == "viewer-123"


def test_public_status_items_body_unchanged_by_views() -> None:
    api, status, _views = _api()
    before = status.snapshot_all()
    api.handle(event("GET", "/api/status", claims=VALID_CLAIMS))
    api.handle(event("GET", "/api/status/s-2", claims=VALID_CLAIMS))
    assert status.snapshot_all() == before


# --- routing fallback: rawPath + method without routeKey -------------------
def test_routing_falls_back_to_raw_path_and_method() -> None:
    api, _status, _views = _api()
    resp = api.handle(event("GET", "/api/status/s-1", claims=VALID_CLAIMS, use_route_key=False))
    assert resp["statusCode"] == 200
