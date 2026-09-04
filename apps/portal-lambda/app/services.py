"""Portal_API business services: status viewing and report reading.

These services depend only on the repository Protocols in ``app.stores`` and the
``Viewer`` from ``app.auth``, so they run identically against the DynamoDB
repositories and the in-memory fakes.

Key invariants (Requirement 10.3, Property 10):
* Viewing the status list or a status detail appends EXACTLY ONE page_view_logs
  record.
* The viewed public_status_items body is only read, never modified.

The service is constructed with an ``id_factory`` and ``clock`` so tests get
deterministic view ids/timestamps and property tests stay pure.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from app.auth import Viewer
from app.config import PortalSettings
from app.errors import not_found
from app.stores import (
    PageViewLogRecord,
    PageViewLogRepository,
    PublicStatusRepository,
    ReportMetadataRepository,
)

VIEW_STATUS_LIST = "status_list"
VIEW_STATUS_DETAIL = "status_detail"


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class StatusService:
    """Serves public_status_items and records exactly one view per read."""

    def __init__(
        self,
        status_repo: PublicStatusRepository,
        page_view_repo: PageViewLogRepository,
        settings: PortalSettings,
        *,
        id_factory: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._status = status_repo
        self._views = page_view_repo
        self._settings = settings
        self._id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self._clock = clock or _default_now

    def list_status(self, viewer: Viewer) -> list[dict[str, Any]]:
        """Return the status list and record a single list view."""
        items = self._status.list_items()
        self._record_view(viewer, VIEW_STATUS_LIST, target_id=None)
        return items

    def get_status(self, viewer: Viewer, status_id: str) -> dict[str, Any]:
        """Return one status detail (404 if absent) and record a single view.

        The view is recorded only when the target exists, so a 404 leaves
        page_view_logs unchanged.
        """
        item = self._status.get_item(status_id)
        if item is None:
            raise not_found("status not found")
        self._record_view(viewer, VIEW_STATUS_DETAIL, target_id=status_id)
        return item

    def _record_view(self, viewer: Viewer, view_type: str, *, target_id: str | None) -> None:
        now = self._clock()
        ttl = now + timedelta(days=self._settings.page_view_log_ttl_days)
        record = PageViewLogRecord(
            view_id=self._id_factory(),
            viewer=viewer.subject,
            view_type=view_type,
            target_id=target_id,
            viewed_at=now.isoformat(),
            expires_at=int(ttl.timestamp()),
        )
        self._views.append(record)


class ReportService:
    """Serves report_metadata list and detail (Requirement 11.1, 11.2, 11.3)."""

    def __init__(self, report_repo: ReportMetadataRepository) -> None:
        self._reports = report_repo

    def list_reports(self, viewer: Viewer) -> list[dict[str, Any]]:
        return self._reports.list_reports()

    def get_report(self, viewer: Viewer, report_id: str) -> dict[str, Any]:
        """Return report metadata + Portal_Storage file reference (meta only).

        No S3 access and no signed-URL generation happens here (Task 13 S3/
        CloudFront handles delivery). Only the stored metadata, which includes
        the object key/prefix reference, is returned.
        """
        report = self._reports.get_report(report_id)
        if report is None:
            raise not_found("report not found")
        return report
