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

REQUIRED_FIELDS = ("external_id", "title", "severity")


def _client() -> tuple[TestClient, str]:
    token = secrets.token_urlsafe(32)
    app = create_app(
        settings=Settings(internal_bearer_token=SecretStr(token)),
        repository_provider=InMemoryRepositoryProvider(),
    )
    return TestClient(app, raise_server_exceptions=False), token


def _valid_payload() -> dict[str, str]:
    return {
        "external_id": "INC-1",
        "title": "database outage",
        "severity": "high",
    }


# non-empty subsets of the required fields to remove
removed_subsets = st.lists(
    st.sampled_from(REQUIRED_FIELDS), min_size=1, max_size=len(REQUIRED_FIELDS), unique=True
)


# Feature: aws-incident-security-ops-platform, Property 5: For any 有効なインシデント入力から必須項目の空でない部分集合を取り除いた入力について、インシデント作成 API は常に HTTP 400 応答を返し、かつエラー内容には取り除かれた各必須項目が欠落項目として含まれなければならない
# **Validates: Requirements 3.5**
@settings(max_examples=100, deadline=None)
@given(removed=removed_subsets)
def test_property_5_missing_required_fields_return_400_with_missing_fields(
    removed: list[str],
) -> None:
    client, token = _client()
    headers = {"Authorization": f"Bearer {token}"}

    payload = _valid_payload()
    for field in removed:
        payload.pop(field, None)

    response = client.post("/incidents", headers=headers, json=payload)
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    missing_fields = set(error["missing_fields"])
    for field in removed:
        assert field in missing_fields
