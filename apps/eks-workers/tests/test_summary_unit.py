"""Unit tests for Cronjob_Summary period computation and aggregation."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.stores import InMemoryMonthlySummaryStore
from workers.summary import (
    SummaryError,
    TimedRecord,
    aggregate_period,
    generate_monthly_summary,
    period_of,
    validate_period,
)


def _at(year: int, month: int, day: int = 15) -> TimedRecord:
    return TimedRecord(created_at=datetime(year, month, day, 12, 0, tzinfo=timezone.utc))


def test_validate_period_accepts_valid_and_rejects_invalid() -> None:
    assert validate_period("202406") == "202406"
    for bad in ("2024", "202413", "202400", "abc", "20240a"):
        with pytest.raises(SummaryError):
            validate_period(bad)


def test_period_of_uses_utc_month() -> None:
    assert period_of(datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)) == "202406"


def test_aggregate_counts_only_in_period() -> None:
    incidents = [_at(2024, 6), _at(2024, 6), _at(2024, 5)]
    findings = [_at(2024, 6), _at(2024, 7)]
    alarms = [_at(2024, 6), _at(2024, 6), _at(2024, 6)]
    record = aggregate_period("202406", incidents, findings, alarms)
    assert record.incident_count == 2
    assert record.finding_count == 1
    assert record.alarm_count == 3


def test_reaggregation_keeps_single_row_with_latest_values() -> None:
    store = InMemoryMonthlySummaryStore()
    generate_monthly_summary(store, "202406", [_at(2024, 6)], [], [])
    generate_monthly_summary(store, "202406", [_at(2024, 6), _at(2024, 6)], [_at(2024, 6)], [])
    assert store.count() == 1
    row = store.get("202406")
    assert row is not None
    assert row.incident_count == 2
    assert row.finding_count == 1
