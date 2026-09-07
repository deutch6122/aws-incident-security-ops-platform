"""Apply forward SQL migrations to Aurora without exposing credential values."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any


class MigrationConfigurationError(RuntimeError):
    """Safe failure whose message contains no credential or connection value."""


@dataclass(frozen=True, slots=True)
class DatabaseCredentials:
    username: str
    password: str = field(repr=False)
    host: str
    port: int
    dbname: str


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationConfigurationError(f"database {field_name} is not configured")
    return value.strip()


def _parse_port(value: object) -> int:
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise MigrationConfigurationError("database port is not configured")
    return value


def parse_credentials(
    payload: str,
    fallback_db_name: str | None,
    fallback_host: str | None = None,
    fallback_port: str | int | None = None,
) -> DatabaseCredentials:
    try:
        raw: Any = json.loads(payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MigrationConfigurationError("database secret is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise MigrationConfigurationError("database secret must be a JSON object")

    missing = [key for key in ("username", "password") if key not in raw]
    if missing:
        raise MigrationConfigurationError("database secret is missing required fields")

    text_fields: dict[str, str] = {}
    for key in ("username", "password"):
        value = raw[key]
        if not isinstance(value, str) or not value or (key != "password" and not value.strip()):
            raise MigrationConfigurationError("database secret contains an invalid required field")
        text_fields[key] = value if key == "password" else value.strip()

    host = _non_empty_text(raw.get("host", fallback_host), "host")
    port = _parse_port(raw.get("port", fallback_port))

    secret_dbname = raw.get("dbname")
    if secret_dbname is not None and not isinstance(secret_dbname, str):
        raise MigrationConfigurationError("database secret contains an invalid database name")
    dbname = secret_dbname.strip() if isinstance(secret_dbname, str) else ""
    if not dbname and fallback_db_name is not None:
        dbname = fallback_db_name.strip()
    if not dbname:
        raise MigrationConfigurationError("database name is not configured")

    return DatabaseCredentials(host=host, port=port, dbname=dbname, **text_fields)


def load_secret_string(client: Any, secret_arn: str) -> str:
    try:
        response = client.get_secret_value(SecretId=secret_arn)
    except Exception as exc:
        raise MigrationConfigurationError("database credentials could not be loaded") from exc
    value = response.get("SecretString")
    if not isinstance(value, str):
        raise MigrationConfigurationError("database secret must use SecretString")
    return value


def forward_migration_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise MigrationConfigurationError("migration directory is unavailable")
    files = sorted(
        path
        for path in directory.glob("[0-9][0-9][0-9][0-9]_*.sql")
        if not path.name.endswith(".down.sql")
    )
    if not files:
        raise MigrationConfigurationError("no forward migration files were found")
    return files


def apply_migrations(connection: Any, files: list[Path]) -> None:
    for path in files:
        connection.execute(path.read_text(encoding="utf-8"), prepare=False)


def main() -> int:
    secret_arn = os.getenv("BACKEND_DB_SECRET_ARN", "").strip()
    if not secret_arn:
        raise MigrationConfigurationError("BACKEND_DB_SECRET_ARN is required")

    try:
        import boto3
        import psycopg

        client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION") or None)
        payload = load_secret_string(client, secret_arn)
        credentials = parse_credentials(
            payload,
            os.getenv("BACKEND_DB_NAME"),
            os.getenv("BACKEND_DB_HOST"),
            os.getenv("BACKEND_DB_PORT"),
        )
        files = forward_migration_files(Path(os.getenv("MIGRATIONS_DIR", "/opt/migrations")))

        with psycopg.connect(
            host=credentials.host,
            port=credentials.port,
            user=credentials.username,
            password=credentials.password,
            dbname=credentials.dbname,
            connect_timeout=10,
            autocommit=True,
        ) as connection:
            apply_migrations(connection, files)
    except MigrationConfigurationError:
        raise
    except Exception as exc:
        raise MigrationConfigurationError("database migration failed") from exc

    print(f"Applied {len(files)} forward migration file(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationConfigurationError as error:
        print(f"Migration failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
