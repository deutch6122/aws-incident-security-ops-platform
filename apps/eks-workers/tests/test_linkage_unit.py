"""Unit tests for the A->B linkage derivation (workers.linkage)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.linkage import (
    REPORTS_PREFIX,
    build_linkage_report,
    public_status_id,
    report_id_of,
    report_s3_key,
)
from workers.stores import MonthlySummaryRecord
from workers.summary import SummaryError


def test_report_s3_key_uses_reports_prefix_and_period() -> None:
    assert report_s3_key("202406") == f"{REPORTS_PREFIX}/202406/summary.json"


def test_ids_are_slash_free_and_deterministic() -> None:
    assert "/" not in public_status_id("202406")
    assert "/" not in report_id_of("202406")
    assert public_status_id("202406") == public_status_id("202406")
    assert report_id_of("202406") == "summary-202406"


def test_invalid_period_rejected() -> None:
    for bad in ("2024", "202413", "abc"):
        with pytest.raises(SummaryError):
            report_s3_key(bad)


def test_build_linkage_report_copies_counts_only() -> None:
    record = MonthlySummaryRecord(
        period="202406",
        incident_count=2,
        finding_count=4,
        alarm_count=6,
        detail={"secret": "leak"},
    )
    report = build_linkage_report(record)
    assert report.incident_count == 2
    assert report.finding_count == 4
    assert report.alarm_count == 6
    # detail is not propagated into any derived body.
    assert "leak" not in str(report.report_body())
    assert "leak" not in str(report.report_metadata_item())
    assert "leak" not in str(report.public_status_item())
