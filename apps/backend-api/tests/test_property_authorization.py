import secrets

import pytest

hypothesis = pytest.importorskip("hypothesis")
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app

PROTECTED_REQUESTS = (
    ("GET", "/_contracts/protected", None),
    ("POST", "/_contracts/required-fields", {}),
    ("GET", "/_contracts/incidents/not-an-integer", None),
    ("GET", "/_contracts/findings/not-an-integer", None),
    ("GET", "/_contracts/summaries/not-a-period", None),
    ("GET", "/_contracts/unexpected-error", None),
)


@st.composite
def invalid_authorization(draw) -> str | None:
    kind = draw(st.sampled_from(("missing", "wrong-scheme", "empty-bearer", "invalid-bearer")))
    if kind == "missing":
        return None
    if kind == "wrong-scheme":
        value = draw(st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=32))
        return f"Basic {value}"
    if kind == "empty-bearer":
        return "Bearer"
    value = draw(st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=1, max_size=64).filter(lambda item: " " not in item))
    return f"Bearer {value}"


# Feature: aws-incident-security-ops-platform, Property 2: For any 保護された Backend_API エンドポイントおよび有効な認可情報を伴わない任意のリクエストについて、Backend_API は常に HTTP 401 応答を返さなければならない
# **Validates: Requirements 2.3**
@settings(max_examples=100, deadline=None)
@given(request_case=st.sampled_from(PROTECTED_REQUESTS), authorization=invalid_authorization())
def test_property_2_invalid_authorization_always_returns_401(
    request_case: tuple[str, str, dict[str, str] | None], authorization: str | None
) -> None:
    valid_token = secrets.token_urlsafe(32)
    if authorization == f"Bearer {valid_token}":
        authorization = None
    client = TestClient(
        create_app(settings=Settings(internal_bearer_token=SecretStr(valid_token))),
        raise_server_exceptions=False,
    )
    method, path, body = request_case
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
