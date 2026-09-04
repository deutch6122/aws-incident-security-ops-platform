"""Typed SQLAlchemy repositories. Each write method owns commit/rollback."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, Finding, FindingTriage, Incident, IncidentComment, MonthlySummary
from app.domain.aggregation import merge_status_counts

_ModelT = TypeVar("_ModelT")


def _commit(session: Session, entity: _ModelT | None = None) -> _ModelT | None:
    try:
        session.commit()
        if entity is not None:
            session.refresh(entity)
        return entity
    except Exception:
        session.rollback()
        raise


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, external_id: str, title: str, severity: str, status: str = "open", description: str | None = None) -> Incident:
        incident = Incident(external_id=external_id, title=title, severity=severity, status=status, description=description)
        self.session.add(incident)
        return _commit(self.session, incident)  # type: ignore[return-value]

    def get(self, incident_id: int) -> Incident | None:
        return self.session.get(Incident, incident_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> list[Incident]:
        statement = select(Incident).order_by(Incident.id).offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def update(self, incident_id: int, **changes: str | None) -> Incident | None:
        incident = self.get(incident_id)
        if incident is None:
            return None
        allowed = {"title", "severity", "status", "description"}
        for name, value in changes.items():
            if name not in allowed:
                raise ValueError(f"unsupported incident field: {name}")
            setattr(incident, name, value)
        return _commit(self.session, incident)  # type: ignore[return-value]

    def delete(self, incident_id: int) -> bool:
        incident = self.get(incident_id)
        if incident is None:
            return False
        self.session.delete(incident)
        _commit(self.session)
        return True

    def count_by_status(self) -> dict[str, int]:
        rows = self.session.execute(
            select(Incident.status, func.count(Incident.id)).group_by(Incident.status)
        ).all()
        return merge_status_counts((str(status), int(count)) for status, count in rows)


class IncidentCommentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, incident_id: int, author: str, body: str) -> IncidentComment:
        comment = IncidentComment(incident_id=incident_id, author=author, body=body)
        self.session.add(comment)
        return _commit(self.session, comment)  # type: ignore[return-value]

    def get(self, comment_id: int) -> IncidentComment | None:
        return self.session.get(IncidentComment, comment_id)

    def list_for_incident(self, incident_id: int) -> list[IncidentComment]:
        statement = select(IncidentComment).where(IncidentComment.incident_id == incident_id).order_by(IncidentComment.id)
        return list(self.session.scalars(statement))

    def update(self, comment_id: int, *, body: str) -> IncidentComment | None:
        comment = self.get(comment_id)
        if comment is None:
            return None
        comment.body = body
        return _commit(self.session, comment)  # type: ignore[return-value]

    def delete(self, comment_id: int) -> bool:
        comment = self.get(comment_id)
        if comment is None:
            return False
        self.session.delete(comment)
        _commit(self.session)
        return True


class FindingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, external_id: str, title: str, severity: str, resource_type: str | None = None, status: str = "new") -> Finding:
        finding = Finding(external_id=external_id, title=title, severity=severity, resource_type=resource_type, status=status)
        self.session.add(finding)
        return _commit(self.session, finding)  # type: ignore[return-value]

    def get(self, finding_id: int) -> Finding | None:
        return self.session.get(Finding, finding_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> list[Finding]:
        statement = select(Finding).order_by(Finding.id).offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def update(self, finding_id: int, **changes: str | None) -> Finding | None:
        finding = self.get(finding_id)
        if finding is None:
            return None
        allowed = {"title", "severity", "resource_type", "status"}
        for name, value in changes.items():
            if name not in allowed:
                raise ValueError(f"unsupported finding field: {name}")
            setattr(finding, name, value)
        return _commit(self.session, finding)  # type: ignore[return-value]

    def delete(self, finding_id: int) -> bool:
        finding = self.get(finding_id)
        if finding is None:
            return False
        self.session.delete(finding)
        _commit(self.session)
        return True

    def count_by_status(self) -> dict[str, int]:
        rows = self.session.execute(
            select(Finding.status, func.count(Finding.id)).group_by(Finding.status)
        ).all()
        return merge_status_counts((str(status), int(count)) for status, count in rows)


class FindingTriageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, finding_id: int, triage_status: str, assessed_severity: str, note: str | None = None) -> FindingTriage:
        triage = FindingTriage(finding_id=finding_id, triage_status=triage_status, assessed_severity=assessed_severity, note=note)
        self.session.add(triage)
        return _commit(self.session, triage)  # type: ignore[return-value]

    def get(self, triage_id: int) -> FindingTriage | None:
        return self.session.get(FindingTriage, triage_id)

    def list_for_finding(self, finding_id: int) -> list[FindingTriage]:
        statement = select(FindingTriage).where(FindingTriage.finding_id == finding_id).order_by(FindingTriage.id)
        return list(self.session.scalars(statement))

    def update(self, triage_id: int, **changes: str | None) -> FindingTriage | None:
        triage = self.get(triage_id)
        if triage is None:
            return None
        allowed = {"triage_status", "assessed_severity", "note"}
        for name, value in changes.items():
            if name not in allowed:
                raise ValueError(f"unsupported triage field: {name}")
            setattr(triage, name, value)
        return _commit(self.session, triage)  # type: ignore[return-value]

    def delete(self, triage_id: int) -> bool:
        triage = self.get(triage_id)
        if triage is None:
            return False
        self.session.delete(triage)
        _commit(self.session)
        return True


class MonthlySummaryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, period: str, incident_count: int, finding_count: int, alarm_count: int, detail: Mapping[str, Any] | None = None) -> MonthlySummary:
        summary = MonthlySummary(period=period, incident_count=incident_count, finding_count=finding_count, alarm_count=alarm_count, detail=dict(detail) if detail is not None else None)
        self.session.add(summary)
        return _commit(self.session, summary)  # type: ignore[return-value]

    def get(self, summary_id: int) -> MonthlySummary | None:
        return self.session.get(MonthlySummary, summary_id)

    def get_by_period(self, period: str) -> MonthlySummary | None:
        return self.session.scalar(select(MonthlySummary).where(MonthlySummary.period == period))

    def list(self) -> list[MonthlySummary]:
        return list(self.session.scalars(select(MonthlySummary).order_by(MonthlySummary.period.desc())))

    def update(self, summary_id: int, *, incident_count: int, finding_count: int, alarm_count: int, detail: Mapping[str, Any] | None = None) -> MonthlySummary | None:
        summary = self.get(summary_id)
        if summary is None:
            return None
        summary.incident_count = incident_count
        summary.finding_count = finding_count
        summary.alarm_count = alarm_count
        summary.detail = dict(detail) if detail is not None else None
        return _commit(self.session, summary)  # type: ignore[return-value]

    def delete(self, summary_id: int) -> bool:
        summary = self.get(summary_id)
        if summary is None:
            return False
        self.session.delete(summary)
        _commit(self.session)
        return True


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, entity_type: str, entity_id: int, action: str, before_value: Mapping[str, Any] | None, after_value: Mapping[str, Any] | None, actor: str | None = None) -> AuditLog:
        log = AuditLog(entity_type=entity_type, entity_id=entity_id, action=action, before_value=dict(before_value) if before_value is not None else None, after_value=dict(after_value) if after_value is not None else None, actor=actor)
        self.session.add(log)
        return _commit(self.session, log)  # type: ignore[return-value]

    def get(self, log_id: int) -> AuditLog | None:
        return self.session.get(AuditLog, log_id)

    def list_for_entity(self, entity_type: str, entity_id: int) -> list[AuditLog]:
        statement = select(AuditLog).where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id).order_by(AuditLog.id)
        return list(self.session.scalars(statement))

    def update(self, log_id: int, *, actor: str | None) -> AuditLog | None:
        log = self.get(log_id)
        if log is None:
            return None
        log.actor = actor
        return _commit(self.session, log)  # type: ignore[return-value]

    def delete(self, log_id: int) -> bool:
        result = self.session.execute(delete(AuditLog).where(AuditLog.id == log_id))
        if result.rowcount == 0:
            self.session.rollback()
            return False
        _commit(self.session)
        return True
