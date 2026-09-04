"""Task 7-only lookup port and in-memory fake for HTTP contract verification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ContractLookup(Protocol):
    def has_incident(self, identifier: int) -> bool: ...
    def has_finding(self, identifier: int) -> bool: ...
    def has_summary(self, period: str) -> bool: ...


@dataclass(slots=True)
class InMemoryContractLookup:
    incident_ids: set[int] = field(default_factory=set)
    finding_ids: set[int] = field(default_factory=set)
    summary_periods: set[str] = field(default_factory=set)

    def has_incident(self, identifier: int) -> bool:
        return identifier in self.incident_ids

    def has_finding(self, identifier: int) -> bool:
        return identifier in self.finding_ids

    def has_summary(self, period: str) -> bool:
        return period in self.summary_periods
