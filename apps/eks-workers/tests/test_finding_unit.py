"""Unit tests for Worker_Finding judgement and consistent registration."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.finding import (
    ALLOWED_SEVERITIES,
    ALLOWED_TRIAGE_STATUSES,
    FindingEvent,
    FindingEventError,
    handle_finding_body,
    judge_finding,
    normalize_severity,
    parse_finding_event,
)
from workers.stores import InMemoryFindingStore


def test_normalize_severity_maps_aliases_and_unknown() -> None:
    assert normalize_severity("CRITICAL") == "critical"
    assert normalize_severity("moderate") == "medium"
    assert normalize_severity("informational") == "low"
    assert normalize_severity("something-weird") == "medium"


def test_judge_critical_escalates() -> None:
    j = judge_finding(FindingEvent("e", "t", "critical", "s3", None))
    assert j.assessed_severity == "critical"
    assert j.triage_status == "escalated"


def test_judge_high_on_sensitive_escalates() -> None:
    j = judge_finding(FindingEvent("e", "t", "high", "iam", None))
    assert j.triage_status == "escalated"


def test_judge_low_on_nonsensitive_auto_triaged() -> None:
    j = judge_finding(FindingEvent("e", "t", "low", "ec2", None))
    assert j.triage_status == "auto_triaged"
    assert j.finding_status == "triaged"


def test_judgement_always_in_allowed_ranges_for_examples() -> None:
    for sev in ("low", "medium", "high", "critical", "weird"):
        for rt in (None, "s3", "ec2", "iam"):
            j = judge_finding(FindingEvent("e", "t", sev, rt, None))
            assert j.assessed_severity in ALLOWED_SEVERITIES
            assert j.triage_status in ALLOWED_TRIAGE_STATUSES


def test_parse_rejects_missing_required() -> None:
    with pytest.raises(FindingEventError):
        parse_finding_event('{"title": "t", "severity": "low"}')
    with pytest.raises(FindingEventError):
        parse_finding_event('{"external_id": "e", "severity": "low"}')


def test_parse_eventbridge_finding_event_from_sqs_body() -> None:
    body = json.dumps(
        {
            "version": "0",
            "id": "2c76d716-bc24-0a76-4da2-a19987d97c55",
            "detail-type": "SecurityFinding",
            "source": "ops-platform.sample",
            "account": "397289505365",
            "time": "2026-09-07T16:37:14Z",
            "region": "ap-northeast-1",
            "resources": [],
            "detail": {
                "external_id": "SAMPLE-FINDING-0004",
                "title": "Sample finding 0004",
                "severity": "CRITICAL",
                "resource_type": "AwsEc2Instance",
                "workflow_state": "NEW",
                "description": "Sample dummy security finding for dev/MVP seeding.",
                "detected_at": "2024-01-05T00:00:00Z",
            },
        }
    )

    event = parse_finding_event(body)

    assert event.external_id == "SAMPLE-FINDING-0004"
    assert event.title == "Sample finding 0004"
    assert event.raw_severity == "CRITICAL"
    assert event.resource_type == "AwsEc2Instance"
    assert event.raw_status == "NEW"


def test_registration_is_consistent_and_idempotent() -> None:
    store = InMemoryFindingStore()
    body = {"external_id": "f-1", "title": "t", "severity": "high", "resource_type": "s3"}
    handle_finding_body(store, body)
    handle_finding_body(store, body)
    # Both finding and triage present, and no duplicates.
    assert store.finding_count() == 1
    assert store.triage_count() == 1
    assert store.get_finding("f-1") is not None
    assert store.get_triage("f-1") is not None
