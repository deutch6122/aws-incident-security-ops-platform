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
    # RDS-managed rotation secrets may omit dbname entirely, so it is optional.
    # An absent or blank dbname is normalized to None here and resolved later via
    # the BACKEND_DB_NAME fallback (see resolve_database_name).
    dbname: str | None = None


# dbname is intentionally NOT required: RDS-managed secrets often omit it. The
# username/password/host/port fields remain mandatory.
_REQUIRED_KEYS = frozenset({"username", "password", "host", "port"})


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

    # Required text fields (username/password/host). These keep their existing
    # strict non-empty validation; the dbname relaxation below does not weaken it.
    text_values: dict[str, str] = {}
    for key in ("username", "password", "host"):
        value = raw[key]
        if not isinstance(value, str) or not value:
            raise DatabaseConfigurationError(f"database secret field {key} must be non-empty text")
        if key != "password" and not value.strip():
            raise DatabaseConfigurationError(f"database secret field {key} must be non-empty text")
        text_values[key] = value if key == "password" else value.strip()

    port = raw["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise DatabaseConfigurationError("database secret field port must be an integer from 1 to 65535")

    # Optional dbname handling:
    #   - absent            -> None
    #   - empty/whitespace  -> None (treated as unset so the fallback can apply)
    #   - non-empty string  -> stripped and used
    #   - any non-string    -> safe DatabaseConfigurationError
    dbname: str | None
    if "dbname" not in raw:
        dbname = None
    else:
        raw_dbname = raw["dbname"]
        if raw_dbname is None:
            dbname = None
        elif isinstance(raw_dbname, str):
            stripped = raw_dbname.strip()
            dbname = stripped or None
        else:
            raise DatabaseConfigurationError("database secret field dbname must be text when present")

    return DatabaseSecret(port=port, dbname=dbname, **text_values)


def load_database_secret(reader: SecretReader, secret_arn: str) -> DatabaseSecret:
    try:
        return parse_database_secret(reader.get_secret_string(secret_arn))
    except DatabaseConfigurationError:
        raise
    except Exception as exc:
        raise DatabaseConfigurationError("database credentials could not be loaded") from exc


def resolve_database_name(secret: DatabaseSecret, fallback_db_name: str | None) -> str:
    """Resolve the effective database name without leaking any configured value.

    Resolution order (Requirements 3.4, 3.5, 3.6):
      1. A non-empty dbname carried in the secret.
      2. The BACKEND_DB_NAME fallback (passed in as fallback_db_name).
      3. Otherwise a safe DatabaseConfigurationError with a fixed message that
         includes neither the secret value nor the environment value.
    """

    if secret.dbname is not None:
        # parse_database_secret already stripped and rejected blank values.
        return secret.dbname

    if fallback_db_name is not None:
        candidate = fallback_db_name.strip()
        if candidate:
            return candidate

    raise DatabaseConfigurationError(
        "database name is not configured: the secret has no dbname and no fallback was provided"
    )


def build_database_url(secret: DatabaseSecret, fallback_db_name: str | None = None) -> URL:
    """Build a structured URL so credentials are encoded safely by SQLAlchemy.

    Backward compatible: an existing caller passing a secret that carries a
    non-empty dbname keeps working as build_database_url(secret). When the secret
    omits dbname, the fallback_db_name (BACKEND_DB_NAME) supplies the value.
    """

    database = resolve_database_name(secret, fallback_db_name)
    return URL.create(
        drivername="postgresql+psycopg",
        username=secret.username,
        password=secret.password,
        host=secret.host,
        port=secret.port,
        database=database,
    )
