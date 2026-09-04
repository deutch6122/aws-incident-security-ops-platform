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
from app.contract_store import InMemoryContractLookup
from app.main import create_app

missing_periods = st.tuples(st.integers(min_value=2000, max_value=2099), st.integers(min_value=1, max_value=12)).map(
    lambda value: f"{value[0]:04d}{value[1]:02d}"
).filter(lambda period: period != "202401")


# Feature: aws-incident-security-ops-platform, Property 4: For any Aurora_DB / Portal_DB に存在しない任意の識別子について、当該識別子を指定した参照 API は常に HTTP 404 応答を返さなければならない
# **Validates: Requirements 3.3, 4.3, 5.2, 11.3**
@settings(max_examples=100, deadline=None)
@given(
    incident_id=st.integers(min_value=2, max_value=2**63 - 1),
    finding_id=st.integers(min_value=2, max_value=2**63 - 1),
    period=missing_periods,
)
def test_property_4_unknown_identifiers_always_return_404(
    incident_id: int, finding_id: int, period: str
) -> None:
    token = secrets.token_urlsafe(32)
    lookup = InMemoryContractLookup(
        incident_ids={1}, finding_ids={1}, summary_periods={"202401"}
    )
    client = TestClient(
        create_app(
            settings=Settings(internal_bearer_token=SecretStr(token)),
            contract_lookup=lookup,
        ),
        raise_server_exceptions=False,
    )
    headers = {"Authorization": f"Bearer {token}"}

    for path in (
        f"/_contracts/incidents/{incident_id}",
        f"/_contracts/findings/{finding_id}",
        f"/_contracts/summaries/{period}",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
