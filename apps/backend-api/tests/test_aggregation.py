from dataclasses import dataclass

import pytest

from app.domain.aggregation import make_summary_counts, merge_status_counts, status_breakdown


@dataclass
class Record:
    status: str


def test_status_breakdown_is_sorted_and_counts_duplicates() -> None:
    records = [Record("open"), Record("closed"), Record("open")]
    assert status_breakdown(records) == {"closed": 1, "open": 2}


def test_merge_status_counts_merges_duplicate_group_rows() -> None:
    assert merge_status_counts([("open", 2), ("closed", 1), ("open", 3)]) == {
        "closed": 1,
        "open": 5,
    }


def test_make_summary_counts_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        make_summary_counts({"open": -1}, {}, 0)
