"""Worker_Finding (security-finding-worker) core logic.

Pure judgement of a finding-shaped event (severity, resource type, response
status) followed by consistent registration into findings + finding_triage.

The judgement function is deliberately pure and total: for ANY input it returns
an assessed severity and a triage status drawn from a fixed, allowed value set
(Property 8: results stay within the allowed value range). Registration is
idempotent on external_id: re-processing the same event adds no new rows
(Property 8: no duplicate rows).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from workers.stores import FindingRecord, FindingRepository, TriageRecord

# Allowed value ranges. The judgement result is always a member of these sets.
ALLOWED_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high", "critical"})
ALLOWED_TRIAGE_STATUSES: frozenset[str] = frozenset(
    {"auto_triaged", "needs_review", "escalated"}
)
ALLOWED_FINDING_STATUSES: frozenset[str] = frozenset({"new", "triaged"})

# Resource types considered sensitive; a finding on them is escalated by policy.
_SENSITIVE_RESOURCE_TYPES: frozenset[str] = frozenset(
    {"iam", "kms", "secretsmanager", "s3", "rds", "aurora"}
)

# Normalization map from arbitrary inbound severity text to the allowed set.
_SEVERITY_ALIASES: dict[str, str] = {
    "informational": "low",
    "info": "low",
    "low": "low",
    "medium": "medium",
    "moderate": "medium",
    "warning": "medium",
    "high": "high",
    "important": "high",
    "critical": "critical",
    "severe": "critical",
    "fatal": "critical",
}


class FindingEventError(ValueError):
    """Raised when a finding event cannot be parsed into a valid record."""


@dataclass(frozen=True, slots=True)
class FindingEvent:
    external_id: str
    title: str
    raw_severity: str
    resource_type: str | None
    raw_status: str | None


@dataclass(frozen=True, slots=True)
class FindingJudgement:
    assessed_severity: str
    finding_status: str
    triage_status: str


def _decode_object(body: str | dict[str, Any]) -> dict[str, Any]:
    """Decode a JSON body and require an object shape."""

    if isinstance(body, str):
        try:
            raw: Any = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise FindingEventError("finding event body is not valid JSON") from exc
    else:
        raw = body

    if not isinstance(raw, dict):
        raise FindingEventError("finding event must be a JSON object")

    return raw


def _unwrap_eventbridge_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept direct finding JSON or EventBridge events delivered through SQS."""

    detail = raw.get("detail")
    if detail is None:
        return raw

    if isinstance(detail, str):
        try:
            decoded_detail: Any = json.loads(detail)
        except (TypeError, json.JSONDecodeError) as exc:
            raise FindingEventError("finding event detail is not valid JSON") from exc
        detail = decoded_detail

    if not isinstance(detail, dict):
        raise FindingEventError("finding event detail must be an object when present")

    return dict(detail)


def _securityhub_finding_to_flat(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert one AWS Security Finding Format item to the worker contract."""

    severity = raw.get("Severity")
    resources = raw.get("Resources")
    workflow = raw.get("Workflow")

    severity_label = severity.get("Label") if isinstance(severity, dict) else None
    resource_type = None
    if isinstance(resources, list) and resources and isinstance(resources[0], dict):
        resource_type = resources[0].get("Type")
    workflow_status = workflow.get("Status") if isinstance(workflow, dict) else None

    return {
        "external_id": raw.get("Id"),
        "title": raw.get("Title"),
        "severity": severity_label,
        "resource_type": resource_type,
        "workflow_state": workflow_status,
    }


def _parse_flat_finding(raw: dict[str, Any]) -> FindingEvent:
    """Parse the worker's normalized, single-finding input shape."""

    external_id = raw.get("external_id")
    if not isinstance(external_id, str) or not external_id.strip():
        raise FindingEventError("finding event field external_id must be non-empty text")

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        raise FindingEventError("finding event field title must be non-empty text")

    raw_severity = raw.get("severity")
    if not isinstance(raw_severity, str) or not raw_severity.strip():
        raise FindingEventError("finding event field severity must be non-empty text")

    resource_type = raw.get("resource_type")
    if resource_type is not None and not isinstance(resource_type, str):
        raise FindingEventError("finding event resource_type must be text when present")

    raw_status = raw.get("status", raw.get("workflow_state"))
    if raw_status is not None and not isinstance(raw_status, str):
        raise FindingEventError("finding event status must be text when present")

    return FindingEvent(
        external_id=external_id.strip(),
        title=title.strip(),
        raw_severity=raw_severity.strip(),
        resource_type=(
            resource_type.strip()
            if isinstance(resource_type, str) and resource_type.strip()
            else None
        ),
        raw_status=raw_status,
    )


def normalize_severity(raw_severity: str) -> str:
    """Map arbitrary severity text to an allowed severity. Unknown -> medium."""

    key = (raw_severity or "").strip().lower()
    return _SEVERITY_ALIASES.get(key, "medium")


def judge_finding(event: FindingEvent) -> FindingJudgement:
    """Total, pure judgement. Result is always within the allowed value ranges."""

    assessed = normalize_severity(event.raw_severity)
    resource = (event.resource_type or "").strip().lower()
    sensitive = resource in _SENSITIVE_RESOURCE_TYPES

    if assessed == "critical" or (assessed == "high" and sensitive):
        triage_status = "escalated"
    elif assessed in {"high", "medium"} or sensitive:
        triage_status = "needs_review"
    else:
        triage_status = "auto_triaged"

    finding_status = "triaged" if triage_status != "needs_review" else "new"

    return FindingJudgement(
        assessed_severity=assessed,
        finding_status=finding_status,
        triage_status=triage_status,
    )


def parse_finding_events(body: str | dict[str, Any]) -> list[FindingEvent]:
    """Parse a sample/direct finding or a native Security Hub event batch.

    Security Hub's ``Security Hub Findings - Imported`` event stores AWS
    Security Finding Format objects under ``detail.findings``. AWS currently
    emits one finding per event; accepting a non-empty list keeps parsing
    robust for fixtures and future-compatible envelopes. The worker evaluates
    every item and applies the Product_B CRITICAL-only rule independently.
    """

    envelope = _decode_object(body)
    detail = envelope.get("detail")
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (TypeError, json.JSONDecodeError) as exc:
            raise FindingEventError("finding event detail is not valid JSON") from exc

    if isinstance(detail, dict) and "findings" in detail:
        findings = detail.get("findings")
        if not isinstance(findings, list) or not findings:
            raise FindingEventError("Security Hub event findings must be a non-empty list")
        if not all(isinstance(item, dict) for item in findings):
            raise FindingEventError("Security Hub event findings must contain objects")
        return [_parse_flat_finding(_securityhub_finding_to_flat(item)) for item in findings]

    return [_parse_flat_finding(_unwrap_eventbridge_envelope(envelope))]


def parse_finding_event(body: str | dict[str, Any]) -> FindingEvent:
    """Parse a body containing exactly one logical finding."""

    events = parse_finding_events(body)
    if len(events) != 1:
        raise FindingEventError("finding event contains multiple findings")
    return events[0]


def build_records(event: FindingEvent, judgement: FindingJudgement) -> tuple[FindingRecord, TriageRecord]:
    """Build the consistent finding + triage pair from an event and its judgement."""

    finding = FindingRecord(
        external_id=event.external_id,
        title=event.title,
        severity=judgement.assessed_severity,
        resource_type=event.resource_type,
        status=judgement.finding_status,
    )
    triage = TriageRecord(
        triage_status=judgement.triage_status,
        assessed_severity=judgement.assessed_severity,
        note=None,
    )
    return finding, triage


def register_finding(repository: FindingRepository, event: FindingEvent) -> FindingJudgement:
    """Judge then register the finding + triage consistently and idempotently."""

    judgement = judge_finding(event)
    finding, triage = build_records(event, judgement)
    repository.upsert_with_triage(finding, triage)
    return judgement


def handle_finding_body(repository: FindingRepository, body: str | dict[str, Any]) -> FindingJudgement:
    """Parse then register; returns the judgement for logging/testing."""

    event = parse_finding_event(body)
    return register_finding(repository, event)
