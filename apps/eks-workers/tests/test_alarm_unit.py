"""Unit tests for Worker_Alarm parsing and idempotent ingestion (stdlib only)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.alarm import AlarmEventError, handle_alarm_body, parse_alarm_event
from workers.stores import InMemoryAlarmStore


def test_parse_valid_alarm_event() -> None:
    body = json.dumps(
        {"external_id": "evt-1", "source": "cloudwatch", "event_type": "alarm", "payload": {"k": 1}}
    )
    record = parse_alarm_event(body)
    assert record.external_id == "evt-1"
    assert record.source == "cloudwatch"
    assert record.event_type == "alarm"
    assert record.payload == {"k": 1}


def test_parse_eventbridge_alarm_event_from_sqs_body() -> None:
    body = json.dumps(
        {
            "version": "0",
            "id": "5d6f3a57-b270-6257-8aed-b1fb235f1d38",
            "detail-type": "AlarmEvent",
            "source": "ops-platform.sample",
            "account": "397289505365",
            "time": "2026-09-07T16:37:14Z",
            "region": "ap-northeast-1",
            "resources": [],
            "detail": {
                "external_id": "SAMPLE-ALARM-0002",
                "alarm_name": "ops-platform-dev-sample-alarm-0002",
                "state": "OK",
                "namespace": "AWS/ApplicationELB",
                "metric_name": "HTTPCode_ELB_5XX_Count",
                "resource_ref": "ops-platform-dev-resource-0002",
                "reason": "Sample dummy alarm for dev/MVP seeding.",
                "occurred_at": "2024-01-03T00:00:00Z",
            },
        }
    )

    record = parse_alarm_event(body)

    assert record.external_id == "SAMPLE-ALARM-0002"
    assert record.source == "ops-platform.sample"
    assert record.event_type == "AlarmEvent"
    assert record.payload == {
        "alarm_name": "ops-platform-dev-sample-alarm-0002",
        "state": "OK",
        "namespace": "AWS/ApplicationELB",
        "metric_name": "HTTPCode_ELB_5XX_Count",
        "resource_ref": "ops-platform-dev-resource-0002",
        "reason": "Sample dummy alarm for dev/MVP seeding.",
        "occurred_at": "2024-01-03T00:00:00Z",
    }


def test_parse_rejects_missing_fields() -> None:
    with pytest.raises(AlarmEventError):
        parse_alarm_event('{"source": "s", "event_type": "e"}')


def test_parse_rejects_bad_json_and_non_object() -> None:
    with pytest.raises(AlarmEventError):
        parse_alarm_event("not-json")
    with pytest.raises(AlarmEventError):
        parse_alarm_event("[1, 2, 3]")


def test_parse_rejects_non_object_payload() -> None:
    with pytest.raises(AlarmEventError):
        parse_alarm_event(
            '{"external_id": "e", "source": "s", "event_type": "t", "payload": 5}'
        )


def test_ingest_is_idempotent_on_external_id() -> None:
    store = InMemoryAlarmStore()
    body = {"external_id": "dup-1", "source": "s", "event_type": "t"}
    handle_alarm_body(store, body)
    handle_alarm_body(store, body)
    handle_alarm_body(store, body)
    assert store.count() == 1
