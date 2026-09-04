import secrets

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("pydantic_settings")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.repository_fakes import (
    FakeFinding,
    FakeFindingTriage,
    FakeIncident,
    FakeIncidentComment,
    FakeMonthlySummary,
    FakeStore,
    InMemoryRepositoryProvider,
)

# Business API prefixes that MUST be authentication-protected (Req 2.3 regression).
PROTECTED_BUSINESS_REQUESTS = (
    ("GET", "/dashboard/summary"),
    ("GET", "/incidents"),
    ("GET", "/incidents/1"),
    ("POST", "/incidents"),
    ("PATCH", "/incidents/1/status"),
    ("GET", "/findings"),
    ("GET", "/findings/1"),
    ("GET", "/summaries/202401"),
)


def build_client(store: FakeStore | None = None) -> tuple[TestClient, str, FakeStore]:
    resolved_store = store or FakeStore()
    token = secrets.token_urlsafe(32)
    app = create_app(
        settings=Settings(internal_bearer_token=SecretStr(token)),
        repository_provider=InMemoryRepositoryProvider(resolved_store),
    )
    return TestClient(app, raise_server_exceptions=False), token, resolved_store


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ----- 401: middleware protection extension regression ---------------------


@pytest.mark.parametrize("method,path", PROTECTED_BUSINESS_REQUESTS)
def test_business_apis_require_authentication(method: str, path: str) -> None:
    client, _, _ = build_client()
    response = client.request(method, path)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_business_apis_reject_wrong_token() -> None:
    client, _, _ = build_client()
    response = client.get("/incidents", headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_public_paths_stay_public() -> None:
    client, _, _ = build_client()
    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200


# ----- Dashboard: empty set and duplicate status boundary ------------------


def test_dashboard_summary_empty_store() -> None:
    client, token, _ = build_client()
    response = client.get("/dashboard/summary", headers=auth(token))
    assert response.status_code == 200
    assert response.json() == {
        "incident_count": 0,
        "finding_count": 0,
        "status_breakdown": {},
    }


def test_dashboard_summary_merges_duplicate_statuses() -> None:
    store = FakeStore()
    for index, status in enumerate(["open", "open", "closed"], start=1):
        store.incidents.append(
            FakeIncident(id=store.next_id("incident"), external_id=f"INC-{index}", title="t", severity="low", status=status)
        )
    for index, status in enumerate(["open", "resolved"], start=1):
        store.findings.append(
            FakeFinding(id=store.next_id("finding"), external_id=f"FND-{index}", title="t", severity="low", status=status)
        )
    client, token, _ = build_client(store)
    response = client.get("/dashboard/summary", headers=auth(token))
    body = response.json()
    assert body["incident_count"] == 3
    assert body["finding_count"] == 2
    # "open" merges across incidents(2) + findings(1) -> 3
    assert body["status_breakdown"] == {"closed": 1, "open": 3, "resolved": 1}
    assert sum(body["status_breakdown"].values()) == 5


# ----- Incidents: list / detail examples -----------------------------------


def test_list_incidents_empty_and_populated() -> None:
    store = FakeStore()
    client, token, _ = build_client(store)
    assert client.get("/incidents", headers=auth(token)).json() == []

    store.incidents.append(
        FakeIncident(id=store.next_id("incident"), external_id="INC-1", title="outage", severity="high", status="open")
    )
    listed = client.get("/incidents", headers=auth(token)).json()
    assert len(listed) == 1
    assert listed[0]["external_id"] == "INC-1"


def test_incident_detail_includes_comments() -> None:
    store = FakeStore()
    store.incidents.append(
        FakeIncident(id=store.next_id("incident"), external_id="INC-1", title="outage", severity="high", status="open")
    )
    store.comments.append(
        FakeIncidentComment(id=store.next_id("comment"), incident_id=1, author="ops", body="investigating")
    )
    client, token, _ = build_client(store)
    detail = client.get("/incidents/1", headers=auth(token))
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == 1
    assert len(body["comments"]) == 1
    assert body["comments"][0]["body"] == "investigating"


def test_incident_detail_unknown_returns_404() -> None:
    client, token, _ = build_client()
    response = client.get("/incidents/999", headers=auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["resource"] == "incident"


def test_create_incident_missing_fields_returns_400() -> None:
    client, token, _ = build_client()
    response = client.post("/incidents", headers=auth(token), json={"title": "only title"})
    assert response.status_code == 400
    missing = set(response.json()["error"]["missing_fields"])
    assert {"external_id", "severity"} <= missing


def test_create_incident_success_defaults_status_open() -> None:
    client, token, _ = build_client()
    response = client.post(
        "/incidents",
        headers=auth(token),
        json={"external_id": "INC-9", "title": "disk full", "severity": "medium"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "open"
    assert body["external_id"] == "INC-9"


def test_patch_status_unknown_incident_returns_404() -> None:
    client, token, _ = build_client()
    response = client.patch("/incidents/999/status", headers=auth(token), json={"status": "closed"})
    assert response.status_code == 404


def test_patch_status_updates_and_records_audit() -> None:
    store = FakeStore()
    store.incidents.append(
        FakeIncident(id=store.next_id("incident"), external_id="INC-1", title="t", severity="high", status="open")
    )
    client, token, _ = build_client(store)
    response = client.patch("/incidents/1/status", headers=auth(token), json={"status": "closed"})
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert len(store.audit_logs) == 1
    assert store.audit_logs[0].before_value == {"status": "open"}
    assert store.audit_logs[0].after_value == {"status": "closed"}


# ----- Findings ------------------------------------------------------------


def test_list_findings_and_detail_with_triage() -> None:
    store = FakeStore()
    store.findings.append(
        FakeFinding(id=store.next_id("finding"), external_id="FND-1", title="s3 public", severity="high", status="new")
    )
    store.triage.append(
        FakeFindingTriage(id=store.next_id("triage"), finding_id=1, triage_status="confirmed", assessed_severity="high")
    )
    client, token, _ = build_client(store)

    assert len(client.get("/findings", headers=auth(token)).json()) == 1

    detail = client.get("/findings/1", headers=auth(token))
    assert detail.status_code == 200
    body = detail.json()
    assert len(body["triage"]) == 1
    assert body["triage"][0]["triage_status"] == "confirmed"


def test_finding_detail_unknown_returns_404() -> None:
    client, token, _ = build_client()
    response = client.get("/findings/999", headers=auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["resource"] == "finding"


# ----- Monthly summaries ---------------------------------------------------


def test_summary_returns_registered_period() -> None:
    store = FakeStore()
    store.summaries.append(
        FakeMonthlySummary(
            id=store.next_id("summary"),
            period="202401",
            incident_count=3,
            finding_count=5,
            alarm_count=7,
            detail={"note": "january"},
        )
    )
    client, token, _ = build_client(store)
    response = client.get("/summaries/202401", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["period"] == "202401"
    assert body["incident_count"] == 3
    assert body["alarm_count"] == 7


def test_summary_unknown_period_returns_404() -> None:
    client, token, _ = build_client()
    response = client.get("/summaries/209912", headers=auth(token))
    assert response.status_code == 404
    assert response.json()["error"]["resource"] == "summary"


def test_summary_malformed_period_returns_404() -> None:
    client, token, _ = build_client()
    response = client.get("/summaries/2024-1", headers=auth(token))
    assert response.status_code == 404


def test_no_sensitive_data_in_responses() -> None:
    store = FakeStore()
    store.incidents.append(
        FakeIncident(id=store.next_id("incident"), external_id="INC-1", title="t", severity="high", status="open")
    )
    client, token, _ = build_client(store)
    payload = client.get("/incidents/1", headers=auth(token)).text.lower()
    for secret_marker in ("password", "secret", "authorization", "postgresql://"):
        assert secret_marker not in payload
