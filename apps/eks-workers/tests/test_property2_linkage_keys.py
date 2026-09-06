# Feature: dev-full-stack-wiring, Property 2: A→B 連携の決定的キー導出
# **Validates: Requirements 10.3, 10.4**
"""Property test for deterministic and period-unique Product_B keys."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from workers.linkage import public_status_id, report_id_of, report_s3_key


@st.composite
def periods(draw: st.DrawFn) -> str:
    year = draw(st.integers(min_value=2000, max_value=9999))
    month = draw(st.integers(min_value=1, max_value=12))
    return f"{year:04d}{month:02d}"


def keys_for(period: str) -> tuple[str, str, str]:
    return report_s3_key(period), report_id_of(period), public_status_id(period)


@settings(max_examples=150)
@given(period=periods())
def test_same_period_always_derives_the_same_keys(period: str) -> None:
    assert keys_for(period) == keys_for(period)


@settings(max_examples=150)
@given(first=periods(), second=periods())
def test_distinct_periods_derive_distinct_keys(first: str, second: str) -> None:
    if first == second:
        return
    first_keys = keys_for(first)
    second_keys = keys_for(second)
    assert all(left != right for left, right in zip(first_keys, second_keys, strict=True))
