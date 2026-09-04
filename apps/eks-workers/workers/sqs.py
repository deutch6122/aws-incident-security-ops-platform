"""SQS abstraction: a Protocol, a lazy boto3 adapter, and the receive/process/
delete loop skeleton shared by the two Deployment workers.

At-least-once delivery is assumed. The loop deletes a message ONLY after its
handler returns successfully (Requirement 6.5); a handler that raises leaves the
message on the queue so SQS redelivers it after the visibility timeout, and
repeated failures move it to the DLQ (Requirement 6.4, configured in Task 11).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class SqsMessage:
    """A minimal, transport-agnostic view of one SQS message."""

    message_id: str
    receipt_handle: str
    body: str


class SqsClient(Protocol):
    def receive(self, max_messages: int, wait_time_seconds: int, visibility_timeout: int) -> list[SqsMessage]:
        """Return up to max_messages messages (long polling)."""

    def delete(self, receipt_handle: str) -> None:
        """Delete a successfully processed message."""


class Boto3SqsClient:
    """Production adapter. boto3 and its client are created only on first use."""

    def __init__(self, queue_url: str, region_name: str) -> None:
        self._queue_url = queue_url
        self._region_name = region_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("sqs", region_name=self._region_name)
        return self._client

    def receive(self, max_messages: int, wait_time_seconds: int, visibility_timeout: int) -> list[SqsMessage]:
        response = self._get_client().receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=max(1, min(max_messages, 10)),
            WaitTimeSeconds=wait_time_seconds,
            VisibilityTimeout=visibility_timeout,
        )
        messages = response.get("Messages", [])
        return [
            SqsMessage(
                message_id=m.get("MessageId", ""),
                receipt_handle=m["ReceiptHandle"],
                body=m.get("Body", ""),
            )
            for m in messages
        ]

    def delete(self, receipt_handle: str) -> None:
        self._get_client().delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)


@dataclass(frozen=True, slots=True)
class BatchResult:
    processed: int
    deleted: int
    failed: int


def process_batch(
    client: SqsClient,
    handler: Callable[[SqsMessage], None],
    *,
    max_messages: int,
    wait_time_seconds: int,
    visibility_timeout: int,
) -> BatchResult:
    """Receive one batch and process each message.

    Deletion happens strictly after the handler succeeds. A handler exception is
    swallowed per-message (counted as failed) so one poison message does not
    abort the whole batch; SQS redelivery / DLQ handles the retry semantics.
    """

    messages = client.receive(
        max_messages=max_messages,
        wait_time_seconds=wait_time_seconds,
        visibility_timeout=visibility_timeout,
    )
    processed = 0
    deleted = 0
    failed = 0
    for message in messages:
        try:
            handler(message)
        except Exception:  # noqa: BLE001 - keep the message for redelivery/DLQ
            failed += 1
            continue
        processed += 1
        # Delete only after successful processing (Requirement 6.5).
        client.delete(message.receipt_handle)
        deleted += 1
    return BatchResult(processed=processed, deleted=deleted, failed=failed)
