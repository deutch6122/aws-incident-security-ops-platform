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


def parse_finding_event(body: str | dict[str, Any]) -> FindingEvent:
    """Parse a JSON body (or already-decoded dict) into a FindingEvent."""

    if isinstance(body, str):
        try:
            raw: Any = json.loads(body)
        except (TypeError, json.JSONDecodeError) as exc:
            raise FindingEventError("finding event body is not valid JSON") from exc
    else:
        raw = body

    if not isinstance(raw, dict):
        raise FindingEventError("finding event must be a JSON object")

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

    raw_status = raw.get("status")
    if raw_status is not None and not isinstance(raw_status, str):
        raise FindingEventError("finding event status must be text when present")

    return FindingEvent(
        external_id=external_id.strip(),
        title=title.strip(),
        raw_severity=raw_severity.strip(),
        resource_type=resource_type.strip() if isinstance(resource_type, str) and resource_type.strip() else None,
        raw_status=raw_status,
    )


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
