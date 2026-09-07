"""Property + unit tests for BACKEND_DB_NAME fallback resolution.

Feature: dev-full-stack-wiring, Property 1
Validates: Requirements 3.4, 3.5, 3.6

Property 1 asserts that, for any RDS-managed-style secret payload that carries
username/password and omits dbname, the resolved database name always equals
the non-empty BACKEND_DB_NAME fallback value. The tests also confirm the secret
password value, raw payload, and DB URL never leak into exceptions, str/repr
output, or the resolved value.
"""

import json
import secrets

import pytest

pytest.importorskip("hypothesis")
pytest.importorskip("sqlalchemy")

from hypothesis import given, settings, strategies as st

from app.db.secrets import (
    DatabaseConfigurationError,
    DatabaseSecret,
    build_database_url,
    parse_database_secret,
    resolve_database_name,
)

# Identifier-like strategy for db names and fallbacks (non-empty, no surrounding
# whitespace so the value survives a strip() unchanged).
_db_name = st.text(
    alphabet=st.characters(min_codepoint=48, max_codepoint=122),
    min_size=1,
    max_size=40,
).map(lambda s: s.strip()).filter(lambda s: len(s) > 0)

_host = st.text(
    alphabet=st.characters(min_codepoint=97, max_codepoint=122),
    min_size=1,
    max_size=20,
).filter(lambda s: len(s.strip()) > 0)

_port = st.integers(min_value=1, max_value=65535)


def _rds_managed_payload_without_dbname(username: str, password: str) -> str:
    # RDS-managed master-user secret shape observed in AWS: username/password only.
    return json.dumps({"username": username, "password": password})


# Feature: dev-full-stack-wiring, Property 1
# Validates: Requirements 3.4, 3.5, 3.6
@settings(max_examples=200, deadline=None)
@given(
    username=_host,
    password_seed=st.integers(min_value=0, max_value=2**31 - 1),
    host=_host,
    port=_port,
    fallback=_db_name,
)
def test_property_1_dbname_omitted_resolves_to_fallback(
    username: str, password_seed: int, host: str, port: int, fallback: str
) -> None:
    # A distinctive, high-entropy password value so the leakage assertions below
    # cannot pass by accident (e.g. a 1-char password being a substring of port).
    password = "PW-" + secrets.token_urlsafe(24) + f"-{password_seed}"
    payload = _rds_managed_payload_without_dbname(username, password)
    secret = parse_database_secret(payload)
    # dbname omitted -> normalized to None.
    assert secret.dbname is None

    resolved = resolve_database_name(secret, fallback)
    assert resolved == fallback

    url = build_database_url(secret, fallback, host, port)
    assert url.database == fallback
    assert url.host == host
    assert url.port == port

    # The password value, raw payload, and resolved URL must not leak into the
    # str/repr of the secret dataclass.
    for leaked in (password, payload):
        assert leaked not in repr(secret)
    # SQLAlchemy masks the password in str(url).
    assert password not in str(url)


def _base_secret(dbname: str | None) -> DatabaseSecret:
    return DatabaseSecret(
        username="svc",
        password=secrets.token_urlsafe(24),
        host="db.internal",
        port=5432,
        dbname=dbname,
    )


def test_secret_dbname_takes_precedence_over_fallback() -> None:
    secret = _base_secret("from_secret")
    assert resolve_database_name(secret, "from_fallback") == "from_secret"
    assert build_database_url(secret, "from_fallback").database == "from_secret"


def test_missing_dbname_uses_fallback() -> None:
    secret = _base_secret(None)
    assert resolve_database_name(secret, "fallback_db") == "fallback_db"


@pytest.mark.parametrize("blank", ["", "   ", "\t", "\n"])
def test_blank_dbname_in_payload_is_treated_as_unset(blank: str) -> None:
    payload = json.dumps(
        {"username": "u", "password": "p", "host": "h", "port": 5432, "dbname": blank}
    )
    secret = parse_database_secret(payload)
    assert secret.dbname is None
    assert resolve_database_name(secret, "fallback_db") == "fallback_db"


@pytest.mark.parametrize("blank_fallback", [None, "", "   "])
def test_both_missing_fails_safely(blank_fallback: str | None) -> None:
    secret = _base_secret(None)
    unique = secrets.token_urlsafe(16)
    with pytest.raises(DatabaseConfigurationError) as captured:
        resolve_database_name(secret, blank_fallback)
    message = str(captured.value)
    # Fixed, safe message: it must not include the password, or the fallback value.
    assert secret.password not in message
    if blank_fallback:
        assert blank_fallback not in message
    assert unique not in message


def test_rds_managed_payload_parses_successfully() -> None:
    payload = _rds_managed_payload_without_dbname("svc", secrets.token_urlsafe(24))
    secret = parse_database_secret(payload)
    assert secret.username == "svc"
    assert secret.host is None
    assert secret.port is None
    assert secret.dbname is None


def test_generated_url_database_is_resolved_name() -> None:
    secret = _base_secret(None)
    url = build_database_url(secret, "resolved_name", "fallback.internal", 5432)
    assert url.database == "resolved_name"


def test_non_string_dbname_raises_safe_error() -> None:
    payload = json.dumps(
        {"username": "u", "password": "p", "host": "h", "port": 5432, "dbname": 123}
    )
    with pytest.raises(DatabaseConfigurationError) as captured:
        parse_database_secret(payload)
    assert "123" not in str(captured.value)


def test_error_does_not_include_password_payload_or_url() -> None:
    secret = _base_secret(None)
    with pytest.raises(DatabaseConfigurationError) as captured:
        build_database_url(secret, None)
    message = str(captured.value)
    assert secret.password not in message
    assert secret.host not in message
    assert "postgresql" not in message
