"""Task 11.3 async-path integration test: EventBridge -> SQS -> Worker -> (fake) Aurora.

Validates: Requirements 6.1, 6.4, 6.5

No AWS access, no Docker, no real Aurora. The worker persistence layer is the
in-memory alarm store (workers.stores.InMemoryAlarmStore), which replicates the
alarm_events.external_id UNIQUE / ON CONFLICT DO NOTHING semantics of Aurora.

Two front-ends exercise the same invariants:

* A dependency-free fake SqsClient (Protocol implementation) that models an
  EventBridge -> SQS delivery, receive with a visibility timeout, and delete.
  This case always runs on stdlib + the existing workers package.
* An optional moto-backed case (pytest.importorskip("moto")) that creates a real
  SQS queue, sends a message the way EventBridge would, receives it, and deletes
  it after the handler succeeds. Skipped when moto is not installed.

Invariants checked:
  1. On handler success, the SQS message is deleted (queue drains).
  2. On handler failure, the message is NOT deleted (stays for redelivery/DLQ).
  3. Idempotency: processing the same external_id more than once does not grow
     the alarm store (pipeline view of Property 7).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.alarm import handle_alarm_body
from workers.sqs import SqsMessage, process_batch
from workers.stores import InMemoryAlarmStore


# ---------------------------------------------------------------------------
# Fake front-end: models EventBridge -> SQS with a visibility-timeout / delete
# ---------------------------------------------------------------------------
class FakeQueue:
    """A minimal Standard-queue fake with at-least-once receive semantics.

    A received message becomes invisible for the batch and is removed from the
    queue only on delete(). If it is not deleted, a later receive() sees it
    again (redelivery), which is what keeps a failed message on the queue.
    """

    def __init__(self) -> None:
        self._messages: list[SqsMessage] = []
        self._inflight: dict[str, SqsMessage] = {}
        self._counter = 0

    def send_from_eventbridge(self, detail: dict) -> None:
        """EventBridge target delivery: the event body lands as the SQS body."""
        self._counter += 1
        mid = f"m{self._counter}"
        self._messages.append(
            SqsMessage(message_id=mid, receipt_handle=f"rh{self._counter}", body=json.dumps(detail))
        )

    # SqsClient Protocol -----------------------------------------------------
    def receive(self, max_messages, wait_time_seconds, visibility_timeout):
        batch = self._messages[:max_messages]
        for msg in batch:
            self._inflight[msg.receipt_handle] = msg
        # Make received messages invisible for this batch.
        self._messages = self._messages[len(batch):]
        return batch

    def delete(self, receipt_handle: str) -> None:
        self._inflight.pop(receipt_handle, None)

    def make_failed_visible_again(self) -> None:
        """Simulate visibility-timeout expiry: undeleted in-flight msgs return."""
        self._messages.extend(self._inflight.values())
        self._inflight.clear()

    def depth(self) -> int:
        return len(self._messages) + len(self._inflight)


def _alarm_detail(external_id: str) -> dict:
    return {
        "external_id": external_id,
        "source": "ops-platform.sample",
        "event_type": "alarm.state.change",
        "payload": {"state": "ALARM"},
    }


def test_fake_pipeline_success_deletes_message_and_persists_once() -> None:
    queue = FakeQueue()
    store = InMemoryAlarmStore()
    queue.send_from_eventbridge(_alarm_detail("evt-1"))

    result = process_batch(
        queue,
        lambda m: handle_alarm_body(store, m.body),
        max_messages=10,
        wait_time_seconds=0,
        visibility_timeout=30,
    )

    # Invariant 1: success -> deleted, queue drained.
    assert result.processed == 1 and result.deleted == 1 and result.failed == 0
    assert queue.depth() == 0
    # Persisted to the (fake) Aurora store.
    assert store.count() == 1
    assert store.get("evt-1") is not None


def test_fake_pipeline_failure_keeps_message_for_redelivery() -> None:
    queue = FakeQueue()
    store = InMemoryAlarmStore()
    # A body that cannot be parsed makes the handler raise -> no delete.
    queue.send_from_eventbridge({"source": "ops-platform.sample"})  # missing external_id

    def handler(message: SqsMessage) -> None:
        handle_alarm_body(store, message.body)  # raises AlarmEventError

    result = process_batch(
        queue, handler, max_messages=10, wait_time_seconds=0, visibility_timeout=30
    )

    # Invariant 2: failure -> not deleted, message survives for redelivery/DLQ.
    assert result.failed == 1 and result.deleted == 0
    assert store.count() == 0
    queue.make_failed_visible_again()
    assert queue.depth() == 1


def test_fake_pipeline_idempotent_on_duplicate_external_id() -> None:
    queue = FakeQueue()
    store = InMemoryAlarmStore()
    # EventBridge delivers the same logical event three times (at-least-once).
    for _ in range(3):
        queue.send_from_eventbridge(_alarm_detail("evt-dup"))

    total_deleted = 0
    for _ in range(3):
        result = process_batch(
            queue,
            lambda m: handle_alarm_body(store, m.body),
            max_messages=1,
            wait_time_seconds=0,
            visibility_timeout=30,
        )
        total_deleted += result.deleted

    # Invariant 3: three deliveries all delete, but the store holds exactly one row.
    assert total_deleted == 3
    assert queue.depth() == 0
    assert store.count() == 1


# ---------------------------------------------------------------------------
# Optional moto-backed front-end (skipped when moto is not installed)
# ---------------------------------------------------------------------------
class _MotoSqsAdapter:
    """Adapts a boto3 SQS client to the workers.sqs.SqsClient Protocol."""

    def __init__(self, client, queue_url: str) -> None:
        self._client = client
        self._queue_url = queue_url

    def receive(self, max_messages, wait_time_seconds, visibility_timeout):
        response = self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=max(1, min(max_messages, 10)),
            WaitTimeSeconds=wait_time_seconds,
            VisibilityTimeout=visibility_timeout,
        )
        return [
            SqsMessage(
                message_id=m.get("MessageId", ""),
                receipt_handle=m["ReceiptHandle"],
                body=m.get("Body", ""),
            )
            for m in response.get("Messages", [])
        ]

    def delete(self, receipt_handle: str) -> None:
        self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt_handle)

    def approximate_depth(self) -> int:
        attrs = self._client.get_queue_attributes(
            QueueUrl=self._queue_url,
            AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
        )["Attributes"]
        return int(attrs["ApproximateNumberOfMessages"]) + int(
            attrs["ApproximateNumberOfMessagesNotVisible"]
        )


def test_moto_pipeline_success_deletes_message() -> None:
    pytest.importorskip("moto")
    boto3 = pytest.importorskip("boto3")
    from moto import mock_aws

    with mock_aws():
        client = boto3.client("sqs", region_name="ap-northeast-1")
        queue_url = client.create_queue(QueueName="ops-platform-dev-events")["QueueUrl"]
        # EventBridge would SendMessage the event body onto the queue.
        client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(_alarm_detail("moto-1")))

        adapter = _MotoSqsAdapter(client, queue_url)
        store = InMemoryAlarmStore()

        result = process_batch(
            adapter,
            lambda m: handle_alarm_body(store, m.body),
            max_messages=10,
            wait_time_seconds=0,
            visibility_timeout=30,
        )

        assert result.processed == 1 and result.deleted == 1 and result.failed == 0
        assert store.count() == 1
        assert adapter.approximate_depth() == 0


def test_moto_pipeline_failure_leaves_message_on_queue() -> None:
    pytest.importorskip("moto")
    boto3 = pytest.importorskip("boto3")
    from moto import mock_aws

    with mock_aws():
        client = boto3.client("sqs", region_name="ap-northeast-1")
        queue_url = client.create_queue(QueueName="ops-platform-dev-events")["QueueUrl"]
        # Missing external_id -> handler raises -> message must NOT be deleted.
        client.send_message(QueueUrl=queue_url, MessageBody=json.dumps({"source": "x"}))

        adapter = _MotoSqsAdapter(client, queue_url)
        store = InMemoryAlarmStore()

        result = process_batch(
            adapter,
            lambda m: handle_alarm_body(store, m.body),
            max_messages=10,
            wait_time_seconds=0,
            visibility_timeout=0,
        )

        assert result.failed == 1 and result.deleted == 0
        assert store.count() == 0
        # With visibility_timeout=0 the undeleted message is immediately visible.
        assert adapter.approximate_depth() >= 1
