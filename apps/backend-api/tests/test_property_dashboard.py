import secrets

import pytest

pytest.importorskip("hypothesis")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.repository_fakes import FakeFinding, FakeIncident, FakeStore, InMemoryRepositoryProvider

status_text = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=8
)


def _client(store: FakeStore) -> tuple[TestClient, str]:
    token = secrets.token_urlsafe(32)
    app = create_app(
        settings=Settings(internal_bearer_token=SecretStr(token)),
        repository_provider=InMemoryRepositoryProvider(store),
    )
    return TestClient(app, raise_server_exceptions=False), token


# Feature: aws-incident-security-ops-platform, Property 1: For any インシデント集合および Finding 集合について、ダッシュボード集計が返す incident_count は件数と一致し、finding_count は件数と一致し、ステータス別集計の各値の合計は総件数と一致しなければならない
# **Validates: Requirements 2.1**
@settings(max_examples=100, deadline=None)
@given(
    incident_statuses=st.lists(status_text, max_size=25),
    finding_statuses=st.lists(status_text, max_size=25),
)
def test_property_1_dashboard_aggregation_is_consistent(
    incident_statuses: list[str], finding_statuses: list[str]
) -> None:
    store = FakeStore()
    for index, incident_status in enumerate(incident_statuses, start=1):
        store.incidents.append(
            FakeIncident(
                id=store.next_id("incident"),
                external_id=f"INC-{index}",
                title=f"incident-{index}",
                severity="medium",
                status=incident_status,
            )
        )
    for index, finding_status in enumerate(finding_statuses, start=1):
        store.findings.append(
            FakeFinding(
                id=store.next_id("finding"),
                external_id=f"FND-{index}",
                title=f"finding-{index}",
                severity="medium",
                status=finding_status,
            )
        )

    client, token = _client(store)
    response = client.get("/dashboard/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()

    assert body["incident_count"] == len(incident_statuses)
    assert body["finding_count"] == len(finding_statuses)
    total = len(incident_statuses) + len(finding_statuses)
    assert sum(body["status_breakdown"].values()) == total
