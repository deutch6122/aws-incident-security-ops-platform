# Feature: aws-incident-security-ops-platform, Property 9: For any 対象年月とその期間に属する incidents / findings / alarm_events の集合について、生成する monthly_summaries の各件数は実件数と一致し、かつ同一年月に対する再集計後も 1 行のみでなければならない
# **Validates: Requirements 7.1, 7.2**
"""Property 9: monthly aggregation consistency and re-aggregation idempotency.

Testing substitution note: tasks.md 10.7 references testcontainers. Per the
execution constraints (no Docker / no real DB), this property uses the in-memory
monthly-summary store keyed on period, which replicates the
monthly_summaries.period UNIQUE + ON CONFLICT DO UPDATE semantics.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from workers.stores import InMemoryMonthlySummaryStore
from workers.summary import TimedRecord, generate_monthly_summary, period_of

# Generate timestamps across a small window of months so some fall inside the
# target period and some outside it.
_years = st.integers(min_value=2023, max_value=2025)
_months = st.integers(min_value=1, max_value=12)
_days = st.integers(min_value=1, max_value=28)


@st.composite
def _timed(draw) -> TimedRecord:
    return TimedRecord(
        created_at=datetime(draw(_years), draw(_months), draw(_days), 12, 0, tzinfo=timezone.utc)
    )


def _expected_count(records: list[TimedRecord], period: str) -> int:
    return sum(1 for r in records if period_of(r.created_at) == period)


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(
    incidents=st.lists(_timed(), max_size=25),
    findings=st.lists(_timed(), max_size=25),
    alarms=st.lists(_timed(), max_size=25),
    year=_years,
    month=_months,
)
def test_monthly_summary_consistency_and_idempotency(
    incidents: list[TimedRecord],
    findings: list[TimedRecord],
    alarms: list[TimedRecord],
    year: int,
    month: int,
) -> None:
    period = f"{year:04d}{month:02d}"
    store = InMemoryMonthlySummaryStore()

    record = generate_monthly_summary(store, period, incidents, findings, alarms)

    # Counts equal the true number of records inside the target period.
    assert record.incident_count == _expected_count(incidents, period)
    assert record.finding_count == _expected_count(findings, period)
    assert record.alarm_count == _expected_count(alarms, period)

    # Re-aggregating the same period keeps exactly one row with the latest values.
    record2 = generate_monthly_summary(store, period, incidents, findings, alarms)
    assert store.count() == 1
    stored = store.get(period)
    assert stored is not None
    assert stored.incident_count == record2.incident_count
    assert stored.finding_count == record2.finding_count
    assert stored.alarm_count == record2.alarm_count
