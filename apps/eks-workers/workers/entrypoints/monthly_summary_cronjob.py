"""Cronjob_Summary entrypoint (CronJob: monthly-summary-cronjob).

Single-shot job: determine the target period, aggregate the incidents /
findings / alarm_events in that month, and upsert monthly_summaries keyed on
period. Exits when done (CronJob semantics).

A->B linkage (Requirement 14): this CronJob is the ONLY execution subject that
reflects the (non-sensitive) monthly summary into Product_B -- a report file in
Portal_Storage reports/*, plus report_metadata and public_status_items. The
linkage runs only when the Product_B targets are configured (PORTAL_REPORTS_
BUCKET etc.); otherwise it is skipped so the summary job still succeeds. The
linkage is one-way A -> B: it never reads or writes Product_A from Product_B.

All AWS/DB resources are built lazily.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from workers.config import WorkerSettings
from workers.db.models import AlarmEvent, Finding, Incident
from workers.db.repositories import SqlMonthlySummaryRepository
from workers.db.session import WorkerDatabase
from workers.linkage import LinkageReport, link_summary_to_portal
from workers.portal_adapters import (
    DynamoPublicStatusWriter,
    DynamoReportMetadataWriter,
    PortalTargets,
    S3PortalStorage,
)
from workers.stores import MonthlySummaryRecord
from workers.summary import (
    TimedRecord,
    generate_monthly_summary,
    period_of,
    validate_period,
)

logger = logging.getLogger("monthly-summary-cronjob")


def resolve_period(environ: dict[str, str] | None = None) -> str:
    """Use WORKER_SUMMARY_PERIOD if set, otherwise the current UTC month."""

    env = environ if environ is not None else dict(os.environ)
    configured = (env.get("WORKER_SUMMARY_PERIOD") or "").strip()
    if configured:
        return validate_period(configured)
    return period_of(datetime.now(timezone.utc))


def _timed_rows(session: Session, model) -> list[TimedRecord]:
    rows = session.execute(select(model.created_at)).scalars().all()
    return [TimedRecord(created_at=value) for value in rows]


def run(database: WorkerDatabase, period: str) -> MonthlySummaryRecord:
    with database.session() as session:
        incidents = _timed_rows(session, Incident)
        findings = _timed_rows(session, Finding)
        # alarm_events uses received_at as its timestamp column.
        alarm_rows = session.execute(select(AlarmEvent.received_at)).scalars().all()
        alarms = [TimedRecord(created_at=value) for value in alarm_rows]

        repository = SqlMonthlySummaryRepository(session)
        record = generate_monthly_summary(repository, period, incidents, findings, alarms)
        session.commit()
    logger.info(
        "generated monthly summary",
        extra={
            "period": record.period,
            "incident_count": record.incident_count,
            "finding_count": record.finding_count,
            "alarm_count": record.alarm_count,
        },
    )
    return record


def link_to_portal(
    record: MonthlySummaryRecord, targets: PortalTargets | None = None
) -> LinkageReport | None:
    """Reflect the non-sensitive summary into Product_B (one-way A -> B).

    Skips silently when Portal_Storage is not configured so the summary job still
    succeeds in environments without Product_B wiring. This is the only place the
    linkage is triggered (CronJob-limited execution subject, Requirement 14).
    """
    targets = targets or PortalTargets.from_env()
    if not targets.reports_bucket:
        logger.info("portal linkage skipped: PORTAL_REPORTS_BUCKET not configured")
        return None

    report = link_summary_to_portal(
        record,
        storage=S3PortalStorage(targets),
        report_writer=DynamoReportMetadataWriter(targets),
        status_writer=DynamoPublicStatusWriter(targets),
    )
    logger.info(
        "reflected monthly summary to portal",
        extra={
            "period": report.period,
            "report_id": report.report_id,
            "status_id": report.public_status_item()["status_id"],
            "s3_key": report.s3_key,
        },
    )
    return report


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    settings = WorkerSettings.from_env()
    database = WorkerDatabase(settings)
    period = resolve_period()
    record = run(database, period)
    link_to_portal(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
