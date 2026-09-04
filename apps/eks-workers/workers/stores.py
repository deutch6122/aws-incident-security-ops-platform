"""Repository ports and in-memory fakes for worker persistence.

The repository Protocols describe the idempotent upsert operations the workers
need. Production repositories (SQLAlchemy, ON CONFLICT DO ...) implement the
same Protocols; the in-memory fakes here provide a dependency-free substitute so
unit and property tests run without a database.

NOTE ON TESTING SUBSTITUTION: tasks.md 10.3/10.5/10.7 mention testcontainers.
Per the execution constraints (no Docker / no real DB), the property tests use
these in-memory fakes keyed on the same UNIQUE columns that the DB enforces
(alarm_events.external_id, findings.external_id, monthly_summaries.period). The
fakes replicate ON CONFLICT semantics, so they exercise the same idempotency
invariant the DB UNIQUE constraint guarantees.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Records (plain value objects, independent of SQLAlchemy)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AlarmEventRecord:
    external_id: str
    source: str
    event_type: str
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class FindingRecord:
    external_id: str
    title: str
    severity: str
    resource_type: str | None
    status: str


@dataclass(frozen=True, slots=True)
class TriageRecord:
    triage_status: str
    assessed_severity: str
    note: str | None = None


@dataclass(frozen=True, slots=True)
class MonthlySummaryRecord:
    period: str
    incident_count: int
    finding_count: int
    alarm_count: int
    detail: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Repository ports
# ---------------------------------------------------------------------------
class AlarmEventRepository(Protocol):
    def upsert(self, record: AlarmEventRecord) -> None:
        """Insert the alarm event if external_id is new; otherwise no new row."""

    def count(self) -> int: ...


class FindingRepository(Protocol):
    def upsert_with_triage(self, finding: FindingRecord, triage: TriageRecord) -> None:
        """Insert finding + triage atomically if external_id is new; else no new rows."""

    def finding_count(self) -> int: ...

    def triage_count(self) -> int: ...


class MonthlySummaryRepository(Protocol):
    def upsert(self, record: MonthlySummaryRecord) -> None:
        """Insert or update the single row for record.period (period UNIQUE)."""

    def count(self) -> int: ...


# ---------------------------------------------------------------------------
# In-memory fakes (ON CONFLICT semantics on the UNIQUE key)
# ---------------------------------------------------------------------------
@dataclass
class InMemoryAlarmStore:
    """Keyed on external_id. Re-ingesting the same external_id is a no-op."""

    _rows: dict[str, AlarmEventRecord] = field(default_factory=dict)

    def upsert(self, record: AlarmEventRecord) -> None:
        # ON CONFLICT (external_id) DO NOTHING: keep the first-seen row.
        self._rows.setdefault(record.external_id, record)

    def count(self) -> int:
        return len(self._rows)

    def get(self, external_id: str) -> AlarmEventRecord | None:
        return self._rows.get(external_id)


@dataclass
class InMemoryFindingStore:
    """Keyed on findings.external_id. Triage is stored consistently with its finding."""

    _findings: dict[str, FindingRecord] = field(default_factory=dict)
    _triage: dict[str, TriageRecord] = field(default_factory=dict)

    def upsert_with_triage(self, finding: FindingRecord, triage: TriageRecord) -> None:
        # ON CONFLICT (external_id) DO NOTHING for the finding, and finding +
        # triage are written together so they are always consistent (both
        # present or both absent).
        if finding.external_id in self._findings:
            return
        self._findings[finding.external_id] = finding
        self._triage[finding.external_id] = triage

    def finding_count(self) -> int:
        return len(self._findings)

    def triage_count(self) -> int:
        return len(self._triage)

    def get_finding(self, external_id: str) -> FindingRecord | None:
        return self._findings.get(external_id)

    def get_triage(self, external_id: str) -> TriageRecord | None:
        return self._triage.get(external_id)


@dataclass
class InMemoryMonthlySummaryStore:
    """Keyed on period. Re-aggregating a period updates the single row in place."""

    _rows: dict[str, MonthlySummaryRecord] = field(default_factory=dict)

    def upsert(self, record: MonthlySummaryRecord) -> None:
        # ON CONFLICT (period) DO UPDATE: replace with the latest values.
        self._rows[record.period] = replace(record)

    def count(self) -> int:
        return len(self._rows)

    def get(self, period: str) -> MonthlySummaryRecord | None:
        return self._rows.get(period)
