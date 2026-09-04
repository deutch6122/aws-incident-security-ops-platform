"""Unit tests for the SQS receive/process/delete loop (Requirement 6.5).

Pure stdlib; no AWS access. Verifies deletion happens only after successful
handling and that a failing handler leaves the message for redelivery.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.sqs import SqsMessage, process_batch


class FakeSqsClient:
    def __init__(self, messages: list[SqsMessage]) -> None:
        self._messages = messages
        self.deleted: list[str] = []

    def receive(self, max_messages, wait_time_seconds, visibility_timeout):
        batch = self._messages[:max_messages]
        return batch

    def delete(self, receipt_handle: str) -> None:
        self.deleted.append(receipt_handle)


def _msg(i: int) -> SqsMessage:
    return SqsMessage(message_id=f"m{i}", receipt_handle=f"rh{i}", body="{}")


def test_message_deleted_only_after_successful_handling() -> None:
    client = FakeSqsClient([_msg(1), _msg(2)])
    handled: list[str] = []

    def handler(message: SqsMessage) -> None:
        handled.append(message.message_id)

    result = process_batch(client, handler, max_messages=10, wait_time_seconds=0, visibility_timeout=30)

    assert handled == ["m1", "m2"]
    assert client.deleted == ["rh1", "rh2"]
    assert result.processed == 2 and result.deleted == 2 and result.failed == 0


def test_failing_handler_does_not_delete_message() -> None:
    client = FakeSqsClient([_msg(1), _msg(2)])

    def handler(message: SqsMessage) -> None:
        if message.message_id == "m1":
            raise RuntimeError("transient failure")

    result = process_batch(client, handler, max_messages=10, wait_time_seconds=0, visibility_timeout=30)

    # m1 failed and is NOT deleted (left for redelivery / DLQ); m2 succeeded.
    assert client.deleted == ["rh2"]
    assert result.failed == 1 and result.processed == 1 and result.deleted == 1


def test_delete_call_order_is_after_handler() -> None:
    events: list[str] = []

    class OrderedClient:
        def receive(self, max_messages, wait_time_seconds, visibility_timeout):
            return [_msg(1)]

        def delete(self, receipt_handle: str) -> None:
            events.append("delete")

    def handler(message: SqsMessage) -> None:
        events.append("handle")

    process_batch(OrderedClient(), handler, max_messages=1, wait_time_seconds=0, visibility_timeout=30)
    assert events == ["handle", "delete"]
