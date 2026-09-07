"""Docker-free tests for the dedicated migration runner and image contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("run_migration", APP_DIR / "run_migration.py")
assert SPEC and SPEC.loader
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def _payload(**overrides: object) -> str:
    data: dict[str, object] = {
        "username": "migration_user",
        "password": "test-only-value",
        "host": "db.internal.invalid",
        "port": 5432,
    }
    data.update(overrides)
    return json.dumps(data)


def test_rds_shape_uses_backend_db_name_fallback() -> None:
    credentials = RUNNER.parse_credentials(_payload(), "appdb")
    assert credentials.dbname == "appdb"
    assert "test-only-value" not in repr(credentials)


def test_rds_managed_master_secret_uses_endpoint_fallbacks() -> None:
    payload = json.dumps({"username": "migration_user", "password": "test-only-value"})
    credentials = RUNNER.parse_credentials(payload, "appdb", "writer.cluster.internal", "5432")
    assert credentials.host == "writer.cluster.internal"
    assert credentials.port == 5432
    assert credentials.dbname == "appdb"


def test_secret_dbname_takes_precedence() -> None:
    credentials = RUNNER.parse_credentials(_payload(dbname="secret_db"), "fallback_db")
    assert credentials.dbname == "secret_db"


def test_errors_do_not_echo_secret_values() -> None:
    sensitive = "must-not-appear"
    with pytest.raises(RUNNER.MigrationConfigurationError) as caught:
        RUNNER.parse_credentials(_payload(password=sensitive, port="bad"), "appdb")
    assert sensitive not in str(caught.value)


def test_forward_files_are_sorted_and_down_file_is_excluded(tmp_path: Path) -> None:
    (tmp_path / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")
    (tmp_path / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0001_first.down.sql").write_text("DROP TABLE x;", encoding="utf-8")
    assert [path.name for path in RUNNER.forward_migration_files(tmp_path)] == [
        "0001_first.sql",
        "0002_second.sql",
    ]


def test_apply_uses_unprepared_multi_statement_execution(tmp_path: Path) -> None:
    migration = tmp_path / "0001_init.sql"
    migration.write_text("BEGIN; SELECT 1; COMMIT;", encoding="utf-8")

    class FakeConnection:
        calls: list[tuple[str, bool]] = []

        def execute(self, sql: str, *, prepare: bool) -> None:
            self.calls.append((sql, prepare))

    connection = FakeConnection()
    RUNNER.apply_migrations(connection, [migration])
    assert connection.calls == [("BEGIN; SELECT 1; COMMIT;", False)]


def test_dockerfile_uses_repository_root_paths_and_dedicated_image() -> None:
    dockerfile = (APP_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY apps/db-migration/requirements.txt" in dockerfile
    assert "COPY --chown=migration:migration db/migrations /opt/migrations" in dockerfile
    assert "apps/backend-api" not in dockerfile
    backend_dockerfile = (REPO_ROOT / "apps/backend-api/Dockerfile").read_text(encoding="utf-8")
    assert "db/migrations" not in backend_dockerfile


def test_repository_schema_defines_required_business_tables_and_constraints() -> None:
    sql = (REPO_ROOT / "db/migrations/0001_init_schema.sql").read_text(encoding="utf-8").lower()
    for table in (
        "incidents",
        "incident_comments",
        "findings",
        "finding_triage",
        "alarm_events",
        "monthly_summaries",
        "audit_logs",
    ):
        assert f"create table if not exists {table}" in sql
    assert sql.count("on delete cascade") >= 2
    assert sql.count("external_id") >= 3
