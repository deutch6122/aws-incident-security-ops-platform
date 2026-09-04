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
from app.repository_fakes import InMemoryRepositoryProvider

non_empty_text = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=40
)
optional_text = st.one_of(st.none(), st.text(max_size=80))


@st.composite
def valid_incident(draw) -> dict[str, object]:
    payload: dict[str, object] = {
        "external_id": draw(non_empty_text),
        "title": draw(non_empty_text),
        "severity": draw(st.sampled_from(["low", "medium", "high", "critical"])),
    }
    status = draw(st.one_of(st.none(), non_empty_text))
    if status is not None:
        payload["status"] = status
    description = draw(optional_text)
    if description is not None:
        payload["description"] = description
    return payload


def _client() -> tuple[TestClient, str]:
    token = secrets.token_urlsafe(32)
    app = create_app(
        settings=Settings(internal_bearer_token=SecretStr(token)),
        repository_provider=InMemoryRepositoryProvider(),
    )
    return TestClient(app, raise_server_exceptions=False), token


# Feature: aws-incident-security-ops-platform, Property 3: For any 必須項目を満たした有効なインシデント入力について、作成後に同一 ID で取得すると、取得結果は作成時に指定した内容と一致しなければならない
# **Validates: Requirements 3.4, 8.2**
@settings(max_examples=100, deadline=None)
@given(payload=valid_incident())
def test_property_3_create_then_get_roundtrip_matches(payload: dict[str, object]) -> None:
    client, token = _client()
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post("/incidents", headers=headers, json=payload)
    assert created.status_code == 201
    created_body = created.json()
    incident_id = created_body["id"]

    fetched = client.get(f"/incidents/{incident_id}", headers=headers)
    assert fetched.status_code == 200
    fetched_body = fetched.json()

    assert fetched_body["external_id"] == payload["external_id"]
    assert fetched_body["title"] == payload["title"]
    assert fetched_body["severity"] == payload["severity"]
    assert fetched_body["status"] == payload.get("status", "open")
    assert fetched_body["description"] == payload.get("description")
