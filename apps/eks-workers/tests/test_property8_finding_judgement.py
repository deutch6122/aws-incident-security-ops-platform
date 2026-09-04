# Feature: aws-incident-security-ops-platform, Property 8: For any Finding 風イベントについて、Worker_Finding による判定結果（重大度・対応ステータス）は許容される値域に収まり、findings と finding_triage は整合して登録され、かつ同一イベント（同一 external_id）の再処理でレコードが重複してはならない
# **Validates: Requirements 6.3**
"""Property 8: Finding judgement validity and idempotent, consistent registration.

Testing substitution note: tasks.md 10.5 references testcontainers. Per the
execution constraints (no Docker / no real DB), this property uses the in-memory
finding store keyed on findings.external_id, which replicates the UNIQUE +
ON CONFLICT DO NOTHING semantics; the finding and its triage are written
together so they are always consistent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from workers.finding import (
    ALLOWED_FINDING_STATUSES,
    ALLOWED_SEVERITIES,
    ALLOWED_TRIAGE_STATUSES,
    handle_finding_body,
    parse_finding_event,
    register_finding,
)
from workers.stores import InMemoryFindingStore

_ids = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
_titles = st.text(min_size=1, max_size=60).filter(lambda s: s.strip() != "")
# Include allowed severities, aliases, and arbitrary/unknown text.
_severities = st.one_of(
    st.sampled_from(["low", "medium", "high", "critical", "info", "moderate", "severe", "warning"]),
    st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
)
_resource_types = st.one_of(
    st.none(),
    st.sampled_from(["iam", "kms", "s3", "rds", "aurora", "ec2", "lambda", "vpc"]),
    st.text(min_size=1, max_size=20).filter(lambda s: s.strip() != ""),
)


@st.composite
def _finding_event(draw) -> dict:
    event = {
        "external_id": draw(_ids),
        "title": draw(_titles),
        "severity": draw(_severities),
    }
    rt = draw(_resource_types)
    if rt is not None:
        event["resource_type"] = rt
    return event


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(event=_finding_event(), repeats=st.integers(min_value=1, max_value=5))
def test_finding_judgement_and_registration(event: dict, repeats: int) -> None:
    parsed = parse_finding_event(dict(event))
    store = InMemoryFindingStore()

    judgement = None
    for _ in range(repeats):
        judgement = register_finding(store, parsed)

    assert judgement is not None
    # 1) Judgement is always within the allowed value ranges.
    assert judgement.assessed_severity in ALLOWED_SEVERITIES
    assert judgement.triage_status in ALLOWED_TRIAGE_STATUSES
    assert judgement.finding_status in ALLOWED_FINDING_STATUSES

    # 2) findings and finding_triage are registered consistently (both present).
    assert store.finding_count() == 1
    assert store.triage_count() == 1
    assert store.get_finding(parsed.external_id) is not None
    assert store.get_triage(parsed.external_id) is not None

    # 3) Re-processing the same external_id creates no duplicate rows.
    assert store.finding_count() == 1
    assert store.triage_count() == 1
