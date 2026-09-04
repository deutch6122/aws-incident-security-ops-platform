import secrets

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.contract_store import InMemoryContractLookup
from app.main import create_app


@pytest.fixture
def client_and_token() -> tuple[TestClient, str]:
    token = secrets.token_urlsafe(32)
    settings = Settings(internal_bearer_token=SecretStr(token))
    app = create_app(settings=settings, contract_lookup=InMemoryContractLookup())
    return TestClient(app, raise_server_exceptions=False), token


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_openapi_are_public(client_and_token: tuple[TestClient, str]) -> None:
    client, _ = client_and_token
    assert client.get("/health").json() == {"status": "ok"}
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert schema.json()["info"]["title"] == "Product_A Backend API"


def test_unconfigured_token_fails_closed() -> None:
    client = TestClient(create_app(settings=Settings()), raise_server_exceptions=False)
    response = client.get("/_contracts/protected")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_missing_required_fields_are_normalized_to_400(client_and_token: tuple[TestClient, str]) -> None:
    client, token = client_and_token
    response = client.post("/_contracts/required-fields", headers=auth(token), json={"title": "example"})
    assert response.status_code == 400
    assert response.json()["error"]["missing_fields"] == ["severity"]


def test_not_found_error_is_safe_and_reusable(client_and_token: tuple[TestClient, str]) -> None:
    client, token = client_and_token
    response = client.get("/_contracts/incidents/987", headers=auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["resource"] == "incident"
    assert response.json()["error"]["identifier"] == "987"


def test_unexpected_error_returns_valid_correlation_id(client_and_token: tuple[TestClient, str]) -> None:
    client, token = client_and_token
    response = client.get(
        "/_contracts/unexpected-error",
        headers={**auth(token), "X-Correlation-ID": "unsafe correlation id"},
    )
    assert response.status_code == 500
    correlation_id = response.json()["correlation_id"]
    assert response.headers["X-Correlation-ID"] == correlation_id
    assert correlation_id != "unsafe correlation id"
    assert response.json()["error"]["message"] == "An unexpected error occurred"
