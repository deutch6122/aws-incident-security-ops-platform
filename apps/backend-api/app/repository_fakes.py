"""In-memory fake repositories and provider for testing the business APIs.

These fakes require no database or AWS access. They mirror the observable
behaviour of the SQLAlchemy repositories (auto-increment ids, unique
external_id, status counts, audit-log append) closely enough to exercise the
routers end to end via FastAPI's TestClient.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.repository_ports import RepositoryBundle


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FakeIncident:
    id: int
    external_id: str
    title: str
    severity: str
    status: str = "open"
    description: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class FakeIncidentComment:
    id: int
    incident_id: int
    author: str
    body: str
    created_at: datetime = field(default_factory=_now)


@dataclass
class FakeFinding:
    id: int
    external_id: str
    title: str
    severity: str
    resource_type: str | None = None
    status: str = "new"
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


@dataclass
class FakeFindingTriage:
    id: int
    finding_id: int
    triage_status: str
    assessed_severity: str
    note: str | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass
class FakeMonthlySummary:
    id: int
    period: str
    incident_count: int
    finding_count: int
    alarm_count: int
    detail: dict[str, Any] | None = None
    generated_at: datetime = field(default_factory=_now)


@dataclass
class FakeAuditLog:
    id: int
    entity_type: str
    entity_id: int
    action: str
    before_value: dict[str, Any] | None
    after_value: dict[str, Any] | None
    actor: str | None = None
    created_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class FakeStore:
    """Shared mutable state behind all fake repositories."""

    incidents: list[FakeIncident] = field(default_factory=list)
    comments: list[FakeIncidentComment] = field(default_factory=list)
    findings: list[FakeFinding] = field(default_factory=list)
    triage: list[FakeFindingTriage] = field(default_factory=list)
    summaries: list[FakeMonthlySummary] = field(default_factory=list)
    audit_logs: list[FakeAuditLog] = field(default_factory=list)
    _counters: Counter[str] = field(default_factory=Counter)

    def next_id(self, name: str) -> int:
        self._counters[name] += 1
        return self._counters[name]


class FakeIncidentRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def create(
        self,
        *,
        external_id: str,
        title: str,
        severity: str,
        status: str = "open",
        description: str | None = None,
    ) -> FakeIncident:
        if any(item.external_id == external_id for item in self._store.incidents):
            raise ValueError(f"duplicate incident external_id: {external_id}")
        incident = FakeIncident(
            id=self._store.next_id("incident"),
            external_id=external_id,
            title=title,
            severity=severity,
            status=status,
            description=description,
        )
        self._store.incidents.append(incident)
        return incident

    def get(self, incident_id: int) -> FakeIncident | None:
        return next((item for item in self._store.incidents if item.id == incident_id), None)

    def list(self, *, offset: int = 0, limit: int = 100) -> list[FakeIncident]:
        ordered = sorted(self._store.incidents, key=lambda item: item.id)
        return ordered[offset : offset + limit]

    def update(self, incident_id: int, **changes: str | None) -> FakeIncident | None:
        incident = self.get(incident_id)
        if incident is None:
            return None
        allowed = {"title", "severity", "status", "description"}
        for name, value in changes.items():
            if name not in allowed:
                raise ValueError(f"unsupported incident field: {name}")
            setattr(incident, name, value)
        incident.updated_at = _now()
        return incident

    def count_by_status(self) -> dict[str, int]:
        counts = Counter(item.status for item in self._store.incidents)
        return dict(sorted(counts.items()))


class FakeIncidentCommentRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def create(self, *, incident_id: int, author: str, body: str) -> FakeIncidentComment:
        comment = FakeIncidentComment(
            id=self._store.next_id("comment"),
            incident_id=incident_id,
            author=author,
            body=body,
        )
        self._store.comments.append(comment)
        return comment

    def list_for_incident(self, incident_id: int) -> list[FakeIncidentComment]:
        return sorted(
            (item for item in self._store.comments if item.incident_id == incident_id),
            key=lambda item: item.id,
        )


class FakeFindingRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def create(
        self,
        *,
        external_id: str,
        title: str,
        severity: str,
        resource_type: str | None = None,
        status: str = "new",
    ) -> FakeFinding:
        if any(item.external_id == external_id for item in self._store.findings):
            raise ValueError(f"duplicate finding external_id: {external_id}")
        finding = FakeFinding(
            id=self._store.next_id("finding"),
            external_id=external_id,
            title=title,
            severity=severity,
            resource_type=resource_type,
            status=status,
        )
        self._store.findings.append(finding)
        return finding

    def get(self, finding_id: int) -> FakeFinding | None:
        return next((item for item in self._store.findings if item.id == finding_id), None)

    def list(self, *, offset: int = 0, limit: int = 100) -> list[FakeFinding]:
        ordered = sorted(self._store.findings, key=lambda item: item.id)
        return ordered[offset : offset + limit]

    def update(self, finding_id: int, **changes: str | None) -> FakeFinding | None:
        finding = self.get(finding_id)
        if finding is None:
            return None
        allowed = {"title", "severity", "resource_type", "status"}
        for name, value in changes.items():
            if name not in allowed:
                raise ValueError(f"unsupported finding field: {name}")
            setattr(finding, name, value)
        finding.updated_at = _now()
        return finding

    def count_by_status(self) -> dict[str, int]:
        counts = Counter(item.status for item in self._store.findings)
        return dict(sorted(counts.items()))


class FakeFindingTriageRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def create(
        self, *, finding_id: int, triage_status: str, assessed_severity: str, note: str | None = None
    ) -> FakeFindingTriage:
        triage = FakeFindingTriage(
            id=self._store.next_id("triage"),
            finding_id=finding_id,
            triage_status=triage_status,
            assessed_severity=assessed_severity,
            note=note,
        )
        self._store.triage.append(triage)
        return triage

    def list_for_finding(self, finding_id: int) -> list[FakeFindingTriage]:
        return sorted(
            (item for item in self._store.triage if item.finding_id == finding_id),
            key=lambda item: item.id,
        )


class FakeMonthlySummaryRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def create(
        self,
        *,
        period: str,
        incident_count: int,
        finding_count: int,
        alarm_count: int,
        detail: Mapping[str, Any] | None = None,
    ) -> FakeMonthlySummary:
        summary = FakeMonthlySummary(
            id=self._store.next_id("summary"),
            period=period,
            incident_count=incident_count,
            finding_count=finding_count,
            alarm_count=alarm_count,
            detail=dict(detail) if detail is not None else None,
        )
        self._store.summaries.append(summary)
        return summary

    def get_by_period(self, period: str) -> FakeMonthlySummary | None:
        return next((item for item in self._store.summaries if item.period == period), None)


class FakeAuditLogRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    def create(
        self,
        *,
        entity_type: str,
        entity_id: int,
        action: str,
        before_value: Mapping[str, Any] | None,
        after_value: Mapping[str, Any] | None,
        actor: str | None = None,
    ) -> FakeAuditLog:
        log = FakeAuditLog(
            id=self._store.next_id("audit_log"),
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            before_value=dict(before_value) if before_value is not None else None,
            after_value=dict(after_value) if after_value is not None else None,
            actor=actor,
        )
        self._store.audit_logs.append(log)
        return log

    def list_for_entity(self, entity_type: str, entity_id: int) -> list[FakeAuditLog]:
        return sorted(
            (
                item
                for item in self._store.audit_logs
                if item.entity_type == entity_type and item.entity_id == entity_id
            ),
            key=lambda item: item.id,
        )


class InMemoryRepositoryProvider:
    """Provider that binds fake repositories over a single shared store."""

    def __init__(self, store: FakeStore | None = None) -> None:
        self.store = store or FakeStore()

    @contextmanager
    def bundle(self) -> Iterator[RepositoryBundle]:
        yield RepositoryBundle(
            incidents=FakeIncidentRepository(self.store),
            comments=FakeIncidentCommentRepository(self.store),
            findings=FakeFindingRepository(self.store),
            triage=FakeFindingTriageRepository(self.store),
            summaries=FakeMonthlySummaryRepository(self.store),
            audit_logs=FakeAuditLogRepository(self.store),
        )
