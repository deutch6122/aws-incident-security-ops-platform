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
from app.repository_fakes import FakeIncident, FakeStore, InMemoryRepositoryProvider

status_text = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1, max_size=12
)


def _client(store: FakeStore) -> tuple[TestClient, str]:
    token = secrets.token_urlsafe(32)
    app = create_app(
        settings=Settings(internal_bearer_token=SecretStr(token)),
        repository_provider=InMemoryRepositoryProvider(store),
    )
    return TestClient(app, raise_server_exceptions=False), token


# Feature: aws-incident-security-ops-platform, Property 6: For any 登録済みインシデントまたは Finding と、その任意の有効な状態変更について、状態変更操作の後に audit_logs のレコード件数はちょうど 1 件増加し、変更前後の値が記録されなければならない
# **Validates: Requirements 3.6, 8.3**
@settings(max_examples=100, deadline=None)
@given(initial_status=status_text, new_status=status_text)
def test_property_6_status_change_records_exactly_one_audit_log(
    initial_status: str, new_status: str
) -> None:
    store = FakeStore()
    incident = FakeIncident(
        id=store.next_id("incident"),
        external_id="INC-1",
        title="incident",
        severity="high",
        status=initial_status,
    )
    store.incidents.append(incident)

    client, token = _client(store)
    headers = {"Authorization": f"Bearer {token}"}

    before_count = len(store.audit_logs)
    response = client.patch(
        f"/incidents/{incident.id}/status", headers=headers, json={"status": new_status}
    )
    assert response.status_code == 200
    assert response.json()["status"] == new_status

    assert len(store.audit_logs) == before_count + 1
    record = store.audit_logs[-1]
    assert record.entity_type == "incident"
    assert record.entity_id == incident.id
    assert record.before_value == {"status": initial_status}
    assert record.after_value == {"status": new_status}
