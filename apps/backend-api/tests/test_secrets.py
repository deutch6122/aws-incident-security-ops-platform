import json
import secrets
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("pydantic_settings")
pytest.importorskip("sqlalchemy")

from app.config import Settings
from app.db.secrets import (
    DatabaseConfigurationError,
    build_database_url,
    load_database_secret,
    parse_database_secret,
)
from app.db.session import Database


class FakeSecretReader:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    def get_secret_string(self, secret_arn: str) -> str:
        self.calls += 1
        return self.payload


def generated_payload() -> tuple[str, str]:
    password = secrets.token_urlsafe(24) + "/@:"
    return json.dumps(
        {
            "username": "service@user",
            "password": password,
            "host": "db.internal",
            "port": 5432,
            "dbname": "operations",
        }
    ), password


def test_secret_is_strictly_validated_and_url_preserves_special_characters() -> None:
    payload, password = generated_payload()
    secret = parse_database_secret(payload)
    url = build_database_url(secret)

    assert url.drivername == "postgresql+psycopg"
    assert url.username == "service@user"
    assert url.password == password
    assert url.host == "db.internal"
    assert url.port == 5432
    assert url.database == "operations"
    assert "***" in str(url)
    assert password not in str(url)


def _payload_with_password(base: dict, password_value: str) -> str:
    return json.dumps({**base, "password": password_value})


@pytest.mark.parametrize(
    "payload_factory, has_password_value",
    [
        # Non-JSON and non-object payloads have no password value to protect.
        (lambda pw: "not-json", False),
        (lambda pw: "[]", False),
        # Missing required keys (including password itself).
        (lambda pw: json.dumps({"username": "u"}), False),
        # Invalid port with a password value present.
        (
            lambda pw: _payload_with_password(
                {"username": "u", "host": "h", "port": True, "dbname": "d"}, pw
            ),
            True,
        ),
        (
            lambda pw: _payload_with_password(
                {"username": "u", "host": "h", "port": 70000, "dbname": "d"}, pw
            ),
            True,
        ),
    ],
)
def test_invalid_secret_payloads_raise_safe_errors(payload_factory, has_password_value: bool) -> None:
    marker = secrets.token_urlsafe(20)
    # A unique, detectable dummy password value used only to prove the real
    # password value is never echoed into the safe error message.
    secret_value = secrets.token_urlsafe(24)
    payload = payload_factory(secret_value)
    if payload == "not-json":
        payload += marker

    with pytest.raises(DatabaseConfigurationError) as captured:
        parse_database_secret(payload)

    message = str(captured.value)
    # The raw input marker must never appear in the safe error message.
    assert marker not in message
    # The actual password *value* must never leak. The word "password" as a
    # key name in messages (e.g. "field password") is acceptable; only the
    # concrete secret value must not appear.
    if has_password_value:
        assert secret_value not in message


def test_reader_errors_are_wrapped_without_leaking_original_message() -> None:
    marker = secrets.token_urlsafe(20)
    reader = Mock()
    reader.get_secret_string.side_effect = RuntimeError(marker)
    with pytest.raises(DatabaseConfigurationError) as captured:
        load_database_secret(reader, "configured-arn")
    assert marker not in str(captured.value)


def test_database_constructor_performs_no_secret_or_engine_access() -> None:
    payload, _ = generated_payload()
    reader = FakeSecretReader(payload)
    settings = Settings(db_secret_arn="configured-arn")

    with patch("app.db.session.create_engine") as create_engine:
        database = Database(settings, secret_reader=reader)
        assert reader.calls == 0
        create_engine.assert_not_called()
        database.get_engine()
        assert reader.calls == 1
        create_engine.assert_called_once()
