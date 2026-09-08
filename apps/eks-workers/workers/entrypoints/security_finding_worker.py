"""Worker_Finding entrypoint (Deployment: security-finding-worker).

Long-running loop: receive sample or native Security Hub finding events from
SQS, register finding + triage consistently in Product_A, then reflect only
CRITICAL findings into Product_B public_status_items. Product_B is write-only
from this worker; no reverse reference is introduced.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from workers.config import WorkerSettings
from workers.critical_finding_linkage import PublicStatusWriter, reflect_critical_finding
from workers.db.repositories import SqlFindingRepository
from workers.db.session import WorkerDatabase
from workers.finding import parse_finding_events, register_finding
from workers.portal_adapters import DynamoPublicStatusWriter, PortalTargets
from workers.sqs import Boto3SqsClient, SqsClient, SqsMessage, process_batch

logger = logging.getLogger("security-finding-worker")

_running = True


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _running
    _running = False


def _make_handler(database: WorkerDatabase, status_writer: PublicStatusWriter):
    def handler(message: SqsMessage) -> None:
        processed = []
        with database.session() as session:
            repository = SqlFindingRepository(session)
            for event in parse_finding_events(message.body):
                judgement = register_finding(repository, event)
                processed.append((event, judgement))
            session.commit()
        for event, judgement in processed:
            reflected = reflect_critical_finding(status_writer, event, judgement)
            logger.info(
                "registered finding",
                extra={
                    "assessed_severity": judgement.assessed_severity,
                    "triage_status": judgement.triage_status,
                    "reflected_to_portal": reflected,
                },
            )

    return handler


def run(
    client: SqsClient,
    database: WorkerDatabase,
    settings: WorkerSettings,
    status_writer: PublicStatusWriter,
) -> None:
    handler = _make_handler(database, status_writer)
    while _running:
        process_batch(
            client,
            handler,
            max_messages=settings.max_messages,
            wait_time_seconds=settings.wait_time_seconds,
            visibility_timeout=settings.visibility_timeout_seconds,
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    settings = WorkerSettings.from_env()
    client = Boto3SqsClient(settings.require_sqs_queue_url(), settings.aws_region)
    database = WorkerDatabase(settings)
    status_writer = DynamoPublicStatusWriter(
        PortalTargets(
            aws_region=settings.aws_region,
            public_status_items_table=(
                settings.require_portal_public_status_items_table()
            ),
        )
    )
    run(client, database, settings, status_writer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
