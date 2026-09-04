"""Worker_Finding entrypoint (Deployment: security-finding-worker).

Long-running loop: receive finding events from SQS, judge them, register the
finding + triage consistently and idempotently, then delete the message. All
AWS/DB resources are built lazily; importing this module has no side effects.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from workers.config import WorkerSettings
from workers.db.repositories import SqlFindingRepository
from workers.db.session import WorkerDatabase
from workers.finding import handle_finding_body
from workers.sqs import Boto3SqsClient, SqsClient, SqsMessage, process_batch

logger = logging.getLogger("security-finding-worker")

_running = True


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _running
    _running = False


def _make_handler(database: WorkerDatabase):
    def handler(message: SqsMessage) -> None:
        with database.session() as session:
            repository = SqlFindingRepository(session)
            judgement = handle_finding_body(repository, message.body)
            session.commit()
        logger.info(
            "registered finding",
            extra={
                "assessed_severity": judgement.assessed_severity,
                "triage_status": judgement.triage_status,
            },
        )

    return handler


def run(client: SqsClient, database: WorkerDatabase, settings: WorkerSettings) -> None:
    handler = _make_handler(database)
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
    run(client, database, settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
