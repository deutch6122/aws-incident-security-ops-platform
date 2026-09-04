#!/usr/bin/env python3
"""Seed dummy monthly reports and public status items into Product_B.

Task 18.1 — Requirements 14.1, 14.2. This is the A->B one-way direction:
it writes NON-SENSITIVE, DUMMY data to Product_B only:

* report metadata  -> Portal_DB DynamoDB ``report_metadata`` table
* report files      -> Portal_Storage S3 (``reports/<period>/summary.json``)
* public status     -> Portal_DB DynamoDB ``public_status_items`` table

It never reads from or writes to Product_A (Aurora / ECS / EKS). By default it
prints the payloads (dry-run); ``--execute`` performs the DynamoDB puts and the
S3 upload.

Usage:
    python3 scripts/seed_portal_reports.py                # dry-run (default)
    python3 scripts/seed_portal_reports.py --count 6      # 6 monthly periods
    python3 scripts/seed_portal_reports.py --execute \
        --report-metadata-table ops-platform-dev-report-metadata \
        --public-status-table ops-platform-dev-public-status-items \
        --reports-bucket ops-platform-dev-portal-REPLACE_WITH_SUFFIX

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

DEFAULT_REPORT_METADATA_TABLE = "ops-platform-dev-report-metadata"
DEFAULT_PUBLIC_STATUS_TABLE = "ops-platform-dev-public-status-items"
# Bucket name intentionally a placeholder; the real suffix is resolved at deploy
# time. No real bucket / domain is embedded.
DEFAULT_REPORTS_BUCKET = "ops-platform-dev-portal-REPLACE_WITH_SUFFIX"

_STATUS_VALUES = ("operational", "degraded", "maintenance")


def _period(index: int) -> str:
    """Return a YYYYMM period string for the *index*-th sample month in 2024."""

    month = ((index - 1) % 12) + 1
    return f"2024{month:02d}"


def build_report_items(count: int) -> list[dict]:
    """Build dummy report_metadata items (one per period). Placeholders only."""

    items: list[dict] = []
    for i in range(1, count + 1):
        period = _period(i)
        item = {
            "report_id": f"report-{period}",
            "period": period,
            "title": f"Sample monthly report {period}",
            # S3 object key only — no bucket/domain, no signed URL, no real ARN.
            "storage_key": f"reports/{period}/summary.json",
            "summary": "Sample dummy monthly report for dev/MVP seeding.",
            "published_at": f"{period[:4]}-{period[4:]}-01T00:00:00Z",
        }
        assert_non_sensitive(item)
        items.append(item)
    return items


def build_public_status_items(count: int) -> list[dict]:
    """Build dummy public_status_items. Placeholders only."""

    items: list[dict] = []
    for i in range(1, count + 1):
        item = {
            "status_id": f"status-{i:04d}",
            "title": f"Sample service status {i:04d}",
            "status": _STATUS_VALUES[(i - 1) % len(_STATUS_VALUES)],
            "message": "Sample dummy public status for dev/MVP seeding.",
            "updated_at": f"2024-01-{(i % 28) + 1:02d}T00:00:00Z",
        }
        assert_non_sensitive(item)
        items.append(item)
    return items


def build_report_file(period: str) -> dict:
    """Build the dummy report file body stored at reports/<period>/summary.json."""

    body = {
        "period": period,
        "incident_count": 0,
        "finding_count": 0,
        "overview": "Sample dummy summary. Non-sensitive placeholder content.",
    }
    assert_non_sensitive(body)
    return body


def _dry_run(report_items: list[dict], status_items: list[dict]) -> None:
    print_dry_run("report_metadata", report_items)
    print_dry_run("public_status_item", status_items)
    files = [
        {"key": item["storage_key"], "body": build_report_file(item["period"])}
        for item in report_items
    ]
    print_dry_run("report-file(S3)", files)


def _execute(  # pragma: no cover - only under --execute
    report_items: list[dict],
    status_items: list[dict],
    region: str,
    report_metadata_table: str,
    public_status_table: str,
    reports_bucket: str,
) -> None:
    dynamodb = get_boto3_client("dynamodb", region)
    s3 = get_boto3_client("s3", region)

    for item in report_items:
        dynamodb.put_item(
            TableName=report_metadata_table,
            Item={k: {"S": str(v)} for k, v in item.items()},
        )
        body = json.dumps(build_report_file(item["period"]), ensure_ascii=False)
        s3.put_object(
            Bucket=reports_bucket,
            Key=item["storage_key"],
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
    for item in status_items:
        dynamodb.put_item(
            TableName=public_status_table,
            Item={k: {"S": str(v)} for k, v in item.items()},
        )
    print(
        f"[execute] wrote {len(report_items)} report(s) and "
        f"{len(status_items)} status item(s) to Product_B."
    )


def run(options: RunOptions, args) -> None:
    report_items = build_report_items(options.count)
    status_items = build_public_status_items(options.count)
    if options.dry_run:
        _dry_run(report_items, status_items)
        return
    _execute(  # pragma: no cover
        report_items,
        status_items,
        options.region,
        args.report_metadata_table,
        args.public_status_table,
        args.reports_bucket,
    )


def main(argv: list[str] | None = None) -> int:
    parser = base_arg_parser(__doc__ or "Seed dummy Product_B reports/status.")
    parser.add_argument("--report-metadata-table", default=DEFAULT_REPORT_METADATA_TABLE)
    parser.add_argument("--public-status-table", default=DEFAULT_PUBLIC_STATUS_TABLE)
    parser.add_argument("--reports-bucket", default=DEFAULT_REPORTS_BUCKET)
    options = parse_options(parser, argv)
    args = parser.parse_args(argv)
    run(options, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
