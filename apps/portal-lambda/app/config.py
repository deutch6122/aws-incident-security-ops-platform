"""Environment-backed Portal_API settings; no secret values live here.

Only non-secret configuration is read from the environment: the AWS region and
the four Product_B DynamoDB table names. There is no DB password, no connection
URL, and no Product_A configuration. Reading settings performs no AWS I/O.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class PortalConfigurationError(RuntimeError):
    """Configuration error that never embeds a secret value."""


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True, slots=True)
class PortalSettings:
    """Non-secret deployment settings for the Portal_API Lambda.

    Table names default to the Naming_Convention (ops-platform-dev-*) used by the
    dynamodb module (infra/modules/dynamodb). Only Product_B tables appear here.
    """

    aws_region: str = "ap-northeast-1"
    public_status_items_table: str = "ops-platform-dev-public-status-items"
    report_metadata_table: str = "ops-platform-dev-report-metadata"
    page_view_logs_table: str = "ops-platform-dev-page-view-logs"
    maintenance_windows_table: str = "ops-platform-dev-maintenance-windows"
    ttl_attribute_name: str = "expires_at"
    page_view_log_ttl_days: int = 30

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "PortalSettings":
        """Build settings from the environment without importing AWS clients."""

        env = environ if environ is not None else dict(os.environ)
        defaults = cls()

        def _int(name: str, default: int) -> int:
            raw = _clean(env.get(name))
            if raw is None:
                return default
            try:
                return int(raw)
            except ValueError as exc:
                raise PortalConfigurationError(f"{name} must be an integer") from exc

        return cls(
            aws_region=_clean(env.get("PORTAL_AWS_REGION")) or defaults.aws_region,
            public_status_items_table=(
                _clean(env.get("PORTAL_PUBLIC_STATUS_ITEMS_TABLE"))
                or defaults.public_status_items_table
            ),
            report_metadata_table=(
                _clean(env.get("PORTAL_REPORT_METADATA_TABLE"))
                or defaults.report_metadata_table
            ),
            page_view_logs_table=(
                _clean(env.get("PORTAL_PAGE_VIEW_LOGS_TABLE"))
                or defaults.page_view_logs_table
            ),
            maintenance_windows_table=(
                _clean(env.get("PORTAL_MAINTENANCE_WINDOWS_TABLE"))
                or defaults.maintenance_windows_table
            ),
            ttl_attribute_name=(
                _clean(env.get("PORTAL_TTL_ATTRIBUTE_NAME")) or defaults.ttl_attribute_name
            ),
            page_view_log_ttl_days=_int(
                "PORTAL_PAGE_VIEW_LOG_TTL_DAYS", defaults.page_view_log_ttl_days
            ),
        )
