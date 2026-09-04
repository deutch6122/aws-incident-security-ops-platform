# Feature: aws-incident-security-ops-platform, Property 10: For any 認証済み Viewer による障害ステータス閲覧または障害詳細閲覧について、閲覧操作の後に page_view_logs のレコードはちょうど 1 件増加し、かつ閲覧対象の public_status_items 本体は変更されてはならない
# **Validates: Requirements 10.3**
"""Property 10: viewing side-effect invariant.

For any authenticated Viewer reading the status list or a status detail, exactly
one page_view_logs record is added and the viewed public_status_items body is
unchanged.

Testing substitution note: tasks.md 15.3 lists moto / DynamoDB Local as
optional. Per the execution constraints (no Docker / no new installs), this
property uses the in-memory Portal_DB stores (app.stores), which mirror the
DynamoDB item shapes and the append-only page_view_logs / read-only
public_status_items behaviour. This fake-based property is never skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests._helpers import VALID_CLAIMS, build_api, build_stores, event

# Smart generators constrained to the public_status_items input space.
# status_id is addressed as a single URL path segment (GET /api/status/{id}), so
# it must be a non-empty value containing no '/' — the same constraint a real API
# Gateway path parameter imposes. Slash-bearing ids are out of the addressable
# input space for detail views and are excluded here.
_status_ids = st.text(min_size=1, max_size=24).filter(
    lambda s: s.strip() != "" and "/" not in s
)
_words = st.text(min_size=0, max_size=30)
_severities = st.sampled_from(["low", "medium", "high", "critical"])
_states = st.sampled_from(["investigating", "identified", "monitoring", "resolved"])


@st.composite
def _status_item(draw) -> dict:
    return {
        "status_id": draw(_status_ids),
        "title": draw(_words),
        "severity": draw(_severities),
        "state": draw(_states),
        "detail": draw(_words),
    }


@st.composite
def _unique_items(draw) -> list[dict]:
    items = draw(st.lists(_status_item(), min_size=1, max_size=8))
    seen: dict[str, dict] = {}
    for item in items:
        seen[item["status_id"].strip()] = {**item, "status_id": item["status_id"].strip()}
    return list(seen.values())


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(items=_unique_items(), detail_index=st.integers(min_value=0, max_value=7))
def test_status_view_adds_exactly_one_log_and_leaves_body_unchanged(
    items: list[dict], detail_index: int
) -> None:
    status, reports, views = build_stores(status_items=items)
    api = build_api(status, reports, views)

    before_bodies = status.snapshot_all()
    before_count = views.count()

    # --- list view: exactly one new log, all bodies unchanged ---
    resp = api.handle(event("GET", "/api/status", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 200
    assert views.count() == before_count + 1
    assert status.snapshot_all() == before_bodies

    # --- detail view of an existing item: exactly one more log, body unchanged ---
    target = items[detail_index % len(items)]["status_id"]
    body_before = status.snapshot(target)
    count_before_detail = views.count()

    resp = api.handle(event("GET", f"/api/status/{target}", claims=VALID_CLAIMS))
    assert resp["statusCode"] == 200
    assert views.count() == count_before_detail + 1
    # The viewed item's body is untouched by the read.
    assert status.snapshot(target) == body_before
    # And the whole table is unchanged as well.
    assert status.snapshot_all() == before_bodies
