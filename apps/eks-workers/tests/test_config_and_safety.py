"""Unit tests for config parsing, secret redaction, and import-time safety.

Pure stdlib for config/redaction; the secrets module needs SQLAlchemy (URL) so
those specific assertions are guarded with importorskip.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workers.config import WorkerConfigurationError, WorkerSettings


def test_settings_from_env_reads_non_secret_values() -> None:
    env = {
        "WORKER_AWS_REGION": "ap-northeast-1",
        "WORKER_DB_SECRET_ARN": "arn:aws:secretsmanager:ap-northeast-1:111122223333:secret:db-abc",
        "WORKER_SQS_QUEUE_URL": "https://sqs.ap-northeast-1.amazonaws.com/111122223333/q",
        "WORKER_MAX_MESSAGES": "5",
    }
    settings = WorkerSettings.from_env(env)
    assert settings.aws_region == "ap-northeast-1"
    assert settings.db_secret_arn == env["WORKER_DB_SECRET_ARN"]
    assert settings.max_messages == 5


def test_missing_required_config_raises_without_leaking() -> None:
    settings = WorkerSettings.from_env({})
    with pytest.raises(WorkerConfigurationError):
        settings.require_db_secret_arn()
    with pytest.raises(WorkerConfigurationError):
        settings.require_sqs_queue_url()


def test_invalid_int_config_raises() -> None:
    with pytest.raises(WorkerConfigurationError):
        WorkerSettings.from_env({"WORKER_MAX_MESSAGES": "not-a-number"})


def test_importing_workers_package_does_no_io() -> None:
    # Importing the package and pure modules must not touch AWS or a DB.
    import importlib

    for name in ("workers", "workers.config", "workers.sqs", "workers.stores",
                 "workers.alarm", "workers.finding", "workers.summary",
                 "workers.linkage", "workers.portal_adapters"):
        importlib.import_module(name)


def test_database_secret_repr_and_errors_do_not_leak_password() -> None:
    pytest.importorskip("sqlalchemy")
    from workers.db.secrets import (
        DatabaseConfigurationError,
        DatabaseSecret,
        parse_database_secret,
    )

    secret = DatabaseSecret(username="u", password="s3cr3t-pw", host="h", port=5432, dbname="d")
    # The password field is repr=False, so it must not appear in the repr.
    assert "s3cr3t-pw" not in repr(secret)

    # A malformed payload raises a generic message with no payload content.
    try:
        parse_database_secret('{"username": "u"}')
    except DatabaseConfigurationError as exc:
        assert "s3cr3t-pw" not in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected DatabaseConfigurationError")


def test_build_database_url_is_structured_and_hides_password() -> None:
    pytest.importorskip("sqlalchemy")
    from workers.db.secrets import DatabaseSecret, build_database_url

    url = build_database_url(
        DatabaseSecret(username="u", password="s3cr3t-pw", host="h", port=5432, dbname="d")
    )
    # SQLAlchemy URL renders the password as *** by default.
    assert "s3cr3t-pw" not in repr(url)
    assert url.drivername == "postgresql+psycopg"
