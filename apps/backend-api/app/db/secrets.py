"""Safe Secrets Manager port and strict database credential parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import URL


class DatabaseConfigurationError(RuntimeError):
    """Safe configuration error that never embeds a secret payload or DB URL."""


class SecretReader(Protocol):
    def get_secret_string(self, secret_arn: str) -> str:
        """Return the secret payload for an ARN."""


class Boto3SecretReader:
    """Production adapter. boto3 and its client are created only on first use."""

    def __init__(self, region_name: str) -> None:
        self._region_name = region_name

    def get_secret_string(self, secret_arn: str) -> str:
        try:
            import boto3

            client = boto3.client("secretsmanager", region_name=self._region_name)
            response = client.get_secret_value(SecretId=secret_arn)
            value = response.get("SecretString")
            if not isinstance(value, str):
                raise DatabaseConfigurationError("database secret must use SecretString")
            return value
        except DatabaseConfigurationError:
            raise
        except Exception as exc:
            raise DatabaseConfigurationError("database credentials could not be loaded") from exc


@dataclass(frozen=True, slots=True)
class DatabaseSecret:
    username: str
    password: str = field(repr=False)
    host: str
    port: int
    dbname: str


_REQUIRED_KEYS = frozenset({"username", "password", "host", "port", "dbname"})


def parse_database_secret(payload: str) -> DatabaseSecret:
    """Parse and strictly validate required DB fields without echoing input data."""

    try:
        raw: Any = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise DatabaseConfigurationError("database secret is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise DatabaseConfigurationError("database secret must be a JSON object")

    missing = sorted(_REQUIRED_KEYS.difference(raw))
    if missing:
        raise DatabaseConfigurationError(
            "database secret is missing required keys: " + ", ".join(missing)
        )

    text_values: dict[str, str] = {}
    for key in ("username", "password", "host", "dbname"):
        value = raw[key]
        if not isinstance(value, str) or not value:
            raise DatabaseConfigurationError(f"database secret field {key} must be non-empty text")
        if key != "password" and not value.strip():
            raise DatabaseConfigurationError(f"database secret field {key} must be non-empty text")
        text_values[key] = value if key == "password" else value.strip()

    port = raw["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise DatabaseConfigurationError("database secret field port must be an integer from 1 to 65535")

    return DatabaseSecret(port=port, **text_values)


def load_database_secret(reader: SecretReader, secret_arn: str) -> DatabaseSecret:
    try:
        return parse_database_secret(reader.get_secret_string(secret_arn))
    except DatabaseConfigurationError:
        raise
    except Exception as exc:
        raise DatabaseConfigurationError("database credentials could not be loaded") from exc


def build_database_url(secret: DatabaseSecret) -> URL:
    """Build a structured URL so credentials are encoded safely by SQLAlchemy."""

    return URL.create(
        drivername="postgresql+psycopg",
        username=secret.username,
        password=secret.password,
        host=secret.host,
        port=secret.port,
        database=secret.dbname,
    )
