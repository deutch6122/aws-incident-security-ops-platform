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
    parse_finding_events,
    register_finding,
)
from workers.critical_finding_linkage import (
    InMemoryPublicStatusWriter,
    build_critical_finding_status,
    critical_finding_status_id,
    reflect_critical_finding,
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


def test_parse_native_securityhub_imported_findings_batch() -> None:
    body = {
        "source": "aws.securityhub",
        "detail-type": "Security Hub Findings - Imported",
        "detail": {
            "findings": [
                {
                    "Id": "arn:aws:securityhub:ap-northeast-1:111122223333:subscription/example/finding/1",
                    "Title": "Public S3 bucket detected",
                    "Severity": {"Label": "CRITICAL"},
                    "Resources": [{"Type": "AwsS3Bucket", "Id": "redacted"}],
                    "Workflow": {"Status": "NEW"},
                    "Description": "must not be copied to Product_B",
                },
                {
                    "Id": "arn:aws:securityhub:ap-northeast-1:111122223333:subscription/example/finding/2",
                    "Title": "Informational finding",
                    "Severity": {"Label": "LOW"},
                    "Resources": [{"Type": "AwsEc2Instance", "Id": "redacted"}],
                    "Workflow": {"Status": "NEW"},
                },
            ]
        },
    }

    events = parse_finding_events(body)

    assert len(events) == 2
    assert events[0].raw_severity == "CRITICAL"
    assert events[0].resource_type == "AwsS3Bucket"
    assert events[0].raw_status == "NEW"
    assert events[1].raw_severity == "LOW"


def test_critical_finding_only_is_reflected_to_product_b_idempotently() -> None:
    writer = InMemoryPublicStatusWriter()
    critical = FindingEvent("finding/critical", "Critical title", "CRITICAL", "AwsIamRole", "NEW")
    low = FindingEvent("finding/low", "Low title", "LOW", "AwsEc2Instance", "NEW")

    critical_judgement = judge_finding(critical)
    low_judgement = judge_finding(low)

    assert reflect_critical_finding(writer, low, low_judgement) is False
    assert writer.rows == {}
    assert reflect_critical_finding(writer, critical, critical_judgement) is True
    assert reflect_critical_finding(writer, critical, critical_judgement) is True
    assert len(writer.rows) == 1

    item = writer.rows[critical_finding_status_id(critical.external_id)]
    assert item["severity"] == "critical"
    assert item["state"] == "critical"
    assert item["triage_status"] == "escalated"
    assert item["resource_type"] == "AwsIamRole"
    assert "/" not in item["status_id"]


def test_native_securityhub_batch_registers_all_in_product_a_but_reflects_only_critical() -> None:
    body = {
        "source": "aws.securityhub",
        "detail-type": "Security Hub Findings - Imported",
        "detail": {
            "findings": [
                {
                    "Id": "finding/critical",
                    "Title": "Critical finding",
                    "Severity": {"Label": "CRITICAL"},
                    "Resources": [{"Type": "AwsIamRole"}],
                    "Workflow": {"Status": "NEW"},
                },
                {
                    "Id": "finding/high",
                    "Title": "High finding",
                    "Severity": {"Label": "HIGH"},
                    "Resources": [{"Type": "AwsEc2Instance"}],
                    "Workflow": {"Status": "NEW"},
                },
            ]
        },
    }
    product_a = InMemoryFindingStore()
    product_b = InMemoryPublicStatusWriter()

    for event in parse_finding_events(body):
        judgement = register_finding(product_a, event)
        reflect_critical_finding(product_b, event, judgement)

    assert product_a.finding_count() == 2
    assert product_a.triage_count() == 2
    assert len(product_b.rows) == 1
    assert next(iter(product_b.rows.values()))["finding_id"] == "finding/critical"


def test_critical_product_b_projection_excludes_securityhub_description_and_resource_id() -> None:
    event = FindingEvent("finding-id", "Critical title", "critical", "AwsS3Bucket", "NEW")
    item = build_critical_finding_status(event, judge_finding(event))

    assert item is not None
    assert set(item) == {
        "status_id",
        "kind",
        "finding_id",
        "title",
        "state",
        "severity",
        "triage_status",
        "resource_type",
        "message",
    }


def test_critical_product_b_write_failure_is_propagated_for_sqs_retry() -> None:
    class FailingWriter:
        def upsert_status(self, _item: dict[str, object]) -> None:
            raise RuntimeError("simulated DynamoDB failure")

    event = FindingEvent("finding-id", "Critical title", "critical", "AwsS3Bucket", "NEW")

    with pytest.raises(RuntimeError, match="simulated DynamoDB failure"):
        reflect_critical_finding(FailingWriter(), event, judge_finding(event))


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
