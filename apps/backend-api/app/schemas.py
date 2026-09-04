"""Pydantic request/response schemas for the Task 8 business APIs.

Schemas never expose secrets, credentials, or connection strings; they mirror
only the non-sensitive columns of the Aurora tables (see db/models.py).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

YYYYMM_PATTERN = re.compile(r"^\d{6}$")


def is_valid_period(period: str) -> bool:
    """Validate a ``yyyymm`` period string (year 0001-9999, month 01-12)."""

    if not YYYYMM_PATTERN.fullmatch(period):
        return False
    month = int(period[4:])
    return 1 <= month <= 12


class _ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----- Incidents -----------------------------------------------------------


class IncidentCreate(BaseModel):
    """Incident creation payload. Required fields mirror the NOT NULL columns."""

    model_config = ConfigDict(extra="ignore")

    external_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    status: str = Field(default="open", min_length=1)
    description: str | None = None


class IncidentCommentOut(_ORMModel):
    id: int
    incident_id: int
    author: str
    body: str
    created_at: datetime | None = None


class IncidentOut(_ORMModel):
    id: int
    external_id: str
    title: str
    severity: str
    status: str
    description: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IncidentDetailOut(IncidentOut):
    comments: list[IncidentCommentOut] = Field(default_factory=list)


class IncidentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = Field(min_length=1)
    actor: str | None = None


# ----- Findings ------------------------------------------------------------


class FindingTriageOut(_ORMModel):
    id: int
    finding_id: int
    triage_status: str
    assessed_severity: str
    note: str | None = None
    created_at: datetime | None = None


class FindingOut(_ORMModel):
    id: int
    external_id: str
    title: str
    severity: str
    resource_type: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FindingDetailOut(FindingOut):
    triage: list[FindingTriageOut] = Field(default_factory=list)


# ----- Monthly summary -----------------------------------------------------


class MonthlySummaryOut(_ORMModel):
    id: int
    period: str
    incident_count: int
    finding_count: int
    alarm_count: int
    detail: dict[str, Any] | None = None
    generated_at: datetime | None = None


# ----- Dashboard -----------------------------------------------------------


class DashboardSummaryOut(BaseModel):
    incident_count: int
    finding_count: int
    status_breakdown: dict[str, int]
