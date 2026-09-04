"""SQLAlchemy-backed repositories implementing the store Protocols.

These use PostgreSQL ON CONFLICT to enforce idempotency at the database level via
the UNIQUE columns (alarm_events.external_id, findings.external_id,
monthly_summaries.period). They are used at runtime; tests use the in-memory
fakes in workers.stores. Importing this module performs no DB I/O.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from workers.db.models import AlarmEvent, Finding, FindingTriage, MonthlySummary
from workers.stores import (
    AlarmEventRecord,
    FindingRecord,
    MonthlySummaryRecord,
    TriageRecord,
)


class SqlAlarmEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, record: AlarmEventRecord) -> None:
        stmt = (
            insert(AlarmEvent)
            .values(
                external_id=record.external_id,
                source=record.source,
                event_type=record.event_type,
                payload=record.payload,
            )
            .on_conflict_do_nothing(index_elements=["external_id"])
        )
        self._session.execute(stmt)

    def count(self) -> int:
        from sqlalchemy import func, select

        return int(self._session.execute(select(func.count()).select_from(AlarmEvent)).scalar_one())


class SqlFindingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_with_triage(self, finding: FindingRecord, triage: TriageRecord) -> None:
        stmt = (
            insert(Finding)
            .values(
                external_id=finding.external_id,
                title=finding.title,
                severity=finding.severity,
                resource_type=finding.resource_type,
                status=finding.status,
            )
            .on_conflict_do_nothing(index_elements=["external_id"])
            .returning(Finding.id)
        )
        result = self._session.execute(stmt).scalar_one_or_none()
        if result is None:
            # external_id already present: no new finding and no new triage.
            return
        self._session.add(
            FindingTriage(
                finding_id=result,
                triage_status=triage.triage_status,
                assessed_severity=triage.assessed_severity,
                note=triage.note,
            )
        )

    def finding_count(self) -> int:
        from sqlalchemy import func, select

        return int(self._session.execute(select(func.count()).select_from(Finding)).scalar_one())

    def triage_count(self) -> int:
        from sqlalchemy import func, select

        return int(self._session.execute(select(func.count()).select_from(FindingTriage)).scalar_one())


class SqlMonthlySummaryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, record: MonthlySummaryRecord) -> None:
        stmt = insert(MonthlySummary).values(
            period=record.period,
            incident_count=record.incident_count,
            finding_count=record.finding_count,
            alarm_count=record.alarm_count,
            detail=record.detail,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["period"],
            set_={
                "incident_count": stmt.excluded.incident_count,
                "finding_count": stmt.excluded.finding_count,
                "alarm_count": stmt.excluded.alarm_count,
                "detail": stmt.excluded.detail,
            },
        )
        self._session.execute(stmt)

    def count(self) -> int:
        from sqlalchemy import func, select

        return int(self._session.execute(select(func.count()).select_from(MonthlySummary)).scalar_one())
