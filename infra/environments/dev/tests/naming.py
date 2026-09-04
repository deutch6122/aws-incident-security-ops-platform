"""Pure naming helper mirroring the dev Terraform naming contract."""

from __future__ import annotations

import re

PROJECT = "ops-platform"
ENVIRONMENT = "dev"
NAME_PREFIX = f"{PROJECT}-{ENVIRONMENT}"
MAX_RESOURCE_NAME_LENGTH = 63

_RESOURCE_SUFFIX_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def resource_name(resource: str) -> str:
    """Return ``ops-platform-dev-<resource>`` or reject an unsafe suffix.

    Valid suffixes contain lowercase ASCII letters and digits grouped by single
    hyphens. The resulting name is capped at 63 characters for broad AWS naming
    compatibility. Terraform enforces the same contract in ``variables.tf``.
    """
    if not isinstance(resource, str):
        raise TypeError("resource suffix must be a string")

    candidate = f"{NAME_PREFIX}-{resource}"
    if (
        _RESOURCE_SUFFIX_PATTERN.fullmatch(resource) is None
        or len(candidate) > MAX_RESOURCE_NAME_LENGTH
    ):
        raise ValueError(
            "resource suffix must use lowercase alphanumeric segments separated "
            "by single hyphens and produce a name no longer than 63 characters"
        )

    return candidate
