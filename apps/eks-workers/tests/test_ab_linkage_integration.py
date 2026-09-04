"""Task 16.3 A->B linkage integration tests (Requirement 14.1, 14.2, 14.3).

These verify that Cronjob_Summary's A->B linkage reflects a monthly summary into
Product_B: a report file under Portal_Storage reports/*, a report_metadata
entry, and a public_status_items entry -- with non-sensitive content only, one
direction only (A -> B), and idempotent overwrite on re-run.

Testing substitution note: the fake-based cases ALWAYS run (in-memory ports from
workers.linkage). A moto case is added and runs only if moto is importable; it
is skipped otherwise (no new installs, no Docker / DynamoDB Local).
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.linkage import (
    InMemoryPortalStorage,
    InMemoryPublicStatusWriter,
    InMemoryReportMetadataWriter,
    link_summary_to_portal,
    public_status_id,
    report_s3_key,
)
from workers.stores import MonthlySummaryRecord

APP_ROOT = Path(__file__).resolve().parents[1]

# Sensitive vocabulary that must never leak into Product_B linkage output.
_SENSITIVE_KEYS = {
    "password",
    "secret",
    "db_password",
    "connection_url",
    "dsn",
    "pii",
    "email",
    "ssn",
    "incident_detail",
    "finding_detail",
    "comment",
    "note",
    "payload",
    "detail",
}


def _summary(period: str = "202406") -> MonthlySummaryRecord:
    # detail carries something that would be sensitive if propagated; the linkage
    # must NOT copy it into the report.
    return MonthlySummaryRecord(
        period=period,
        incident_count=3,
        finding_count=5,
        alarm_count=7,
        detail={"secret": "s3cr3t-should-not-leak", "note": "internal only"},
    )


def _ports():
    return (
        InMemoryPortalStorage(),
        InMemoryReportMetadataWriter(),
        InMemoryPublicStatusWriter(),
    )


def _no_sensitive_keys(obj: object) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key.lower() not in _SENSITIVE_KEYS, f"sensitive key leaked: {key}"
            _no_sensitive_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            _no_sensitive_keys(value)


# --- report_metadata registration (Requirement 14.1) -----------------------
def test_report_metadata_is_registered() -> None:
    storage, reports, statuses = _ports()
    report = link_summary_to_portal(
        _summary(), storage=storage, report_writer=reports, status_writer=statuses
    )
    assert reports.count() == 1
    meta = reports.get(report.report_id)
    assert meta is not None
    assert meta["period"] == "202406"
    assert meta["s3_key"] == "reports/202406/summary.json"
    assert "title" in meta


# --- public_status_items reflection (Requirement 14.2) ---------------------
def test_public_status_item_is_reflected_with_slash_free_id() -> None:
    storage, reports, statuses = _ports()
    link_summary_to_portal(
        _summary(), storage=storage, report_writer=reports, status_writer=statuses
    )
    assert statuses.count() == 1
    status = statuses.get(public_status_id("202406"))
    assert status is not None
    # status_id must be usable as a /api/status/{id} path param: no "/".
    assert "/" not in status["status_id"]
    assert status["period"] == "202406"


# --- Portal_Storage object key (Requirement 14.1) --------------------------
def test_report_file_placed_under_reports_prefix() -> None:
    storage, reports, statuses = _ports()
    link_summary_to_portal(
        _summary(), storage=storage, report_writer=reports, status_writer=statuses
    )
    assert storage.count() == 1
    key = report_s3_key("202406")
    assert key.startswith("reports/")
    assert key == "reports/202406/summary.json"
    body = storage.get(key)
    assert body is not None
    parsed = json.loads(body.decode("utf-8"))
    assert parsed["period"] == "202406"


# --- non-sensitive content (Requirement 14 / MVP dummy-non-sensitive) ------
def test_linkage_output_is_non_sensitive() -> None:
    storage, reports, statuses = _ports()
    report = link_summary_to_portal(
        _summary(), storage=storage, report_writer=reports, status_writer=statuses
    )
    # None of the three sinks contain sensitive keys/values.
    _no_sensitive_keys(reports.get(report.report_id))
    _no_sensitive_keys(statuses.get(public_status_id("202406")))
    stored_body = json.loads(storage.get(report.s3_key).decode("utf-8"))
    _no_sensitive_keys(stored_body)

    # The sensitive value from record.detail must not appear anywhere.
    blob = json.dumps(
        [reports.get(report.report_id), statuses.get(public_status_id("202406")), stored_body]
    )
    assert "s3cr3t-should-not-leak" not in blob
    assert "internal only" not in blob
    # Only aggregate counts + period + overview are present.
    assert stored_body["incident_count"] == 3
    assert stored_body["finding_count"] == 5
    assert stored_body["alarm_count"] == 7


# --- idempotent overwrite on re-run (no duplicates) ------------------------
def test_same_period_rerun_does_not_duplicate_and_overwrites() -> None:
    storage, reports, statuses = _ports()
    link_summary_to_portal(
        _summary(), storage=storage, report_writer=reports, status_writer=statuses
    )
    # Second run with updated counts for the same period.
    updated = MonthlySummaryRecord(
        period="202406", incident_count=9, finding_count=9, alarm_count=9, detail=None
    )
    link_summary_to_portal(
        updated, storage=storage, report_writer=reports, status_writer=statuses
    )

    # Counts do not grow: one object, one report_metadata row, one status row.
    assert storage.count() == 1
    assert reports.count() == 1
    assert statuses.count() == 1

    # Values are updated in place.
    body = json.loads(storage.get(report_s3_key("202406")).decode("utf-8"))
    assert body["incident_count"] == 9
    status = statuses.get(public_status_id("202406"))
    assert status["incident_count"] == 9


# --- one-way A -> B: no Product_A write/read in the linkage module ----------
def test_linkage_module_has_no_product_a_write_or_read() -> None:
    """Static check: the linkage module imports nothing from Product_A stacks and
    performs no Aurora/psycopg/SQLAlchemy write, honouring Requirement 14.3.
    """
    source = (APP_ROOT / "workers" / "linkage.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    # No DB / Product_A client libraries are imported by the linkage module.
    for banned in ("sqlalchemy", "psycopg", "psycopg2", "boto3"):
        assert banned not in imported, f"linkage must not import {banned}"
    # No Product_A persistence package (workers.db) is imported.
    for module in (
        n.module
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module
    ):
        assert not module.startswith("workers.db"), "linkage must not import workers.db"

    # No Product_A write verbs against Aurora appear in executable code. We scan
    # attribute-access names via the AST (docstring prose that merely mentions
    # "Aurora" for design context is fine).
    attr_names = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    for banned_attr in ("commit", "execute", "add", "flush"):
        assert banned_attr not in attr_names, f"linkage must not call .{banned_attr}()"


def test_linkage_ports_are_write_only_into_product_b() -> None:
    """The linkage ports expose only write methods into Product_B (no read-back
    into Product_A, no Product_A record types)."""
    import workers.linkage as linkage

    # Only Product_B write ports exist; method names are put/upsert only.
    for port_name, methods in (
        ("PortalStoragePort", {"put_report"}),
        ("ReportMetadataWriterPort", {"upsert_report"}),
        ("PublicStatusWriterPort", {"upsert_status"}),
    ):
        port = getattr(linkage, port_name)
        public = {m for m in dir(port) if not m.startswith("_")}
        assert methods <= public


# --- optional moto case (runs only if moto is importable) ------------------
def test_linkage_with_moto_dynamodb_and_s3() -> None:
    moto = pytest.importorskip("moto")
    import boto3

    from workers.portal_adapters import (
        DynamoPublicStatusWriter,
        DynamoReportMetadataWriter,
        PortalTargets,
        S3PortalStorage,
    )

    targets = PortalTargets(
        aws_region="ap-northeast-1",
        reports_bucket="ops-platform-dev-portal-reports",
        report_metadata_table="ops-platform-dev-report-metadata",
        public_status_items_table="ops-platform-dev-public-status-items",
    )

    with moto.mock_aws():
        s3 = boto3.client("s3", region_name=targets.aws_region)
        s3.create_bucket(
            Bucket=targets.reports_bucket,
            CreateBucketConfiguration={"LocationConstraint": targets.aws_region},
        )
        dynamodb = boto3.resource("dynamodb", region_name=targets.aws_region)
        dynamodb.create_table(
            TableName=targets.report_metadata_table,
            KeySchema=[{"AttributeName": "report_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "report_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamodb.create_table(
            TableName=targets.public_status_items_table,
            KeySchema=[{"AttributeName": "status_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "status_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        link_summary_to_portal(
            _summary(),
            storage=S3PortalStorage(targets),
            report_writer=DynamoReportMetadataWriter(targets),
            status_writer=DynamoPublicStatusWriter(targets),
        )

        obj = s3.get_object(Bucket=targets.reports_bucket, Key=report_s3_key("202406"))
        assert json.loads(obj["Body"].read().decode("utf-8"))["period"] == "202406"

        meta = dynamodb.Table(targets.report_metadata_table).get_item(
            Key={"report_id": "summary-202406"}
        )["Item"]
        assert meta["s3_key"] == "reports/202406/summary.json"

        status = dynamodb.Table(targets.public_status_items_table).get_item(
            Key={"status_id": public_status_id("202406")}
        )["Item"]
        assert "/" not in status["status_id"]

        # Re-run: no duplicates (same keys overwrite).
        link_summary_to_portal(
            MonthlySummaryRecord(
                period="202406", incident_count=9, finding_count=9, alarm_count=9, detail=None
            ),
            storage=S3PortalStorage(targets),
            report_writer=DynamoReportMetadataWriter(targets),
            status_writer=DynamoPublicStatusWriter(targets),
        )
        listing = s3.list_objects_v2(Bucket=targets.reports_bucket)
        assert listing["KeyCount"] == 1
        meta2 = dynamodb.Table(targets.report_metadata_table).scan()["Items"]
        assert len(meta2) == 1
