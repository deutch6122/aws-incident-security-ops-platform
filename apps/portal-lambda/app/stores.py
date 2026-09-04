"""Repository ports and in-memory fakes for Portal_DB (Product_B) access.

The repository Protocols describe exactly what the Portal_API needs against the
four DynamoDB tables. Two implementations satisfy them:

* ``app.repositories`` — the DynamoDB (boto3) implementation used at runtime.
* the in-memory fakes here — a dependency-free substitute so unit and property
  tests run without AWS, Docker, moto, or DynamoDB Local.

TESTING SUBSTITUTION NOTE: tasks.md 15.3/15.5 mention moto / DynamoDB Local as
optional. Per the execution constraints (no Docker, no new installs), the
fake-based tests use these in-memory stores. They mirror the DynamoDB item
shapes and the single-write invariant (page_view_logs append-only, status/report
tables read-only), so they exercise the same behaviour the DynamoDB layer must
guarantee.

SEPARATION NOTE: these ports touch Product_B tables only
(public_status_items / report_metadata / page_view_logs / maintenance_windows).
There is no port or record here for any Product_A store (Aurora/RDS/ECS/EKS/
Product_A SQS). The only write path is appending to page_view_logs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Records (plain value objects; DynamoDB items are plain dicts)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class PageViewLogRecord:
    """One append-only view record written to page_view_logs (Requirement 10.3)."""

    view_id: str
    viewer: str
    view_type: str  # "status_list" | "status_detail"
    target_id: str | None
    viewed_at: str
    expires_at: int


# ---------------------------------------------------------------------------
# Repository ports
# ---------------------------------------------------------------------------
class PublicStatusRepository(Protocol):
    def list_items(self) -> list[dict[str, Any]]:
        """Return all public_status_items (read-only)."""

    def get_item(self, status_id: str) -> dict[str, Any] | None:
        """Return one public_status_items entry, or None if absent (read-only)."""


class ReportMetadataRepository(Protocol):
    def list_reports(self) -> list[dict[str, Any]]:
        """Return all report_metadata entries (read-only)."""

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        """Return one report_metadata entry, or None if absent (read-only)."""


class PageViewLogRepository(Protocol):
    def append(self, record: PageViewLogRecord) -> None:
        """Append exactly one view record (the only Portal_API write path)."""

    def count(self) -> int: ...


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------
@dataclass
class InMemoryPublicStatusStore:
    """Read-only view over public_status_items keyed on status_id.

    Returned items are deep copies so callers cannot mutate the backing store —
    this mirrors DynamoDB returning fresh item dicts and makes the Property 10
    "body is unchanged" invariant meaningful.
    """

    _rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def seed(self, item: dict[str, Any]) -> None:
        self._rows[str(item["status_id"])] = copy.deepcopy(item)

    def list_items(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(row) for row in self._rows.values()]

    def get_item(self, status_id: str) -> dict[str, Any] | None:
        row = self._rows.get(status_id)
        return copy.deepcopy(row) if row is not None else None

    def snapshot(self, status_id: str) -> dict[str, Any] | None:
        """Test helper: current stored body for equality checks (deep copy)."""
        row = self._rows.get(status_id)
        return copy.deepcopy(row) if row is not None else None

    def snapshot_all(self) -> dict[str, dict[str, Any]]:
        return copy.deepcopy(self._rows)


@dataclass
class InMemoryReportMetadataStore:
    """Read-only view over report_metadata keyed on report_id."""

    _rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def seed(self, item: dict[str, Any]) -> None:
        self._rows[str(item["report_id"])] = copy.deepcopy(item)

    def list_reports(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(row) for row in self._rows.values()]

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        row = self._rows.get(report_id)
        return copy.deepcopy(row) if row is not None else None


@dataclass
class InMemoryPageViewLogStore:
    """Append-only page_view_logs fake keyed on view_id."""

    _rows: dict[str, PageViewLogRecord] = field(default_factory=dict)

    def append(self, record: PageViewLogRecord) -> None:
        if record.view_id in self._rows:
            # view_id is a unique key; a duplicate would be a bug in id generation.
            raise ValueError("duplicate view_id")
        self._rows[record.view_id] = record

    def count(self) -> int:
        return len(self._rows)

    def all(self) -> list[PageViewLogRecord]:
        return list(self._rows.values())
