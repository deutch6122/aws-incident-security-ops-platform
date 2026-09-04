"""Worker_Alarm entrypoint (Deployment: alarm-event-processor).

Long-running loop: receive alarm events from SQS, upsert into alarm_events
idempotently, then delete the processed message. All AWS/DB resources are built
lazily, so importing this module has no side effects.
"""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from workers.alarm import handle_alarm_body
from workers.config import WorkerSettings
from workers.db.repositories import SqlAlarmEventRepository
from workers.db.session import WorkerDatabase
from workers.sqs import Boto3SqsClient, SqsClient, SqsMessage, process_batch

logger = logging.getLogger("alarm-event-processor")

_running = True


def _stop(_signum: int, _frame: FrameType | None) -> None:
    global _running
    _running = False


def _make_handler(database: WorkerDatabase):
    def handler(message: SqsMessage) -> None:
        with database.session() as session:
            repository = SqlAlarmEventRepository(session)
            record = handle_alarm_body(repository, message.body)
            session.commit()
        logger.info("ingested alarm event", extra={"external_id": record.external_id})

    return handler


def run(client: SqsClient, database: WorkerDatabase, settings: WorkerSettings) -> None:
    """Poll until a termination signal is received."""

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
