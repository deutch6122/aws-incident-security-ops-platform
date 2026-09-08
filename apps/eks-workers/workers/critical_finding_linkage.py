"""One-way Security Hub CRITICAL finding linkage from Product_A to Product_B.

Only a small, display-safe projection is written to ``public_status_items``.
There is deliberately no Product_B read path and no Product_B-to-Product_A
client. A deterministic hash of the Security Hub finding ID makes repeated
EventBridge/SQS deliveries overwrite the same DynamoDB item.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Protocol

from workers.finding import FindingEvent, FindingJudgement


class PublicStatusWriter(Protocol):
    def upsert_status(self, item: dict[str, Any]) -> None: ...


def critical_finding_status_id(external_id: str) -> str:
    """Return a deterministic, URL-safe DynamoDB/Portal status identifier."""

    digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()
    return f"security-finding-{digest[:32]}"


def build_critical_finding_status(
    event: FindingEvent, judgement: FindingJudgement
) -> dict[str, Any] | None:
    """Build the display-safe status item, or None for non-CRITICAL findings."""

    if judgement.assessed_severity != "critical":
        return None

    resource_type = event.resource_type or "Unknown"
    return {
        "status_id": critical_finding_status_id(event.external_id),
        "kind": "security_finding",
        "finding_id": event.external_id,
        "title": event.title,
        "state": "critical",
        "severity": "critical",
        "triage_status": judgement.triage_status,
        "resource_type": resource_type,
        "message": f"CRITICAL Security Hub finding detected for resource type {resource_type}.",
    }


def reflect_critical_finding(
    writer: PublicStatusWriter,
    event: FindingEvent,
    judgement: FindingJudgement,
) -> bool:
    """Upsert one CRITICAL status; return whether Product_B was written."""

    item = build_critical_finding_status(event, judgement)
    if item is None:
        return False
    writer.upsert_status(item)
    return True


@dataclass
class InMemoryPublicStatusWriter:
    """Test fake with the same deterministic-key overwrite behavior as PutItem."""

    rows: dict[str, dict[str, Any]] = field(default_factory=dict)

    def upsert_status(self, item: dict[str, Any]) -> None:
        self.rows[str(item["status_id"])] = dict(item)
