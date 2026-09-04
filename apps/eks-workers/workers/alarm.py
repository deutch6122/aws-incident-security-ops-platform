"""Worker_Alarm (alarm-event-processor) core logic.

Parses an alarm-shaped event and idempotently ingests it into alarm_events. The
ingest is a no-op on the second and later occurrences of the same external_id
(Requirement 6.2, Property 7). This module has no AWS or DB dependency; it takes
an AlarmEventRepository so it works with the SQLAlchemy repo or the in-memory
fake.
"""

from __future__ import annotations

import json
from typing import Any

from workers.stores import AlarmEventRecord, AlarmEventRepository


class AlarmEventError(ValueError):
    """Raised when an alarm event cannot be parsed into a valid record."""


_REQUIRED = ("external_id", "source", "event_type")


def parse_alarm_event(body: str | dict[str, Any]) -> AlarmEventRecord:
    """Parse a JSON body (or already-decoded dict) into an AlarmEventRecord."""

    if isinstance(body, str):
        try:
            raw: Any = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AlarmEventError("alarm event body is not valid JSON") from exc
    else:
        raw = body

    if not isinstance(raw, dict):
        raise AlarmEventError("alarm event must be a JSON object")

    values: dict[str, str] = {}
    for key in _REQUIRED:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise AlarmEventError(f"alarm event field {key} must be non-empty text")
        values[key] = value.strip()

    payload = raw.get("payload")
    if payload is not None and not isinstance(payload, dict):
        raise AlarmEventError("alarm event payload must be an object when present")

    return AlarmEventRecord(
        external_id=values["external_id"],
        source=values["source"],
        event_type=values["event_type"],
        payload=payload,
    )


def ingest_alarm_event(repository: AlarmEventRepository, record: AlarmEventRecord) -> None:
    """Idempotently persist the alarm event (ON CONFLICT (external_id) DO NOTHING)."""

    repository.upsert(record)


def handle_alarm_body(repository: AlarmEventRepository, body: str | dict[str, Any]) -> AlarmEventRecord:
    """Parse then ingest; returns the parsed record for logging/testing."""

    record = parse_alarm_event(body)
    ingest_alarm_event(repository, record)
    return record
