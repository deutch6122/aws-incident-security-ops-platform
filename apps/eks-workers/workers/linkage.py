"""A->B linkage for Cronjob_Summary (Requirement 14.1, 14.2, 14.3).

The monthly-summary CronJob is the ONLY execution subject of the A->B linkage
(design.md "A->B 連携の実行主体は Cronjob_Summary に限定"). After the monthly
summary is upserted into Aurora (Product_A), this module derives a NON-SENSITIVE
report from that summary and reflects it into Product_B:

* a report file placed under Portal_Storage ``reports/<period>/summary.json``,
* a ``report_metadata`` entry (report_id / period / title / s3_key ...),
* a ``public_status_items`` entry (period-based, non-sensitive overview).

DIRECTIONALITY (Requirement 14.3): linkage is a ONE-WAY hand-off A -> B. This
module defines only WRITE ports INTO Product_B. There is intentionally no port,
client, or record that reads from or writes to Product_A (Aurora / RDS /
SQLAlchemy / psycopg). It receives an already-computed MonthlySummaryRecord as a
plain value object and never queries Product_A itself.

NON-SENSITIVE CONTENT (design.md MVP レポートはダミー/非機微のみ): the derived
report exposes only aggregate counts, the period, and a short overview text.
Product_A sensitive material -- incident detail bodies, finding detail, DB
values, secrets, PII -- is never read here (the input record carries none) and
never written out.

IDEMPOTENCY / OVERWRITE POLICY (same period re-run does not duplicate):
* report_metadata is keyed on report_id (derived deterministically from period),
  upsert overwrites in place.
* public_status_items is keyed on status_id (derived from period, contains no
  "/"), upsert overwrites in place.
* the S3 object key is deterministic per period, so a re-run overwrites the same
  key rather than creating a new object.

All AWS I/O is lazy / behind Protocols: importing this module performs no AWS
I/O. Runtime uses boto3-backed adapters; tests use the in-memory fakes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from workers.stores import MonthlySummaryRecord
from workers.summary import validate_period

# S3 prefix under Portal_Storage where report files are placed (design: reports/*).
REPORTS_PREFIX = "reports"

# Fixed, non-sensitive vocabulary. Overview text is templated from counts only.
STATUS_STATE_OPERATIONAL = "operational"


# ---------------------------------------------------------------------------
# Derived (non-sensitive) linkage payloads
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class LinkageReport:
    """The non-sensitive report derived from a monthly summary.

    Contains ONLY the period, aggregate counts, and a generated overview string.
    No incident/finding detail text, DB value, secret, or PII is present.
    """

    report_id: str
    period: str
    title: str
    s3_key: str
    incident_count: int
    finding_count: int
    alarm_count: int
    overview: str

    def report_body(self) -> dict[str, Any]:
        """The JSON body written to Portal_Storage (non-sensitive)."""
        return {
            "report_id": self.report_id,
            "period": self.period,
            "title": self.title,
            "incident_count": self.incident_count,
            "finding_count": self.finding_count,
            "alarm_count": self.alarm_count,
            "overview": self.overview,
        }

    def report_metadata_item(self) -> dict[str, Any]:
        """The report_metadata entry (non-sensitive meta only)."""
        return {
            "report_id": self.report_id,
            "period": self.period,
            "title": self.title,
            "s3_key": self.s3_key,
        }

    def public_status_item(self) -> dict[str, Any]:
        """The public_status_items entry (period-based, non-sensitive overview).

        status_id is derived from the period and contains NO "/" so it is safe as
        a ``/api/status/{id}`` path parameter.
        """
        return {
            "status_id": public_status_id(self.period),
            "period": self.period,
            "title": self.title,
            "state": STATUS_STATE_OPERATIONAL,
            "incident_count": self.incident_count,
            "overview": self.overview,
        }


def report_id_of(period: str) -> str:
    """Deterministic report_id for a period (keyed for overwrite, no "/")."""
    return f"summary-{validate_period(period)}"


def public_status_id(period: str) -> str:
    """Deterministic status_id for a period.

    Hyphen form (e.g. ``status-202406``) so it never contains "/" and is safe as
    a ``/api/status/{id}`` path parameter (no encoding needed).
    """
    return f"status-{validate_period(period)}"


def report_s3_key(period: str) -> str:
    """Deterministic Portal_Storage object key: reports/<period>/summary.json."""
    return f"{REPORTS_PREFIX}/{validate_period(period)}/summary.json"


def _overview_text(record: MonthlySummaryRecord) -> str:
    """Templated, non-sensitive overview built only from counts and period."""
    return (
        f"Period {record.period}: {record.incident_count} incidents, "
        f"{record.finding_count} findings, {record.alarm_count} alarm events."
    )


def build_linkage_report(record: MonthlySummaryRecord) -> LinkageReport:
    """Derive the non-sensitive LinkageReport from a monthly summary record.

    Only aggregate counts + period are copied. ``record.detail`` (which could in
    principle carry richer data) is deliberately NOT propagated, keeping the
    output non-sensitive.
    """
    period = validate_period(record.period)
    return LinkageReport(
        report_id=report_id_of(period),
        period=period,
        title=f"Monthly Operations Summary {period}",
        s3_key=report_s3_key(period),
        incident_count=record.incident_count,
        finding_count=record.finding_count,
        alarm_count=record.alarm_count,
        overview=_overview_text(record),
    )


# ---------------------------------------------------------------------------
# Product_B write ports (one-way A -> B only)
# ---------------------------------------------------------------------------
class PortalStoragePort(Protocol):
    """Writes a report object under Portal_Storage reports/* (write-only)."""

    def put_report(self, key: str, body: bytes) -> None:
        """Put (overwrite) the object at ``key`` in Portal_Storage."""


class ReportMetadataWriterPort(Protocol):
    """Upserts a report_metadata entry keyed on report_id (write-only)."""

    def upsert_report(self, item: dict[str, Any]) -> None: ...


class PublicStatusWriterPort(Protocol):
    """Upserts a public_status_items entry keyed on status_id (write-only)."""

    def upsert_status(self, item: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# In-memory fakes (overwrite semantics on the key -> no duplicates on re-run)
# ---------------------------------------------------------------------------
@dataclass
class InMemoryPortalStorage:
    """Keyed on object key. Re-running the same period overwrites the object."""

    _objects: dict[str, bytes] = field(default_factory=dict)

    def put_report(self, key: str, body: bytes) -> None:
        self._objects[key] = body

    def count(self) -> int:
        return len(self._objects)

    def keys(self) -> list[str]:
        return list(self._objects.keys())

    def get(self, key: str) -> bytes | None:
        return self._objects.get(key)


@dataclass
class InMemoryReportMetadataWriter:
    """Keyed on report_id. Re-running the same period overwrites the entry."""

    _rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert_report(self, item: dict[str, Any]) -> None:
        self._rows[str(item["report_id"])] = dict(item)

    def count(self) -> int:
        return len(self._rows)

    def get(self, report_id: str) -> dict[str, Any] | None:
        row = self._rows.get(report_id)
        return dict(row) if row is not None else None


@dataclass
class InMemoryPublicStatusWriter:
    """Keyed on status_id. Re-running the same period overwrites the entry."""

    _rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert_status(self, item: dict[str, Any]) -> None:
        self._rows[str(item["status_id"])] = dict(item)

    def count(self) -> int:
        return len(self._rows)

    def get(self, status_id: str) -> dict[str, Any] | None:
        row = self._rows.get(status_id)
        return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Linkage orchestration
# ---------------------------------------------------------------------------
def link_summary_to_portal(
    record: MonthlySummaryRecord,
    *,
    storage: PortalStoragePort,
    report_writer: ReportMetadataWriterPort,
    status_writer: PublicStatusWriterPort,
) -> LinkageReport:
    """Reflect a monthly summary into Product_B (one-way A -> B).

    Derives the non-sensitive report, places the report file under
    reports/<period>/summary.json, upserts report_metadata (report_id key) and
    public_status_items (status_id key). All three writes use deterministic keys,
    so re-running the same period overwrites rather than duplicating.
    """
    report = build_linkage_report(record)
    body = json.dumps(report.report_body(), ensure_ascii=False, sort_keys=True).encode("utf-8")

    storage.put_report(report.s3_key, body)
    report_writer.upsert_report(report.report_metadata_item())
    status_writer.upsert_status(report.public_status_item())
    return report
