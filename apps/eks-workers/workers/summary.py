"""Cronjob_Summary (monthly-summary-cronjob) core aggregation logic.

Aggregates the incidents / findings / alarm_events that fall inside a target
month (YYYYMM) into a MonthlySummaryRecord, then upserts it keyed on period.
Because period is UNIQUE, re-aggregating the same month updates the single row
with the latest values (Requirement 7.1, 7.2, Property 9).

A->B linkage (writing report files to Portal_Storage and metadata to Portal_DB)
is Phase 3 and is intentionally NOT implemented here.

This module is pure/dependency-free: it aggregates from provided iterables and
writes through a MonthlySummaryRepository, so it works with the SQLAlchemy repo
or the in-memory fake.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from workers.stores import MonthlySummaryRecord, MonthlySummaryRepository

_PERIOD_RE = re.compile(r"^(\d{4})(0[1-9]|1[0-2])$")


class HasTimestamp(Protocol):
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TimedRecord:
    """Minimal record with a timezone-aware timestamp used for period filtering."""

    created_at: datetime


class SummaryError(ValueError):
    """Raised for an invalid target period."""


def validate_period(period: str) -> str:
    """Validate a YYYYMM period string, returning it normalized."""

    if not isinstance(period, str) or not _PERIOD_RE.match(period):
        raise SummaryError("period must be a YYYYMM string with month 01-12")
    return period


def period_of(moment: datetime) -> str:
    """Return the YYYYMM period a timestamp belongs to (UTC)."""

    utc = moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    return f"{utc.year:04d}{utc.month:02d}"


def _in_period(record: HasTimestamp, period: str) -> bool:
    return period_of(record.created_at) == period


def count_in_period(records: Iterable[HasTimestamp], period: str) -> int:
    """Count records whose timestamp falls in the target period."""

    return sum(1 for record in records if _in_period(record, period))


def aggregate_period(
    period: str,
    incidents: Iterable[HasTimestamp],
    findings: Iterable[HasTimestamp],
    alarm_events: Iterable[HasTimestamp],
) -> MonthlySummaryRecord:
    """Build the monthly summary counts from records that fall inside the period."""

    validate_period(period)
    return MonthlySummaryRecord(
        period=period,
        incident_count=count_in_period(incidents, period),
        finding_count=count_in_period(findings, period),
        alarm_count=count_in_period(alarm_events, period),
        detail=None,
    )


def generate_monthly_summary(
    repository: MonthlySummaryRepository,
    period: str,
    incidents: Iterable[HasTimestamp],
    findings: Iterable[HasTimestamp],
    alarm_events: Iterable[HasTimestamp],
) -> MonthlySummaryRecord:
    """Aggregate then upsert the monthly summary (ON CONFLICT (period) DO UPDATE)."""

    record = aggregate_period(period, incidents, findings, alarm_events)
    repository.upsert(record)
    return record
