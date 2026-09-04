"""Pure aggregation and transformation functions with no DB dependencies."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol


class HasStatus(Protocol):
    status: str


@dataclass(frozen=True, slots=True)
class SummaryCounts:
    incident_count: int
    finding_count: int
    alarm_count: int


def status_breakdown(records: Iterable[HasStatus]) -> dict[str, int]:
    """Count records by status without mutating input records."""

    return dict(sorted(Counter(record.status for record in records).items()))


def merge_status_counts(rows: Iterable[tuple[str, int]]) -> dict[str, int]:
    """Convert grouped DB rows to a deterministic mapping, merging duplicate keys."""

    totals: Counter[str] = Counter()
    for status, count in rows:
        if count < 0:
            raise ValueError("aggregate counts cannot be negative")
        totals[status] += count
    return dict(sorted(totals.items()))


def make_summary_counts(
    incident_statuses: Mapping[str, int],
    finding_statuses: Mapping[str, int],
    alarm_count: int,
) -> SummaryCounts:
    """Build summary totals from already grouped values."""

    if alarm_count < 0 or any(value < 0 for value in incident_statuses.values()) or any(
        value < 0 for value in finding_statuses.values()
    ):
        raise ValueError("aggregate counts cannot be negative")
    return SummaryCounts(
        incident_count=sum(incident_statuses.values()),
        finding_count=sum(finding_statuses.values()),
        alarm_count=alarm_count,
    )
