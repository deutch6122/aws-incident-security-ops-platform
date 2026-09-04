# Feature: aws-incident-security-ops-platform, Property 7: For any アラーム風イベントについて、同一イベント（同一 external_id）を 1 回処理した場合と 2 回以上処理した場合とで、alarm_events テーブルの当該レコードは同一であり、レコード件数は増加してはならない
# **Validates: Requirements 6.2**
"""Property 7: alarm ingestion idempotency.

Testing substitution note: tasks.md 10.3 references testcontainers. Per the
execution constraints (no Docker / no real DB), this property uses the in-memory
alarm store keyed on external_id, which replicates the alarm_events.external_id
UNIQUE + ON CONFLICT DO NOTHING semantics the database enforces.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from workers.alarm import handle_alarm_body
from workers.stores import InMemoryAlarmStore

# Smart generators constrained to the alarm event input space.
_ids = st.text(min_size=1, max_size=40).filter(lambda s: s.strip() != "")
_payloads = st.one_of(
    st.none(),
    st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), max_size=5),
)


@st.composite
def _alarm_event(draw) -> dict:
    return {
        "external_id": draw(_ids),
        "source": draw(st.sampled_from(["cloudwatch", "guardduty", "eventbridge"])),
        "event_type": draw(st.sampled_from(["alarm", "ok", "insufficient_data"])),
        "payload": draw(_payloads),
    }


@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
@given(event=_alarm_event(), repeats=st.integers(min_value=1, max_value=6))
def test_alarm_ingestion_is_idempotent(event: dict, repeats: int) -> None:
    once = InMemoryAlarmStore()
    handle_alarm_body(once, dict(event))

    many = InMemoryAlarmStore()
    for _ in range(repeats):
        handle_alarm_body(many, dict(event))

    external_id = event["external_id"].strip()
    # Count never increases beyond a single row for the same external_id.
    assert once.count() == 1
    assert many.count() == 1
    # The stored record is identical regardless of how many times it was processed.
    assert many.get(external_id) == once.get(external_id)
