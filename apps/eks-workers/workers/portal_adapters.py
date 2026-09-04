"""boto3-backed adapters for the A->B linkage write ports (Product_B).

These implement the write-only Protocols in ``workers.linkage`` against real AWS
resources (S3 for Portal_Storage, DynamoDB for report_metadata /
public_status_items). Every boto3 client/resource is created LAZILY: importing
this module performs no AWS I/O and needs no credentials. Tests use the
in-memory fakes in ``workers.linkage`` instead, so this module's boto3 path is
not exercised offline.

DIRECTIONALITY (Requirement 14.3): these adapters only WRITE into Product_B.
There is no read path back to Product_B and no reference to Product_A resources.
The linkage is a one-way A -> B hand-off executed by Cronjob_Summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PortalTargets:
    """Non-secret Product_B target references for the linkage (from env)."""

    aws_region: str = "ap-northeast-1"
    reports_bucket: str | None = None
    report_metadata_table: str = "ops-platform-dev-report-metadata"
    public_status_items_table: str = "ops-platform-dev-public-status-items"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "PortalTargets":
        import os

        env = environ if environ is not None else dict(os.environ)

        def _clean(name: str) -> str | None:
            value = env.get(name)
            if value is None:
                return None
            stripped = value.strip()
            return stripped or None

        defaults = cls()
        return cls(
            aws_region=_clean("WORKER_AWS_REGION") or defaults.aws_region,
            reports_bucket=_clean("PORTAL_REPORTS_BUCKET"),
            report_metadata_table=(
                _clean("PORTAL_REPORT_METADATA_TABLE") or defaults.report_metadata_table
            ),
            public_status_items_table=(
                _clean("PORTAL_PUBLIC_STATUS_ITEMS_TABLE")
                or defaults.public_status_items_table
            ),
        )

    def require_reports_bucket(self) -> str:
        if not self.reports_bucket:
            raise RuntimeError("PORTAL_REPORTS_BUCKET is not configured")
        return self.reports_bucket


class S3PortalStorage:
    """Puts report objects under Portal_Storage reports/* (write-only)."""

    def __init__(self, targets: PortalTargets) -> None:
        self._targets = targets
        self._client: Any | None = None

    def _s3(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("s3", region_name=self._targets.aws_region)
        return self._client

    def put_report(self, key: str, body: bytes) -> None:
        self._s3().put_object(
            Bucket=self._targets.require_reports_bucket(),
            Key=key,
            Body=body,
            ContentType="application/json",
        )


class _DynamoTableWriter:
    def __init__(self, targets: PortalTargets, table_name: str) -> None:
        self._targets = targets
        self._table_name = table_name
        self._resource: Any | None = None

    def _table(self) -> Any:
        if self._resource is None:
            import boto3

            self._resource = boto3.resource(
                "dynamodb", region_name=self._targets.aws_region
            )
        return self._resource.Table(self._table_name)


class DynamoReportMetadataWriter(_DynamoTableWriter):
    """Upserts report_metadata keyed on report_id (PutItem overwrites)."""

    def __init__(self, targets: PortalTargets) -> None:
        super().__init__(targets, targets.report_metadata_table)

    def upsert_report(self, item: dict[str, Any]) -> None:
        self._table().put_item(Item=dict(item))


class DynamoPublicStatusWriter(_DynamoTableWriter):
    """Upserts public_status_items keyed on status_id (PutItem overwrites)."""

    def __init__(self, targets: PortalTargets) -> None:
        super().__init__(targets, targets.public_status_items_table)

    def upsert_status(self, item: dict[str, Any]) -> None:
        self._table().put_item(Item=dict(item))
