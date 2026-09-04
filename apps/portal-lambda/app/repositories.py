"""DynamoDB (boto3) implementations of the Portal_DB repository ports.

These satisfy the Protocols in ``app.stores`` and are used at runtime. All AWS
objects are created lazily: the boto3 resource is built on first use, never at
import time (Requirement: lazy init, no import-time AWS I/O). Tests use the
in-memory fakes instead, so this module's boto3 path is not exercised offline.

SEPARATION NOTE: every table referenced here is a Product_B table. There is no
client for Aurora/RDS/ECS/EKS/Product_A SQS. Only page_view_logs is written; the
status and report tables are read exclusively via GetItem/Scan.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.config import PortalSettings
from app.stores import PageViewLogRecord


class DynamoResourceProvider:
    """Lazily builds a single boto3 DynamoDB resource (Product_B only)."""

    def __init__(self, settings: PortalSettings) -> None:
        self._settings = settings
        self._resource: Any | None = None

    def resource(self) -> Any:
        if self._resource is None:
            # Imported and constructed lazily so importing this module performs
            # no AWS I/O and needs no AWS credentials.
            import boto3

            self._resource = boto3.resource(
                "dynamodb", region_name=self._settings.aws_region
            )
        return self._resource

    def table(self, name: str) -> Any:
        return self.resource().Table(name)


class DynamoPublicStatusRepository:
    """Read-only access to public_status_items (Requirement 10.1, 10.2)."""

    def __init__(self, provider: DynamoResourceProvider, settings: PortalSettings) -> None:
        self._provider = provider
        self._table_name = settings.public_status_items_table

    def list_items(self) -> list[dict[str, Any]]:
        table = self._provider.table(self._table_name)
        items: list[dict[str, Any]] = []
        response = table.scan()
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        return items

    def get_item(self, status_id: str) -> dict[str, Any] | None:
        table = self._provider.table(self._table_name)
        response = table.get_item(Key={"status_id": status_id})
        return response.get("Item")


class DynamoReportMetadataRepository:
    """Read-only access to report_metadata (Requirement 11.1, 11.2)."""

    def __init__(self, provider: DynamoResourceProvider, settings: PortalSettings) -> None:
        self._provider = provider
        self._table_name = settings.report_metadata_table

    def list_reports(self) -> list[dict[str, Any]]:
        table = self._provider.table(self._table_name)
        items: list[dict[str, Any]] = []
        response = table.scan()
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        return items

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        table = self._provider.table(self._table_name)
        response = table.get_item(Key={"report_id": report_id})
        return response.get("Item")


class DynamoPageViewLogRepository:
    """Append-only writes to page_view_logs (Requirement 10.3).

    This is the ONLY table the Portal_API writes; the IAM role (lambda module)
    scopes PutItem to page_view_logs only.
    """

    def __init__(self, provider: DynamoResourceProvider, settings: PortalSettings) -> None:
        self._provider = provider
        self._table_name = settings.page_view_logs_table

    def append(self, record: PageViewLogRecord) -> None:
        table = self._provider.table(self._table_name)
        item = {k: v for k, v in asdict(record).items() if v is not None}
        table.put_item(Item=item)

    def count(self) -> int:
        # Provided for interface parity; a full table count is not used at
        # runtime (page_view_logs is append-only and TTL-pruned).
        table = self._provider.table(self._table_name)
        return int(table.item_count)
