#!/usr/bin/env python3
"""Seed dummy Security-Finding-style events into Product_A's async path.

Task 18.1 — Requirement 6.1. Generates NON-SENSITIVE, DUMMY finding events and,
by default, prints them (dry-run). With ``--execute`` it puts the events onto
the EventBridge bus (source ``ops-platform.sample``) which the messaging module
routes to SQS for Worker_Finding to consume.

Usage:
    python3 scripts/seed_finding_events.py                # dry-run (default)
    python3 scripts/seed_finding_events.py --count 5      # generate 5, dry-run
    python3 scripts/seed_finding_events.py --execute      # actually put events

Safety: dry-run by default; nothing reaches AWS without --execute. No real
ARNs, account ids, tokens, secrets, or real domains — placeholders only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed.common import (  # noqa: E402
    RunOptions,
    assert_non_sensitive,
    base_arg_parser,
    get_boto3_client,
    parse_options,
    print_dry_run,
)

EVENT_SOURCE = "ops-platform.sample"
DETAIL_TYPE = "SecurityFinding"

_SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
_RESOURCE_TYPES = ("AwsEc2Instance", "AwsS3Bucket", "AwsIamRole")
_WORKFLOW_STATES = ("NEW", "NOTIFIED", "RESOLVED")


def build_finding_events(count: int) -> list[dict]:
    """Build *count* dummy Finding events. All values are placeholders."""

    events: list[dict] = []
    for i in range(1, count + 1):
        detail = {
            "external_id": f"SAMPLE-FINDING-{i:04d}",
            "title": f"Sample finding {i:04d}",
            "severity": _SEVERITIES[(i - 1) % len(_SEVERITIES)],
            "resource_type": _RESOURCE_TYPES[(i - 1) % len(_RESOURCE_TYPES)],
            "resource_ref": f"ops-platform-dev-resource-{i:04d}",  # placeholder, not an ARN
            "workflow_state": _WORKFLOW_STATES[(i - 1) % len(_WORKFLOW_STATES)],
            "description": "Sample dummy security finding for dev/MVP seeding.",
            "detected_at": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
        }
        event = {
            "Source": EVENT_SOURCE,
            "DetailType": DETAIL_TYPE,
            "Detail": json.dumps(detail, ensure_ascii=False),
        }
        assert_non_sensitive(event)
        events.append(event)
    return events


def send_events(events: list[dict], region: str) -> int:  # pragma: no cover - only under --execute
    client = get_boto3_client("events", region)
    entries = [
        {"Source": e["Source"], "DetailType": e["DetailType"], "Detail": e["Detail"]}
        for e in events
    ]
    resp = client.put_events(Entries=entries)
    failed = resp.get("FailedEntryCount", 0)
    print(f"[execute] put {len(entries)} event(s) to EventBridge; failed={failed}")
    return len(entries) - failed


def run(options: RunOptions) -> int:
    events = build_finding_events(options.count)
    if options.dry_run:
        return print_dry_run("finding-event", events)
    return send_events(events, options.region)


def main(argv: list[str] | None = None) -> int:
    parser = base_arg_parser(__doc__ or "Seed dummy finding events.")
    options = parse_options(parser, argv)
    run(options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
